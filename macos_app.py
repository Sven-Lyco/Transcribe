"""
Einstiegspunkt der Mac-App (Transcribe.app)
============================================
Startet den Server aus transcribe.py im Hintergrund und zeigt die Oberfläche
in einem eigenen Fenster (pywebview, WKWebView). Gebaut wird die App mit
packaging/macos/build.sh.
"""

import os
import sys
import threading
from pathlib import Path

HOME = Path.home()
SUPPORT_DIR = HOME / "Library" / "Application Support" / "Transcribe"
LOG_FILE = HOME / "Library" / "Logs" / "Transcribe" / "transcribe.log"

# Muss vor dem Import von transcribe (und damit numba) gesetzt sein:
# Das App-Bundle ist schreibgeschützt, Transkripte und numba-Cache brauchen einen anderen Ort.
os.environ.setdefault("TRANSCRIBE_OUTPUT_DIR", str(HOME / "Documents" / "Transkripte"))
os.environ.setdefault("NUMBA_CACHE_DIR", str(HOME / "Library" / "Caches" / "Transcribe" / "numba"))

# Die App bringt ein eigenes FFmpeg mit (packaging/macos/build_ffmpeg.sh)
if getattr(sys, "frozen", False):
    os.environ["PATH"] = os.pathsep.join([str(Path(sys._MEIPASS) / "bin"), os.environ.get("PATH", "")])


def redirect_output():
    """Eine App ohne Terminal hat kein stdout/stderr. Ausgaben und Fortschrittsbalken gehen ins Log."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log = open(LOG_FILE, "a", buffering=1, encoding="utf-8")
    sys.stdout = sys.stderr = log


def keep_full_speed():
    """Meldet bei macOS eine vom Nutzer angestoßene Aktivität an.

    Sonst bekommt die App weniger Rechenzeit, sobald ihr Fenster im Hintergrund liegt,
    und eine Transkription dauert spürbar länger. Der Ruhezustand bleibt erlaubt.
    """
    from Foundation import NSProcessInfo
    user_initiated_allowing_idle_sleep = 0x00EFFFFF
    latency_critical = 0xFF00000000
    return NSProcessInfo.processInfo().beginActivityWithOptions_reason_(
        user_initiated_allowing_idle_sleep | latency_critical, "Transkription",
    )


def main():
    redirect_output()
    activity = keep_full_speed()  # Referenz halten, solange die App läuft

    import webview
    import transcribe

    transcribe.load_engines()
    # Fester Port, weil der Verlauf im localStorage am Origin hängt; nur wenn belegt ein anderer
    httpd = transcribe.create_server(transcribe.DEFAULT_PORT, interactive=False)
    url = f"http://{transcribe.HOST}:{httpd.server_address[1]}"
    print(f"Transcribe {transcribe.VERSION} läuft auf {url}")
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    threading.Thread(target=transcribe._prune_jobs_forever, daemon=True).start()

    webview.settings["ALLOW_DOWNLOADS"] = True  # für „Verlauf exportieren“
    webview.create_window(
        "Transcribe", url, width=760, height=900, min_size=(520, 600), background_color="#0f0f0f",
    )
    SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
    # private_mode=False, sonst löscht pywebview den localStorage (und damit den Verlauf) bei jedem Start
    webview.start(private_mode=False, storage_path=str(SUPPORT_DIR / "webview"))

    # Fenster geschlossen: App beenden
    httpd.shutdown()


if __name__ == "__main__":
    # Muss als Erstes laufen: Hilfsprozesse von multiprocessing (z.B. der resource_tracker, den tqdm
    # anstößt) starten die App-Datei erneut. Ohne das würde jeder davon eine weitere App starten.
    import multiprocessing
    multiprocessing.freeze_support()
    main()
