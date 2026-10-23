#!/bin/bash
cd "$(dirname "$0")"

VENV_DIR=".venv"

# Python 3.10 oder neuer finden (mlx-whisper und aktuelle PyTorch-Versionen brauchen das)
is_supported() {
    "$1" -c 'import sys; sys.exit(sys.version_info < (3, 10))' &>/dev/null
}

PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3.14 python3; do
    if command -v "$candidate" &>/dev/null && is_supported "$candidate"; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "Python 3.10 oder neuer nicht gefunden. Bitte installieren: https://www.python.org"
    echo "(macOS: brew install python)"
    read -p "Enter drücken zum Beenden..."
    exit 1
fi

# Eine mit zu altem Python angelegte venv neu erstellen
if [ -d "$VENV_DIR" ] && ! is_supported "$VENV_DIR/bin/python"; then
    echo "Virtual Environment nutzt ein zu altes Python und wird neu erstellt..."
    rm -rf "$VENV_DIR"
fi

# Virtual Environment anlegen falls nicht vorhanden
if [ ! -d "$VENV_DIR" ]; then
    echo "Erstelle Virtual Environment mit $("$PYTHON" --version)..."
    if ! "$PYTHON" -m venv "$VENV_DIR"; then
        echo "Virtual Environment konnte nicht erstellt werden."
        read -p "Enter drücken zum Beenden..."
        exit 1
    fi
fi

# venv aktivieren
if ! source "$VENV_DIR/bin/activate"; then
    echo "Virtual Environment konnte nicht aktiviert werden. Ordner $VENV_DIR löschen und erneut starten."
    read -p "Enter drücken zum Beenden..."
    exit 1
fi

# whisper installieren falls nicht vorhanden
if ! python -c "import whisper" &>/dev/null; then
    echo "Installiere openai-whisper (einmalig)..."
    pip install --quiet openai-whisper
fi

# Auf Apple Silicon zusätzlich mlx-whisper (rechnet auf der GPU, deutlich schneller)
if [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ] && ! python -c "import mlx_whisper" &>/dev/null; then
    echo "Installiere mlx-whisper (einmalig)..."
    pip install --quiet mlx-whisper
fi

python transcribe.py "$@"

read -p "Enter drücken zum Beenden..."
