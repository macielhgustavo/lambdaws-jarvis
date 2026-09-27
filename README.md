# LambdaWS Jarvis

Assistente local em Python com interface de terminal e interface grafica em PySide6.

## Requisitos

- Python 3.14+
- uv
- Chave da Groq configurada fora do repositorio

## Instalar ou atualizar

```bash
./setup-jarvis-v10.sh
```

O instalador sincroniza dependencias, valida o codigo, cria os atalhos `jarvis` e `jarvis-ui`, e registra o atalho de desktop.

## Uso

```bash
jarvis
jarvis-ui
```

## Dados locais

O repositorio nao versiona dados privados ou gerados automaticamente:

- `data/`, com historico local de conversa
- `backups/`, com backups de instalacao
- `.venv/`, caches e bytecode
- arquivos de credencial como `secrets.env`
