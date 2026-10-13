@echo off
cd /d "%~dp0"

set VENV_DIR=.venv

if not exist "%VENV_DIR%" (
    echo Erstelle Virtual Environment...
    py -3.11 -m venv "%VENV_DIR%" 2>nul || py -3 -m venv "%VENV_DIR%" 2>nul || python -m venv "%VENV_DIR%"
)

if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo Virtual Environment konnte nicht erstellt werden. Bitte Python 3.10 oder neuer installieren: https://www.python.org
    pause
    exit /b 1
)

call "%VENV_DIR%\Scripts\activate.bat"

python -c "import whisper" >nul 2>&1
if errorlevel 1 (
    echo Installiere openai-whisper ^(einmalig^)...
    pip install --quiet openai-whisper
)

python transcribe.py %*
pause
