import json
import os
import platform
import socket
import subprocess
import sys
from pathlib import Path

from groq import Groq
from rich.console import Console
from rich.markdown import Markdown
from rich.prompt import Prompt


console = Console()

MODEL = "openai/gpt-oss-120b"
OLLAMA_MODEL = "qwen3:4b"

HOME = Path.home().resolve()
PROJECTS = (HOME / "Projects").resolve()

DATA_DIR = HOME / ".local/share/lambdaws-jarvis/data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

HISTORY_FILE = DATA_DIR / "history.json"

SYSTEM = """
Você é Jarvis, o assistente pessoal da workstation LambdaWS.

Você conversa em português brasileiro por padrão.

Seu objetivo é ajudar o usuário a:
- programar;
- estudar;
- pesquisar;
- organizar projetos;
- usar Linux/Fedora/KDE;
- trabalhar com Git;
- operar a workstation de forma eficiente.

Você possui algumas ferramentas locais seguras.

Regras:
- Não invente resultados de ferramentas.
- Use ferramentas quando precisar observar o estado real da máquina.
- Nunca afirme que abriu, leu ou executou algo sem usar a ferramenta adequada.
- Não tente contornar as limitações das ferramentas.
- Seja direto e útil.
- Para operações potencialmente destrutivas, explique o comando em vez de executá-lo.
"""


# ============================================================
# History
# ============================================================

def load_history():
    try:
        if HISTORY_FILE.exists():
            data = json.loads(HISTORY_FILE.read_text())
            if isinstance(data, list):
                return data[-30:]
    except Exception:
        pass

    return []


def save_history(history):
    try:
        HISTORY_FILE.write_text(
            json.dumps(history[-30:], ensure_ascii=False, indent=2)
        )
    except Exception:
        pass


# ============================================================
# Segurança de paths
# ============================================================

def safe_path(raw: str) -> Path:
    path = Path(raw).expanduser()

    if not path.is_absolute():
        path = HOME / path

    path = path.resolve()

    allowed = (
        path == HOME
        or HOME in path.parents
    )

    if not allowed:
        raise ValueError("Acesso permitido apenas dentro da home do usuário.")

    return path


# ============================================================
# Tools
# ============================================================

def system_info():
    result = {
        "hostname": socket.gethostname(),
        "os": platform.platform(),
        "kernel": platform.release(),
        "architecture": platform.machine(),
    }

    try:
        result["uptime"] = subprocess.check_output(
            ["uptime", "-p"],
            text=True
        ).strip()
    except Exception:
        pass

    try:
        result["memory"] = subprocess.check_output(
            ["free", "-h"],
            text=True
        )
    except Exception:
        pass

    try:
        result["disk"] = subprocess.check_output(
            ["df", "-h", "/"],
            text=True
        )
    except Exception:
        pass

    return result


def list_directory(path="."):
    p = safe_path(path)

    if not p.exists():
        return {"error": "Caminho não existe."}

    if not p.is_dir():
        return {"error": "O caminho não é um diretório."}

    items = []

    for child in sorted(p.iterdir())[:200]:
        items.append({
            "name": child.name,
            "type": "dir" if child.is_dir() else "file",
        })

    return {
        "path": str(p),
        "items": items
    }


def read_text_file(path):
    p = safe_path(path)

    if not p.exists():
        return {"error": "Arquivo não existe."}

    if not p.is_file():
        return {"error": "Não é um arquivo."}

    if p.stat().st_size > 1_000_000:
        return {"error": "Arquivo maior que 1 MB."}

    try:
        text = p.read_text(errors="replace")
    except Exception as e:
        return {"error": str(e)}

    # evita jogar arquivos enormes no contexto
    if len(text) > 30_000:
        text = text[:30_000] + "\n\n[arquivo truncado]"

    return {
        "path": str(p),
        "content": text,
    }


def git_status(path="."):
    p = safe_path(path)

    if not p.is_dir():
        return {"error": "Diretório inválido."}

    try:
        root = subprocess.check_output(
            ["git", "-C", str(p), "rev-parse", "--show-toplevel"],
            text=True,
            stderr=subprocess.STDOUT
        ).strip()

        status = subprocess.check_output(
            ["git", "-C", str(p), "status", "--short", "--branch"],
            text=True,
            stderr=subprocess.STDOUT
        )

        return {
            "repo": root,
            "status": status
        }

    except subprocess.CalledProcessError:
        return {"error": "Não é um repositório Git."}


def git_log(path=".", count=10):
    p = safe_path(path)

    count = max(1, min(int(count), 30))

    try:
        result = subprocess.check_output(
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

        return {"log": result}

    except subprocess.CalledProcessError as e:
        return {"error": e.output}


def open_application(application):
    allowed = {
        "firefox": ["firefox"],
        "code": ["code"],
        "vscode": ["code"],
        "dolphin": ["dolphin"],
        "konsole": ["konsole"],
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

    if key not in allowed:
        return {
            "error": "Aplicativo não está na lista permitida.",
            "allowed": sorted(allowed)
        }

    try:
        subprocess.Popen(
            allowed[key],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )

        return {
            "success": True,
            "application": key
        }

    except Exception as e:
        return {"error": str(e)}


def open_url(url):
    if not (
        url.startswith("https://")
        or url.startswith("http://")
    ):
        return {"error": "Somente URLs http/https são permitidas."}

    try:
        subprocess.Popen(
            ["xdg-open", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )

        return {"success": True, "url": url}

    except Exception as e:
        return {"error": str(e)}


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "system_info",
            "description": "Obtém informações reais do computador.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "Lista arquivos e diretórios dentro da home.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string"
                    }
                },
                "required": ["path"],
                "additionalProperties": False
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "read_text_file",
            "description": "Lê um arquivo texto dentro da home.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string"
                    }
                },
                "required": ["path"],
                "additionalProperties": False
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Mostra o status de um repositório Git.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string"
                    }
                },
                "required": ["path"],
                "additionalProperties": False
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "git_log",
            "description": "Lê os commits recentes de um repositório Git.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string"
                    },
                    "count": {
                        "type": "integer"
                    }
                },
                "required": ["path"],
                "additionalProperties": False
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Abre um aplicativo permitido no desktop.",
            "parameters": {
                "type": "object",
                "properties": {
                    "application": {
                        "type": "string"
                    }
                },
                "required": ["application"],
                "additionalProperties": False
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "Abre uma URL http/https no navegador.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string"
                    }
                },
                "required": ["url"],
                "additionalProperties": False
            }
        }
    },
]


FUNCTIONS = {
    "system_info": lambda **_: system_info(),
    "list_directory": list_directory,
    "read_text_file": read_text_file,
    "git_status": git_status,
    "git_log": git_log,
    "open_application": open_application,
    "open_url": open_url,
}


# ============================================================
# Ollama fallback
# ============================================================

def ollama_fallback(prompt):
    try:
        result = subprocess.check_output(
            ["ollama", "run", OLLAMA_MODEL, prompt],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=180
        )

        return result.strip()

    except Exception as e:
        return f"Groq indisponível e fallback local falhou: {e}"


# ============================================================
# Agent loop
# ============================================================

def run_groq(messages):
    client = Groq(api_key=os.environ["GROQ_API_KEY"])

    for _ in range(8):

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )

        msg = response.choices[0].message

        assistant_msg = {
            "role": "assistant",
            "content": msg.content or "",
        }

        if msg.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": call.id,
                    "type": call.type,
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    }
                }
                for call in msg.tool_calls
            ]

        messages.append(assistant_msg)

        if not msg.tool_calls:
            return msg.content or ""

        for call in msg.tool_calls:

            name = call.function.name

            try:
                args = json.loads(call.function.arguments or "{}")
            except Exception:
                args = {}

            fn = FUNCTIONS.get(name)

            if not fn:
                result = {"error": f"Ferramenta desconhecida: {name}"}
            else:
                try:
                    result = fn(**args)
                except Exception as e:
                    result = {"error": str(e)}

            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(
                    result,
                    ensure_ascii=False
                )
            })

    return "Limite de etapas do agente atingido."


def ask(prompt, history):
    messages = [
        {
            "role": "system",
            "content": SYSTEM
        }
    ]

    messages.extend(history[-20:])

    messages.append({
        "role": "user",
        "content": prompt
    })

    try:
        answer = run_groq(messages)
        backend = "Groq · GPT-OSS 120B"

    except Exception as e:
        console.print(
            f"[yellow]Groq indisponível ({e}). Usando Ollama...[/yellow]"
        )

        answer = ollama_fallback(prompt)
        backend = "Ollama · Qwen3 4B"

    history.append({
        "role": "user",
        "content": prompt
    })

    history.append({
        "role": "assistant",
        "content": answer
    })

    save_history(history)

    return answer, backend


# ============================================================
# UI
# ============================================================

def banner():
    console.print()
    console.print(
        "[bold cyan]JARVIS[/bold cyan] "
        "[dim]LambdaWS Assistant[/dim]"
    )
    console.print(
        "[dim]Groq GPT-OSS 120B · Ollama fallback[/dim]"
    )
    console.print(
        "[dim]/clear limpa memória · /exit sai[/dim]"
    )
    console.print()


def interactive():
    history = load_history()

    banner()

    while True:

        try:
            prompt = Prompt.ask("[bold cyan]Você[/bold cyan]").strip()

        except (KeyboardInterrupt, EOFError):
            console.print()
            return

        if not prompt:
            continue

        if prompt in {"/exit", "/quit"}:
            return

        if prompt == "/clear":
            history.clear()
            save_history(history)
            console.print("[green]Memória da conversa limpa.[/green]")
            continue

        answer, backend = ask(prompt, history)

        console.print()
        console.print(Markdown(answer))
        console.print(f"\n[dim]{backend}[/dim]\n")


def main():
    if len(sys.argv) > 1:

        prompt = " ".join(sys.argv[1:])
        history = load_history()

        answer, backend = ask(prompt, history)

        console.print(Markdown(answer))
        console.print(f"\n[dim]{backend}[/dim]")

    else:
        interactive()


if __name__ == "__main__":
    main()
