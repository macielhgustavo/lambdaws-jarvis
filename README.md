# LambdaWS Jarvis

Assistente pessoal local-first para a workstation LambdaWS, com CLI, desktop
PySide6 e um daemon local compartilhado.

## Estado atual — v12

A v12 consolida duas peças importantes:

- **Ollama com tool calling real**: o fallback local usa o mesmo `AgentRuntime`
  e as mesmas ferramentas do provider cloud;
- **memória SQLite**: histórico e memória durável passam a usar
  `data/jarvis.db`, com migração automática dos JSONs antigos.

A v11 continua presente por baixo: `jarvisd`, IPC local, `ToolRegistry`,
providers desacoplados e `EventBus`.

## Requisitos

- Python 3.14+
- uv
- Groq opcional para provider cloud
- Ollama recomendado para modo local
- modelo local com suporte a tools, como `qwen3:4b`

## Instalar ou atualizar

```bash
./setup-jarvis-v12.sh
```

## Uso

```bash
jarvis
jarvis-ui
systemctl --user status lambdaws-jarvis.service
```

## Arquitetura

```text
CLI / GUI
    |
RemoteJarvis
    |
  jarvisd
    |
AgentRuntime
  |--- GroqProvider
  |--- OllamaProvider  <-- tools locais
  |--- ToolRegistry
  |--- SQLite MemoryStore
  |
EventBus
```

## Memória local

O banco fica em:

```text
~/.local/share/lambdaws-jarvis/data/jarvis.db
```

Na primeira abertura, se o banco estiver vazio, o Jarvis importa automaticamente:

- `history-v2.json`
- `memory.json`

Os arquivos antigos não são apagados durante a migração.

## Próximos passos

1. contexto ativo da workstation e projetos;
2. pipeline de voz realtime com wake word, VAD, STT e TTS;
3. integrações KDE/D-Bus e automações proativas;
4. memória episódica/semântica mais rica;
5. overlay e clientes remotos.
