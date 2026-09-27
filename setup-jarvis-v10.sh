#!/usr/bin/env bash
set -Eeuo pipefail

GREEN="\033[1;32m"
BLUE="\033[1;34m"
RED="\033[1;31m"
RESET="\033[0m"

info() { echo -e "\n${BLUE}==>${RESET} $1"; }
ok() { echo -e "${GREEN}✓${RESET} $1"; }
fail() { echo -e "${RED}✗${RESET} $1"; exit 1; }

[[ "$EUID" -ne 0 ]] || fail "Não rode com sudo."
command -v uv >/dev/null 2>&1 || fail "uv não encontrado."

BASE="$HOME/.local/share/lambdaws-jarvis"
BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"
BACKUP="$BASE/backups/v11-$(date +%Y%m%d-%H%M%S)"

[[ -d "$BASE" ]] || fail "Instalação do Jarvis não encontrada em $BASE."

for file in core.py jarvis_cli.py jarvis_gui.py pyproject.toml test_core.py test_gui.py test_architecture.py; do
    [[ -f "$BASE/$file" ]] || fail "Arquivo ausente: $BASE/$file"
done

info "Criando backup recuperável da instalação atual..."
mkdir -p "$BACKUP"
cp -a "$BASE/core.py" "$BASE/jarvis_cli.py" "$BASE/jarvis_gui.py" \
    "$BASE/pyproject.toml" "$BASE/test_core.py" "$BASE/test_gui.py" \
    "$BASE/test_architecture.py" "$BASE/jarvis_arch" "$BACKUP/"
ok "Backup em $BACKUP"

info "Sincronizando dependências da V11..."
uv sync --directory "$BASE"

info "Validando o núcleo..."
uv run --directory "$BASE" python -m py_compile \
    core.py jarvis_cli.py jarvis_gui.py test_core.py test_gui.py test_architecture.py jarvis_arch/*.py
uv run --directory "$BASE" python -m unittest -q test_core.py test_gui.py test_architecture.py
ok "Arquitetura e núcleo validados"

info "Atualizando os atalhos..."
mkdir -p "$BIN" "$APPS"
cat > "$BIN/jarvis" <<EOF
#!/usr/bin/env bash
exec uv run --directory "$BASE" python "$BASE/jarvis_cli.py" "\$@"
EOF
cat > "$BIN/jarvis-ui" <<EOF
#!/usr/bin/env bash
exec uv run --directory "$BASE" python "$BASE/jarvis_gui.py"
EOF
chmod 755 "$BIN/jarvis" "$BIN/jarvis-ui"

cat > "$APPS/lambdaws-jarvis.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Jarvis V11
Comment=LambdaWS AI Assistant
Exec=$BIN/jarvis-ui
Icon=applications-development
Terminal=false
Categories=Utility;Development;
StartupNotify=true
EOF
chmod 644 "$APPS/lambdaws-jarvis.desktop"

ok "Jarvis V10 instalado sem alterar a credencial"
echo
echo "Terminal: jarvis"
echo "Interface: jarvis-ui"
