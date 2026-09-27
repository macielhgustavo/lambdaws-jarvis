# LambdaWS Jarvis

Assistente pessoal local-first para a workstation LambdaWS, com interface de
terminal e desktop em PySide6.

## Estado atual — v11

A v11 inicia a transição do Jarvis de um assistente monolítico para uma
plataforma modular:

- `AgentRuntime`: loop agentic independente de GUI/CLI;
- `ToolRegistry`: registro explícito de capacidades, sem dispatcher monolítico;
- `GroqProvider` e `OllamaProvider`: providers desacoplados do runtime;
- `EventBus`: contrato inicial para voz, daemon, scheduler e automações futuras;
- camada de compatibilidade em `core.Jarvis`, preservando os clientes atuais.

O comportamento da v10 foi mantido: Groq continua sendo o provider agentic
principal e Ollama/Qwen3 4B continua sendo o fallback local de texto. A nova
arquitetura permite evoluir o fallback local para tool calling sem alterar GUI,
CLI ou runtime.

## Requisitos

- Python 3.14+
- uv
- Chave da Groq configurada fora do repositorio
- Ollama opcional para fallback local

## Instalar ou atualizar

```bash
./setup-jarvis-v11.sh
```

O instalador sincroniza dependencias, valida o codigo, cria os atalhos
`jarvis` e `jarvis-ui`, e registra o atalho de desktop.

## Uso

```bash
jarvis
jarvis-ui
```

## Arquitetura

```text
CLI / GUI
    |
core.Jarvis          <- facade compatível
    |
AgentRuntime
    |------ GroqProvider
    |------ OllamaProvider
    |------ ToolRegistry
    |------ History
    |
EventBus             <- base para serviços futuros
```

Os novos componentes vivem em `jarvis_arch/`.

## Próximos passos

1. provider local com tool calling;
2. memória/contexto em SQLite;
3. pipeline de voz realtime com wake word, VAD, STT e TTS;
4. integrações KDE/D-Bus e automações proativas;
5. clientes extras sobre o daemon (overlay/web/mobile).

## Dados locais

O repositorio nao versiona dados privados ou gerados automaticamente:

- `data/`, com historico local de conversa
- `backups/`, com backups de instalacao
- `.venv/`, caches e bytecode
- arquivos de credencial como `secrets.env`
