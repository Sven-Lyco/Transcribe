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
import uuid
from pathlib import Path

# Alle Daten der App liegen in einem Ordner: Transkripte, Verlauf, Modelle, Caches und Log.
# So kann „Alle App-Daten löschen“ sie vor dem Deinstallieren gesammelt entfernen.
DATA_DIR = Path.home() / "Library" / "Application Support" / "Transcribe"
LOG_FILE = DATA_DIR / "transcribe.log"

# Muss vor dem Import von transcribe, numba und huggingface_hub gesetzt sein
os.environ.setdefault("TRANSCRIBE_DATA_DIR", str(DATA_DIR))
os.environ.setdefault("HF_HOME", str(DATA_DIR / "huggingface"))  # Whisper-Modelle
os.environ.setdefault("NUMBA_CACHE_DIR", str(DATA_DIR / "cache" / "numba"))  # das App-Bundle ist schreibgeschützt

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


def system_is_dark():
    from Foundation import NSUserDefaults
    return NSUserDefaults.standardUserDefaults().stringForKey_("AppleInterfaceStyle") == "Dark"


def accept_opened_files(transcribe, window):
    """Gibt Dateien aus „Öffnen mit“ und vom Dock-Symbol an den Server weiter.

    pywebview bietet dafür nichts an; sein App-Delegate bekommt deshalb eine Unterklasse, die
    macOS' application:openURLs: annimmt. Sie muss vor webview.start() eingesetzt sein, weil
    pywebview den Delegate beim Anlegen des Fensters erzeugt.
    """
    from webview.platforms.cocoa import BrowserView

    def tell_page():
        try:
            window.run_js("window.dispatchEvent(new Event('transcribe:opened'))")
        except Exception:
            pass  # Seite noch nicht geladen: Sie holt die Dateien beim Start selbst ab

    class TranscribeAppDelegate(BrowserView.AppDelegate):
        def application_openURLs_(self, app, urls):
            transcribe.register_opened_files([url.path() for url in urls if url.isFileURL()])
            # run_js wartet auf den Haupt-Thread, auf dem dieser Aufruf gerade läuft
            threading.Thread(target=tell_page, daemon=True).start()

    BrowserView.AppDelegate = TranscribeAppDelegate


def make_notifier(transcribe):
    """Mitteilung von macOS für fertige Transkriptionen; dazu hüpft das Dock-Symbol einmal.

    Die Erlaubnis fragt macOS bei der ersten Mitteilung ab. Ohne sie bleibt das Hüpfen, das keine braucht.
    """
    import AppKit
    from PyObjCTools import AppHelper

    try:
        import UserNotifications as UN
        center = UN.UNUserNotificationCenter.currentNotificationCenter()
    except Exception as e:  # z.B. außerhalb eines App-Bundles
        print("  " + transcribe.tr("notify_failed", error=e))
        center = None

    def notify(title, body):
        AppHelper.callAfter(AppKit.NSApp.requestUserAttention_, AppKit.NSInformationalRequest)
        if center is None:
            return

        def post(granted, error):
            if not granted:
                if error:
                    print("  " + transcribe.tr("notify_failed", error=error))
                return
            content = UN.UNMutableNotificationContent.alloc().init()
            content.setTitle_(title)
            content.setBody_(body)
            content.setSound_(UN.UNNotificationSound.defaultSound())
            request = UN.UNNotificationRequest.requestWithIdentifier_content_trigger_(str(uuid.uuid4()), content, None)
            center.addNotificationRequest_withCompletionHandler_(request, None)

        center.requestAuthorizationWithOptions_completionHandler_(
            UN.UNAuthorizationOptionAlert | UN.UNAuthorizationOptionSound, post,
        )

    return notify


def main():
    redirect_output()
    activity = keep_full_speed()  # Referenz halten, solange die App läuft

    import webview
    import transcribe

    transcribe.load_engines()
    transcribe.migrate_legacy_names()
    # Fester Port, weil der Verlauf im localStorage am Origin hängt; nur wenn belegt ein anderer
    httpd = transcribe.create_server(transcribe.DEFAULT_PORT, interactive=False)
    url = f"http://{transcribe.HOST}:{httpd.server_address[1]}"
    print(f"Transcribe {transcribe.VERSION}: " + transcribe.tr("running_on", url=url))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    threading.Thread(target=transcribe._prune_jobs_forever, daemon=True).start()
    transcribe.notify_hook = make_notifier(transcribe)

    # Hintergrund wie die Seite (static/app.css), damit beim Öffnen nichts aufblitzt
    window = webview.create_window(
        "Transcribe", url, width=760, height=900, min_size=(520, 600),
        background_color="#0f0f0f" if system_is_dark() else "#f5f5f2",
    )
    accept_opened_files(transcribe, window)
    # private_mode=False, sonst löscht pywebview den localStorage (Einstellungen) bei jedem Start
    webview.start(private_mode=False)

    # Fenster geschlossen: App beenden. os._exit, damit kein Hintergrund-Thread einer Bibliothek
    # den Prozess ohne Fenster und ohne Server am Leben hält.
    httpd.shutdown()
    os._exit(0)


if __name__ == "__main__":
    # Muss als Erstes laufen: Hilfsprozesse von multiprocessing (z.B. der resource_tracker, den tqdm
    # anstößt) starten die App-Datei erneut. Ohne das würde jeder davon eine weitere App starten.
    import multiprocessing
    multiprocessing.freeze_support()
    main()
