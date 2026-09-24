#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$ROOT/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
    printf 'No encuentro el entorno virtual en %s/.venv\n' "$ROOT" >&2
    exit 1
fi

if ! "$PYTHON" -m PyInstaller --version >/dev/null 2>&1; then
    printf 'Instala PyInstaller con: %s -m pip install pyinstaller\n' "$PYTHON" >&2
    exit 1
fi

"$PYTHON" -m PyInstaller \
    --noconfirm --clean --onefile --windowed \
    --name asistente-estudio \
    --hidden-import=gi.repository.Gio \
    --hidden-import=gi.repository.GLib \
    "$ROOT/estudio.py"

install -Dm755 "$ROOT/dist/asistente-estudio" "$HOME/.local/bin/asistente-estudio"
printf 'Instalado en %s/.local/bin/asistente-estudio\n' "$HOME"
