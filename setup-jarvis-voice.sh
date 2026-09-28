#!/usr/bin/env bash
set -Eeuo pipefail

BASE="$HOME/.local/share/lambdaws-jarvis"
VOICE_VENV="$BASE/.venv-voice"
SYSTEMD="$HOME/.config/systemd/user"
CONFIG="$HOME/.config/lambdaws-jarvis"

command -v uv >/dev/null 2>&1 || { echo "uv não encontrado."; exit 1; }
command -v pw-record >/dev/null 2>&1 || { echo "pw-record não encontrado (pipewire-utils)."; exit 1; }

mkdir -p "$CONFIG" "$SYSTEMD"
uv python install 3.12
uv venv "$VOICE_VENV" --python 3.12
uv pip install --python "$VOICE_VENV/bin/python" \
  groq faster-whisper piper-tts scipy scikit-learn \
  "openwakeword @ git+https://github.com/dscripka/openWakeWord.git@v0.5.1"


ENV_FILE="$CONFIG/voice.env"
touch "$ENV_FILE"
chmod 600 "$ENV_FILE"

cat > "$SYSTEMD/lambdaws-jarvis-voice.service" <<EOF
[Unit]
Description=LambdaWS Jarvis always-on voice
After=graphical-session.target lambdaws-jarvis.service
Requires=lambdaws-jarvis.service

[Service]
Type=simple
EnvironmentFile=-$ENV_FILE
WorkingDirectory=$BASE
ExecStart=$VOICE_VENV/bin/python $BASE/jarvis_voice.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now lambdaws-jarvis-voice.service

echo
echo "Voice service instalado."
echo "Wake word padrão: hey jarvis"
echo "Status: systemctl --user status lambdaws-jarvis-voice.service"
echo
echo "Para Piper, adicione ao arquivo $ENV_FILE:"
echo "JARVIS_PIPER_MODEL=/caminho/para/voz.onnx"
