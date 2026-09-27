import json
import os
import platform
import shlex
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from groq import Groq

from jarvis_arch import AgentRuntime, GroqProvider, OllamaProvider, ToolRegistry

VERSION = "11.0.0"
HOME = Path.home().resolve()

BASE = HOME / ".local/share/lambdaws-jarvis"
DATA = BASE / "data"
CONFIG = HOME / ".config/lambdaws-jarvis"

DATA.mkdir(parents=True, exist_ok=True)

HISTORY_FILE = DATA / "history-v2.json"
MEMORY_FILE = DATA / "memory.json"
MAX_HISTORY = 40
MAX_AGENT_STEPS = 8

MODEL = "openai/gpt-oss-120b"
LOCAL_MODEL = "qwen3:4b"

SENSITIVE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    "secrets.env",
    "id_rsa",
    "id_ed25519",
}


# ==========================================================
# CREDENCIAIS
# ==========================================================

def load_secret():

    secret = CONFIG / "secrets.env"

    if secret.exists():
        try:
            lines = secret.read_text(encoding="utf-8").splitlines()
        except OSError:
            return

        for line in lines:

            if "=" not in line:
                continue

            key, value = line.split("=", 1)

            if key and value:
                os.environ.setdefault(key, value)


load_secret()


# ==========================================================
# PROMPT
# ==========================================================

SYSTEM = """
Você é Jarvis v10, o assistente pessoal da workstation LambdaWS.

Fale em português brasileiro por padrão.

Você é um agente pessoal de workstation e pode usar ferramentas
para observar e controlar partes da máquina.

PRINCÍPIOS:

1. Nunca invente resultados de ferramentas.
2. Observe o sistema real quando necessário.
3. Use web_search para assuntos atuais.
4. Prefira ações pequenas e verificáveis.
5. Alterações de arquivos e Git exigem confirmação humana.
6. Você NÃO possui sudo.
7. Você NÃO pode apagar arquivos.
8. Não tente contornar as limitações de segurança.
9. Se uma ação não estiver disponível, explique ao usuário.
10. Seja direto, eficiente e técnico quando apropriado.
11. Nunca revele credenciais, chaves privadas ou o conteúdo de arquivos sensíveis.
12. Use a memória local apenas quando o usuário pedir e confirmar o salvamento.

Workspaces LambdaWS:

1 DEV
2 WEB
3 STUDY
4 TOOLS

Ferramentas transversais:
Firefox e Konsole podem ser usados em qualquer workspace.
"""


# ==========================================================
# HISTORY
# ==========================================================

def load_history():

    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))

        if isinstance(data, list):
            return [
                item for item in data[-MAX_HISTORY:]
                if isinstance(item, dict)
                and item.get("role") in {"user", "assistant"}
                and isinstance(item.get("content", ""), str)
            ]

    except (OSError, ValueError, TypeError):
        pass

    return []


def save_history(history):
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            history[-MAX_HISTORY:],
            ensure_ascii=False,
            indent=2
        )
        _atomic_write(HISTORY_FILE, payload, mode=0o600)
    except OSError:
        pass


def load_memory():
    try:
        data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def save_memory(memory):
    try:
        payload = json.dumps(memory, ensure_ascii=False, indent=2)
        _atomic_write(MEMORY_FILE, payload, mode=0o600)
    except OSError as error:
        raise RuntimeError(f"Não foi possível salvar a memória: {error}") from error


def _atomic_write(path, content, mode=0o600):
    """Escreve um arquivo local sem deixar JSON pela metade após interrupção."""
    path.parent.mkdir(parents=True, exist_ok=True)
    old_mode = path.stat().st_mode & 0o777 if path.exists() else mode
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.chmod(temporary_path, old_mode)
        os.replace(temporary_path, path)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink(missing_ok=True)


# ==========================================================
# PATH SAFETY
# ==========================================================

def safe_path(raw):

    p = Path(raw).expanduser()

    if not p.is_absolute():
        p = HOME / p

    p = p.resolve()

    if not (p == HOME or HOME in p.parents):
        raise ValueError("Acesso permitido somente dentro da sua home.")

    if _is_sensitive_path(p):
        raise ValueError("Acesso a credenciais e chaves privadas foi bloqueado.")

    return p


def _is_sensitive_path(path):
    parts = {part.lower() for part in path.parts}
    name = path.name.lower()
    return (
        ".ssh" in parts
        or name in SENSITIVE_NAMES
        or name.endswith((".pem", ".key", ".p12", ".pfx"))
    )


# ==========================================================
# READ TOOLS
# ==========================================================

def system_info():

    result = {
        "hostname": socket.gethostname(),
        "os": platform.platform(),
        "kernel": platform.release(),
    }

    commands = {
        "uptime": ["uptime", "-p"],
        "memory": ["free", "-h"],
        "disk": ["df", "-h", "/"],
    }

    for name, cmd in commands.items():

        try:
            result[name] = subprocess.check_output(
                cmd,
                text=True,
                stderr=subprocess.STDOUT
            ).strip()

        except (OSError, subprocess.SubprocessError):
            pass

    try:

        result["gpu"] = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader"
            ],
            text=True
        ).strip()

    except (OSError, subprocess.SubprocessError):
        pass

    return result


def list_directory(path="."):

    p = safe_path(path)

    if not p.exists():
        return {"error": "Caminho inexistente."}

    if not p.is_dir():
        return {"error": "Não é diretório."}

    items = []

    for child in sorted(p.iterdir())[:250]:

        items.append({
            "name": child.name,
            "type": "dir" if child.is_dir() else "file"
        })

    return {
        "path": str(p),
        "items": items
    }


def read_text_file(path):

    p = safe_path(path)

    if not p.is_file():
        return {"error": "Arquivo não encontrado."}

    if p.stat().st_size > 2_000_000:
        return {"error": "Arquivo maior que 2 MB."}

    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        return {"error": f"Não foi possível ler o arquivo: {error}"}

    if len(text) > 60_000:
        text = text[:60_000] + "\n\n[TRUNCADO]"

    return {
        "path": str(p),
        "content": text
    }


# ==========================================================
# GIT
# ==========================================================

def git_status(path="."):

    p = safe_path(path)

    try:

        output = subprocess.check_output(
            [
                "git",
                "-C",
                str(p),
                "status",
                "--short",
                "--branch"
            ],
            text=True,
            stderr=subprocess.STDOUT
        )

        return {"status": output}

    except subprocess.CalledProcessError as e:

        return {"error": e.output}


def git_log(path=".", count=10):

    p = safe_path(path)
    count = max(1, min(int(count), 40))

    try:

        output = subprocess.check_output(
            [
                "git",
                "-C",
                str(p),
                "log",
                f"-{count}",
                "--oneline",
                "--decorate"
            ],
            text=True,
            stderr=subprocess.STDOUT
        )

        return {"log": output}

    except subprocess.CalledProcessError as e:

        return {"error": e.output}


# ==========================================================
# DESKTOP
# ==========================================================

def open_application(application):

    apps = {

        "firefox": ["firefox"],
        "code": ["code"],
        "vscode": ["code"],
        "konsole": ["konsole"],
        "dolphin": ["dolphin"],

        "dbeaver": [
            "flatpak",
            "run",
            "io.dbeaver.DBeaverCommunity"
        ],

        "bruno": [
            "flatpak",
            "run",
            "com.usebruno.Bruno"
        ],

        "obsidian": [
            "flatpak",
            "run",
            "md.obsidian.Obsidian"
        ],
    }

    key = application.lower().strip()

    if key not in apps:

        return {
            "error": "Aplicativo não permitido.",
            "allowed": list(apps)
        }

    try:

        subprocess.Popen(
            apps[key],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )

        return {
            "success": True,
            "application": key
        }

    except OSError as e:

        return {"error": str(e)}


def open_url(url):

    if not url.startswith(("http://", "https://")):
        return {"error": "URL inválida."}

    try:
        subprocess.Popen(
            ["xdg-open", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as error:
        return {"error": f"Não foi possível abrir a URL: {error}"}

    return {"success": True}


# ==========================================================
# WEB
# ==========================================================

def web_search(query):

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return {"error": "GROQ_API_KEY não configurada."}

    client = Groq(
        api_key=api_key
    )

    response = client.chat.completions.create(

        model=MODEL,

        messages=[
            {
                "role": "user",
                "content":
                    "Pesquise na internet e responda de forma objetiva, "
                    "citando as fontes encontradas. Pergunta: " + query
            }
        ],

        tools=[
            {
                "type": "browser_search"
            }
        ],

        reasoning_effort="low"
    )

    return {
        "result": response.choices[0].message.content
    }


# ==========================================================
# MUTATING TOOLS
# ==========================================================

def write_text_file(path, content, confirm):

    p = safe_path(path)

    action = (
        f"Escrever arquivo:\n\n"
        f"{p}\n\n"
        f"Tamanho: {len(content)} caracteres"
    )

    if not confirm(action):
        return {"cancelled": True}

    if p.exists() and not p.is_file():
        return {"error": "O destino existe e não é um arquivo."}

    if p.exists():

        backup = p.with_suffix(
            p.suffix + ".jarvis-backup"
        )

        backup.write_bytes(p.read_bytes())

    p.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    try:
        _atomic_write(p, content, mode=0o600)
    except OSError as error:
        return {"error": f"Não foi possível escrever o arquivo: {error}"}

    return {
        "success": True,
        "path": str(p)
    }


def create_directory(path, confirm):

    p = safe_path(path)

    if not confirm(
        f"Criar diretório?\n\n{p}"
    ):
        return {"cancelled": True}

    p.mkdir(
        parents=True,
        exist_ok=True
    )

    return {
        "success": True,
        "path": str(p)
    }


def remember(key, value, confirm):
    key = str(key).strip()
    value = str(value).strip()
    if not key or not value:
        return {"error": "A chave e o valor da memória são obrigatórios."}
    if len(key) > 80 or len(value) > 2_000:
        return {"error": "Memória excede o limite permitido."}

    if not confirm(f"Salvar na memória local?\n\n{key}: {value}"):
        return {"cancelled": True}

    memory = load_memory()
    memory[key] = {"value": value, "updated_at": int(time.time())}
    save_memory(memory)
    return {"success": True, "key": key}


def recall_memory(query=""):
    memory = load_memory()
    query = str(query).strip().lower()
    if query:
        filtered = {}
        for key, item in memory.items():
            value = item.get("value", "") if isinstance(item, dict) else item
            if query in key.lower() or query in str(value).lower():
                filtered[key] = item
        memory = filtered
    return {"memory": memory}


def git_action(path, action, argument, confirm):

    p = safe_path(path)

    if not p.is_dir():
        return {"error": "Diretório Git inválido."}

    argument = str(argument or "").strip()
    if action in {"commit", "switch", "new_branch"} and not argument:
        return {"error": f"A ação Git '{action}' exige um argumento."}

    actions = {

        "add": [
            "git",
            "-C",
            str(p),
            "add",
            argument or "."
        ],

        "commit": [
            "git",
            "-C",
            str(p),
            "commit",
            "-m",
            argument
        ],

        "pull": [
            "git",
            "-C",
            str(p),
            "pull"
        ],

        "push": [
            "git",
            "-C",
            str(p),
            "push"
        ],

        "switch": [
            "git",
            "-C",
            str(p),
            "switch",
            argument
        ],

        "new_branch": [
            "git",
            "-C",
            str(p),
            "switch",
            "-c",
            argument
        ],
    }

    if action not in actions:

        return {
            "error": "Ação Git não permitida."
        }

    cmd = actions[action]

    pretty = " ".join(
        shlex.quote(x)
        for x in cmd
    )

    if not confirm(
        f"Jarvis quer executar:\n\n{pretty}"
    ):
        return {"cancelled": True}

    try:

        output = subprocess.check_output(
            cmd,
            text=True,
            stderr=subprocess.STDOUT,
            timeout=120,
        )

        return {
            "success": True,
            "output": output
        }

    except subprocess.CalledProcessError as e:

        return {
            "error": e.output
        }


# ==========================================================
# TOOL SCHEMAS
# ==========================================================

TOOLS = [

    {
        "type": "function",
        "function": {
            "name": "system_info",
            "description": "Obtém informações reais do PC.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "Lista arquivos de um diretório da home.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"}
                },
                "required": ["path"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "remember",
            "description":
                "Salva uma preferência ou fato na memória local. "
                "Sempre exige confirmação do usuário.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "string"}
                },
                "required": ["key", "value"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": "Consulta a memória local do usuário.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                }
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "read_text_file",
            "description": "Lê arquivo texto dentro da home.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"}
                },
                "required": ["path"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Obtém status Git real.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"}
                },
                "required": ["path"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "git_log",
            "description": "Obtém commits recentes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "count": {"type": "integer"}
                },
                "required": ["path"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Abre aplicativo autorizado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "application": {"type": "string"}
                },
                "required": ["application"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "Abre URL no navegador.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"}
                },
                "required": ["url"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description":
                "Pesquisa informações atuais na internet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                },
                "required": ["query"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "write_text_file",
            "description":
                "Cria ou altera um arquivo texto. "
                "Exige confirmação do usuário.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": [
                    "path",
                    "content"
                ]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "create_directory",
            "description":
                "Cria diretório. Exige confirmação.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"}
                },
                "required": ["path"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "git_action",
            "description":
                "Executa ação Git modificadora com confirmação.",
            "parameters": {
                "type": "object",
                "properties": {

                    "path": {
                        "type": "string"
                    },

                    "action": {
                        "type": "string",
                        "enum": [
                            "add",
                            "commit",
                            "pull",
                            "push",
                            "switch",
                            "new_branch"
                        ]
                    },

                    "argument": {
                        "type": "string"
                    }
                },

                "required": [
                    "path",
                    "action"
                ]
            }
        }
    }
]


# ==========================================================
# AGENT
# ==========================================================

def build_tool_registry(confirm_callback):
    """Compose the workstation capabilities exposed to the agent runtime."""

    handlers = {
        "system_info": system_info,
        "list_directory": list_directory,
        "remember": lambda **args: remember(confirm=confirm_callback, **args),
        "recall_memory": recall_memory,
        "read_text_file": read_text_file,
        "git_status": git_status,
        "git_log": git_log,
        "open_application": open_application,
        "open_url": open_url,
        "web_search": web_search,
        "write_text_file": lambda **args: write_text_file(
            confirm=confirm_callback, **args
        ),
        "create_directory": lambda **args: create_directory(
            confirm=confirm_callback, **args
        ),
        "git_action": lambda **args: git_action(
            confirm=confirm_callback, **args
        ),
    }

    categories = {
        "system_info": "system",
        "list_directory": "files",
        "read_text_file": "files",
        "write_text_file": "files",
        "create_directory": "files",
        "git_status": "git",
        "git_log": "git",
        "git_action": "git",
        "open_application": "desktop",
        "open_url": "desktop",
        "web_search": "web",
        "remember": "memory",
        "recall_memory": "memory",
    }

    registry = ToolRegistry()
    for schema in TOOLS:
        name = schema["function"]["name"]
        registry.register_schema(
            schema,
            handlers[name],
            category=categories.get(name, "general"),
        )
    return registry


class Jarvis:
    """Compatibility facade over the v11 modular agent runtime."""

    def __init__(self, confirm_callback):
        self.confirm = confirm_callback
        self.tools = build_tool_registry(confirm_callback)
        self.cloud = GroqProvider(os.environ.get("GROQ_API_KEY"), MODEL)
        self.local = OllamaProvider(LOCAL_MODEL)
        self.runtime = AgentRuntime(
            system_prompt=SYSTEM,
            cloud=self.cloud,
            local=self.local,
            tools=self.tools,
            history=load_history(),
            save_history=save_history,
            max_steps=MAX_AGENT_STEPS,
            history_window=24,
        )

        # Public attributes kept for CLI/GUI and third-party compatibility.
        self.history = self.runtime.history
        self.client = self.cloud.client

    def execute_tool(self, name, args):
        try:
            return self.tools.execute(name, args)
        except KeyError:
            return {"error": f"Ferramenta desconhecida: {name}"}

    def local_fallback(self, prompt):
        return self.runtime._fallback(prompt)

    def ask(self, prompt):
        return self.runtime.ask(prompt)

    def clear(self):
        self.runtime.clear()
