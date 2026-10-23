# Gehostete Variante für Coolify & Co.: faster-whisper auf der CPU, keine Dateien auf dem Server.
# Audio wird über PyAV dekodiert, das ffmpeg-Paket des Systems wird nicht gebraucht.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TRANSCRIBE_HOSTED=1 \
    HF_HOME=/models \
    HF_HUB_DISABLE_TELEMETRY=1

WORKDIR /app
COPY requirements-server.txt .
RUN pip install -r requirements-server.txt

# Modelle landen im Volume /models, damit sie Neustarts und Deployments überleben
RUN useradd --create-home --uid 1000 app && mkdir /models && chown app:app /models
VOLUME /models

COPY transcribe.py .
COPY static ./static

USER app
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/config', timeout=4)"

CMD ["python", "transcribe.py", "--port", "8765"]
