@echo off
cd /d "%~dp0"

set VENV_DIR=.venv

if not exist "%VENV_DIR%" (
    echo Erstelle Virtual Environment...
    py -3.11 -m venv "%VENV_DIR%"
)

call "%VENV_DIR%\Scripts\activate.bat"

python -c "import whisper" >nul 2>&1
if errorlevel 1 (
    echo Installiere openai-whisper ^(einmalig^)...
    pip install --quiet openai-whisper
)

python transcribe.py
pause
