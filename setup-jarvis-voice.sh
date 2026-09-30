#!/usr/bin/env bash
set -Eeuo pipefail

BASE="$HOME/.local/share/lambdaws-jarvis"
VOICE_VENV="$BASE/.venv-voice"
SYSTEMD="$HOME/.config/systemd/user"
CONFIG="$HOME/.config/lambdaws-jarvis"
MODEL_DIR="$BASE/models/openwakeword"

command -v uv >/dev/null 2>&1 || { echo "uv não encontrado."; exit 1; }
command -v pw-record >/dev/null 2>&1 || { echo "pw-record não encontrado (pipewire-utils)."; exit 1; }

mkdir -p "$CONFIG" "$SYSTEMD" "$MODEL_DIR"
uv python install 3.12
uv venv "$VOICE_VENV" --python 3.12
uv pip install --python "$VOICE_VENV/bin/python" \
  groq faster-whisper piper-tts scipy scikit-learn \
  "openwakeword @ git+https://github.com/dscripka/openWakeWord.git@v0.5.1"

MODEL_DIR="$MODEL_DIR" "$VOICE_VENV/bin/python" - <<'PY'
import hashlib
import os
import pathlib
import urllib.request

base = "https://media.githubusercontent.com/media/dscripka/openWakeWord/v0.5.1/openwakeword/resources/models"
models = {
    "hey_jarvis_v0.1.onnx": "94a13cfe60075b132f6a472e7e462e8123ee70861bc3fb58434a73712ee0d2cb",
    "melspectrogram.onnx": "ba2b0e0f8b7b875369a2c89cb13360ff53bac436f2895cced9f479fa65eb176f",
    "embedding_model.onnx": "70d164290c1d095d1d4ee149bc5e00543250a7316b59f31d056cff7bd3075c1f",
}
target = pathlib.Path(os.environ["MODEL_DIR"])
target.mkdir(parents=True, exist_ok=True)

for name, expected in models.items():
    path = target / name
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        with urllib.request.urlopen(f"{base}/{name}", timeout=60) as response:
            data = response.read()
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected:
            raise SystemExit(f"Checksum inválido para {name}: {digest}")
        path.write_bytes(data)
    print(f"✓ {name}")
PY

ENV_FILE="$CONFIG/voice.env"
touch "$ENV_FILE"
chmod 600 "$ENV_FILE"
grep -v '^JARVIS_WAKEWORD_MODEL=' "$ENV_FILE" > "$ENV_FILE.tmp" || true
printf 'JARVIS_WAKEWORD_MODEL=%s\n' "$MODEL_DIR/hey_jarvis_v0.1.onnx" >> "$ENV_FILE.tmp"
mv "$ENV_FILE.tmp" "$ENV_FILE"
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
