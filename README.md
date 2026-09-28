# LambdaWS Jarvis

Assistente pessoal local-first para a workstation LambdaWS, com CLI, desktop
PySide6 e um daemon local compartilhado.

## Estado atual — v13

A v13 dá ao Jarvis **contexto verificável da workstation**. Em vez de inferir o
que você está fazendo, ele agora pode consultar fontes locais e determinísticas:

- sessão KDE/Wayland e informações do KWin;
- janela ativa quando `kdotool` ou `xdotool` estiver disponível;
- mídia via `playerctl`;
- serviços `systemd --user`;
- processos relevantes (Ollama, VS Code, Firefox, Konsole e Jarvis);
- projetos Git recentes em `~/Projects`, `~/Code` e variantes minúsculas;
- branch, dirty state e commits recentes de um projeto específico;
- clipboard opcional e limitado, marcado explicitamente como conteúdo não confiável.

O clipboard **não é lido por padrão**.

## Requisitos

- Python 3.14+
- uv
- Groq opcional
- Ollama recomendado para modo local
- KDE Plasma funciona mesmo sem ferramentas auxiliares, com contexto parcial
- opcionais úteis: `kdotool`, `playerctl`, `wl-clipboard`

## Instalar ou atualizar

```bash
./setup-jarvis-v13.sh
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
  |--- OllamaProvider
  |--- ToolRegistry
  |      |--- workstation_context
  |      |--- project_context
  |      |--- system/files/git/etc
  |--- SQLite MemoryStore
  |
EventBus
```

## Contexto da workstation

`workstation_context` é uma ferramenta de observação. Ela não executa ações
mutadoras. As fontes que não existirem na máquina são omitidas ou marcadas como
indisponíveis.

Para um repositório específico, `project_context(path)` retorna branch,
alterações locais e commits recentes.

## Memória

O banco persistente continua em:

```text
~/.local/share/lambdaws-jarvis/data/jarvis.db
```

## Próximos passos

1. instalar uma integração KWin própria para janela/workspace com fidelidade total;
2. pipeline de voz realtime com wake word, VAD, STT e TTS;
3. automações proativas e scheduler;
4. memória episódica e contexto temporal;
5. overlay nativo do Plasma.
