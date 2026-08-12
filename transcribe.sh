#!/bin/bash
cd "$(dirname "$0")"

VENV_DIR=".venv"

# Python finden
if command -v python3.11 &>/dev/null; then
    PYTHON=python3.11
elif command -v python3 &>/dev/null; then
    PYTHON=python3
else
    echo "Python 3 nicht gefunden. Bitte installieren: https://www.python.org"
    read -p "Enter drücken zum Beenden..."
    exit 1
fi

# Virtual Environment anlegen falls nicht vorhanden
if [ ! -d "$VENV_DIR" ]; then
    echo "Erstelle Virtual Environment..."
    "$PYTHON" -m venv "$VENV_DIR"
fi

# venv aktivieren
source "$VENV_DIR/bin/activate"

# whisper installieren falls nicht vorhanden
if ! python -c "import whisper" &>/dev/null 2>&1; then
    echo "Installiere openai-whisper (einmalig)..."
    pip install --quiet openai-whisper
fi

python transcribe.py

read -p "Enter drücken zum Beenden..."
