"""Tests für transcribe.py, nur mit der Standardbibliothek und ohne Whisper.

Aufruf im Projektordner: python3 -m unittest discover -s tests
"""

import argparse
import http.client
import importlib.util
import io
import json
import re
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import transcribe

ROOT = Path(__file__).resolve().parents[1]


def word(text, start, end):
    return {"word": text, "start": start, "end": end}


class PassagesTest(unittest.TestCase):
    def test_splits_after_sentence_end(self):
        result = {"segments": [
            {"words": [word(" Hallo", 0, 0.5), word(" Welt.", 0.5, 1), word(" Wie", 1.2, 1.5)]},
            {"words": [word(" geht's?", 1.5, 2)]},
        ]}
        self.assertEqual(transcribe._passages(result), [[0, 1, "Hallo Welt."], [1.2, 2, "Wie geht's?"]])

    def test_splits_long_sentence_at_comma(self):
        result = {"segments": [{"words": [word(" eins,", 0, 3), word(" zwei,", 3, 9), word(" drei.", 9, 10)]}]}
        self.assertEqual(transcribe._passages(result), [[0, 9, "eins, zwei,"], [9, 10, "drei."]])

    def test_splits_without_punctuation_after_max_length(self):
        result = {"segments": [{"words": [word(" a", 0, 5), word(" b", 5, 10), word(" c", 10, 16), word(" d", 16, 17)]}]}
        self.assertEqual(transcribe._passages(result), [[0, 16, "a b c"], [16, 17, "d"]])

    def test_keeps_segment_without_word_timestamps(self):
        result = {"segments": [
            {"words": [word(" Erst", 0, 1)]},
            {"start": 1, "end": 3, "text": " ohne Wortzeiten "},
            {"start": 3, "end": 4, "text": "  "},
        ]}
        self.assertEqual(transcribe._passages(result), [[0, 1, "Erst"], [1, 3, "ohne Wortzeiten"]])


class ParsePortTest(unittest.TestCase):
    def test_accepts_valid_port(self):
        self.assertEqual(transcribe.parse_port("9000"), 9000)

    def test_rejects_invalid_ports(self):
        for value in ("abc", "0", "65536", "6000"):  # 6000 blockieren Browser
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                transcribe.parse_port(value)


class DataDirTest(unittest.TestCase):
    def test_refuses_home_and_its_parents(self):
        home = Path.home()
        for folder in (home, home.parent, Path(home.anchor)):
            with self.subTest(folder=folder):
                self.assertFalse(transcribe._is_own_data_dir(folder))

    def test_accepts_folder_inside_home(self):
        self.assertTrue(transcribe._is_own_data_dir(Path.home() / "Library" / "Application Support" / "Transcribe"))

    def test_reset_deletes_nothing_in_home(self):
        with mock.patch.object(transcribe, "APP_DATA_DIR", Path.home()), \
                mock.patch.object(Path, "iterdir", side_effect=AssertionError("darf nichts löschen")), \
                mock.patch("builtins.print"):
            self.assertFalse(transcribe._reset_app_data())


class LanguageTest(unittest.TestCase):
    def test_language_from_environment(self):
        cases = {"de_DE.UTF-8": "de", "de_AT": "de", "en_US.UTF-8": "en", "fr_FR.UTF-8": "en"}
        for value, expected in cases.items():
            with self.subTest(value=value), mock.patch.dict("os.environ", {"TRANSCRIBE_LANG": value}):
                self.assertEqual(transcribe._system_language(), expected)

    def test_messages_exist_in_both_languages(self):
        for key, texts in transcribe.MESSAGES.items():
            with self.subTest(key=key):
                self.assertEqual(len(texts), 2)
                self.assertNotEqual(texts[0], texts[1])

    def test_tr_uses_ui_language(self):
        cases = {"de": "Port 6000 wird von Browsern blockiert", "en": "Browsers block port 6000"}
        for language, expected in cases.items():
            with self.subTest(language=language), mock.patch.object(transcribe, "UI_LANGUAGE", language):
                self.assertEqual(transcribe.tr("port_blocked", port=6000), expected)


class QueueTest(unittest.TestCase):
    def test_runs_jobs_in_upload_order(self):
        started, finished = [], threading.Event()

        def record(job_id):
            started.append(job_id)
            if len(started) == 3:
                finished.set()

        with mock.patch.object(transcribe, "_run_transcription", side_effect=record):
            for n in range(3):
                transcribe._enqueue((f"job{n}",))
            self.assertTrue(finished.wait(5))
        self.assertEqual(started, ["job0", "job1", "job2"])


@unittest.skipUnless(importlib.util.find_spec("tqdm"), "braucht tqdm (z.B. in .venv)")
class DownloadProgressTest(unittest.TestCase):
    def test_reports_bytes_of_the_reconstruct_bar(self):
        with mock.patch.dict(transcribe._jobs, clear=True):
            job_id = transcribe._create_job("a.ogg")
            progress = transcribe._download_progress_class(job_id)
            files = progress(total=2, file=io.StringIO())  # Balken über die Anzahl der Dateien: zählt nicht
            files.update(1)
            self.assertNotIn("download", transcribe._jobs[job_id])
            data = progress(total=0, unit="B", desc="Reconstructing (incomplete total...)", file=io.StringIO())
            data.total = 3000  # huggingface_hub setzt die Summe nachträglich
            data.update(1200)
            self.assertEqual(transcribe._jobs[job_id]["download"], {"done": 1200, "total": 3000})


class VersionTest(unittest.TestCase):
    def test_is_newer(self):
        cases = [("1.10.0", "1.9.0", True), ("1.2.0", "1.2.0", False), ("v2.0", "1.9.9", True), ("", "1.0.0", False)]
        for candidate, current, expected in cases:
            with self.subTest(candidate=candidate, current=current):
                self.assertEqual(transcribe._is_newer(candidate, current), expected)


class TextsTest(unittest.TestCase):
    def test_both_languages_have_the_same_keys(self):
        source = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        blocks = re.search(r"\n  de: \{\n(.*?)\n  \},\n  en: \{\n(.*?)\n  \},\n\};", source, re.S)
        de, en = ({m for m in re.findall(r"^    '?([\w-]+)'?:", block, re.M)} for block in blocks.groups())
        self.assertGreater(len(de), 50)
        self.assertEqual(de, en)


class MigrationTest(unittest.TestCase):
    """Daten von Version 1.1.0: Ordner „Transkripte“ und Verlauf „.verlauf.json“."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name)
        new = self.data / "Transcripts"
        patches = [
            mock.patch.object(transcribe, "APP_DATA_DIR", self.data),
            mock.patch.object(transcribe, "DEFAULT_OUTPUT_DIR", new),
            mock.patch.object(transcribe, "HISTORY_INDEX", new / ".history.json"),
            mock.patch.object(transcribe, "LEGACY_OUTPUT_DIR", self.data / "Transkripte"),
            mock.patch.object(transcribe, "LEGACY_HISTORY_INDEX", new / ".verlauf.json"),
            mock.patch("builtins.print"),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_moves_folder_and_index(self):
        old = self.data / "Transkripte"
        (old / ".audio").mkdir(parents=True)
        (old / "a.txt").write_text("Hallo", encoding="utf-8")
        (old / ".audio" / "abc.ogg").write_bytes(b"ogg")
        elsewhere = str(self.data / "anderswo" / "b.txt")
        index = {"abc": {"path": str(old / "a.txt"), "audio": "abc.ogg"}, "def": {"path": elsewhere}}
        (old / ".verlauf.json").write_text(json.dumps(index), encoding="utf-8")

        transcribe.migrate_legacy_names()

        new = self.data / "Transcripts"
        self.assertFalse(old.exists())
        self.assertEqual((new / "a.txt").read_text(encoding="utf-8"), "Hallo")
        self.assertTrue((new / ".audio" / "abc.ogg").is_file())
        self.assertFalse((new / ".verlauf.json").exists())
        migrated = json.loads((new / ".history.json").read_text(encoding="utf-8"))
        self.assertEqual(migrated["abc"]["path"], str(new / "a.txt"))
        self.assertEqual(migrated["def"]["path"], elsewhere)  # Ausgabeordner außerhalb bleiben

    def test_keeps_existing_new_data(self):
        old, new = self.data / "Transkripte", self.data / "Transcripts"
        old.mkdir()
        new.mkdir()
        (new / ".history.json").write_text("{}", encoding="utf-8")
        transcribe.migrate_legacy_names()
        self.assertTrue(old.exists())
        self.assertEqual((new / ".history.json").read_text(encoding="utf-8"), "{}")

    def test_without_old_data(self):
        transcribe.migrate_legacy_names()
        self.assertEqual(list(self.data.iterdir()), [])


class ServerTest(unittest.TestCase):
    """Echter Server auf einem freien Port; jeder Test beendet ihn wieder."""

    AUDIO = bytes(range(100))

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out = Path(tmp.name)
        self.audio_dir = self.out / ".audio"
        patches = [
            mock.patch.object(transcribe, "DEFAULT_OUTPUT_DIR", self.out),
            mock.patch.object(transcribe, "HISTORY_INDEX", self.out / ".history.json"),
            mock.patch.object(transcribe, "AUDIO_DIR", self.audio_dir),
            mock.patch.object(transcribe, "APP_DATA_DIR", None),
            mock.patch.dict(transcribe._engines, {"openai": object()}),  # Platzhalter, wird nie aufgerufen
            mock.patch.dict(transcribe._jobs, clear=True),
            mock.patch.dict(transcribe._opened, clear=True),
            mock.patch.object(transcribe, "_opened_new", []),
            mock.patch.object(transcribe, "notify_hook", None),
            mock.patch.object(transcribe, "_update_cache", None),
            mock.patch("builtins.print"),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        # Statt zu transkribieren nur festhalten, was in die Warteschlange käme
        self.enqueued = []
        enqueue = mock.patch.object(transcribe, "_enqueue", side_effect=self.enqueued.append)
        enqueue.start()
        self.addCleanup(enqueue.stop)
        self.addCleanup(lambda: [Path(args[3]).unlink(missing_ok=True) for args in self.enqueued])

        self.server = transcribe.Server((transcribe.HOST, 0), transcribe.Handler)
        self.port = self.server.server_address[1]
        thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        # Läuft in umgekehrter Reihenfolge: anhalten, auf den Thread warten, Socket schließen
        self.addCleanup(self.server.server_close)
        self.addCleanup(thread.join, 5)
        self.addCleanup(self.server.shutdown)

    def request(self, method, path, headers=None, body=None, host=None):
        conn = http.client.HTTPConnection(transcribe.HOST, self.port, timeout=5)
        try:
            conn.request(method, path, body=body, headers={"Host": host or f"127.0.0.1:{self.port}", **(headers or {})})
            response = conn.getresponse()
            return response.status, response, response.read()
        finally:
            conn.close()

    def add_transcript(self, transcript_id="abc", audio="abc.ogg"):
        txt = self.out / f"{transcript_id}.txt"
        txt.write_text("Hallo Welt.", encoding="utf-8")
        self.audio_dir.mkdir(exist_ok=True)
        (self.audio_dir / "abc.ogg").write_bytes(self.AUDIO)
        index = transcribe._load_history_index()
        index[transcript_id] = {"path": str(txt), "date": "2026-10-24T10:00:00+02:00", "audio": audio}
        transcribe._save_history_index(index)
        return txt

    # ---------- Nur Anfragen der eigenen Seite ----------

    def test_accepts_own_host_and_origin(self):
        for host in (f"127.0.0.1:{self.port}", f"localhost:{self.port}"):
            with self.subTest(host=host):
                status, _, body = self.request("GET", "/config", {"Origin": f"http://{host}"}, host=host)
                self.assertEqual(status, 200)
                config = json.loads(body)
                self.assertEqual(config["version"], transcribe.VERSION)
                self.assertIn(config["ui_language"], ("de", "en"))

    def test_rejects_foreign_host(self):
        # DNS-Rebinding: Eine fremde Domain zeigt auf 127.0.0.1
        status, _, _ = self.request("GET", "/transcripts", host=f"evil.example:{self.port}")
        self.assertEqual(status, 403)

    def test_rejects_foreign_origin(self):
        for method, path in (("GET", "/transcripts"), ("DELETE", "/transcripts?id=abc"), ("POST", "/transcribe")):
            with self.subTest(method=method):
                status, _, _ = self.request(method, path, {"Origin": "https://evil.example"})
                self.assertEqual(status, 403)

    def test_index_has_csp(self):
        status, response, _ = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("default-src 'self'", response.getheader("Content-Security-Policy"))
        self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")

    # ---------- Verlauf ----------

    def test_lists_and_deletes_transcript(self):
        txt = self.add_transcript()
        status, _, body = self.request("GET", "/transcripts")
        self.assertEqual(status, 200)
        [entry] = json.loads(body)
        self.assertEqual((entry["id"], entry["text"], entry["audio"]), ("abc", "Hallo Welt.", True))

        status, _, _ = self.request("DELETE", "/transcripts?id=abc")
        self.assertEqual(status, 204)
        self.assertFalse(txt.exists())
        self.assertFalse((self.audio_dir / "abc.ogg").exists())

    def test_deletes_only_files_in_output_dir(self):
        outside = self.out.parent / f"{self.out.name}-outside.txt"
        outside.write_text("bleibt", encoding="utf-8")
        self.addCleanup(outside.unlink, missing_ok=True)
        status, _, _ = self.request("DELETE", f"/transcripts?id=file:../{outside.name}")
        self.assertEqual(status, 404)
        self.assertTrue(outside.exists())

    # ---------- Audio ----------

    def test_audio_ranges(self):
        self.add_transcript()
        cases = [
            (None, 200, self.AUDIO, None),
            ("bytes=0-9", 206, self.AUDIO[:10], "bytes 0-9/100"),
            ("bytes=90-", 206, self.AUDIO[90:], "bytes 90-99/100"),
            ("bytes=-5", 206, self.AUDIO[-5:], "bytes 95-99/100"),
            ("bytes=95-500", 206, self.AUDIO[95:], "bytes 95-99/100"),
            ("bytes=9-2", 416, b"", "bytes */100"),
            ("bytes=100-", 416, b"", "bytes */100"),
            ("bytes=0-1,5-6", 416, b"", "bytes */100"),
        ]
        for range_header, expected_status, expected_body, content_range in cases:
            with self.subTest(range=range_header):
                headers = {"Range": range_header} if range_header else {}
                status, response, body = self.request("GET", "/audio?id=abc", headers)
                self.assertEqual(status, expected_status)
                self.assertEqual(body, expected_body)
                self.assertEqual(response.getheader("Content-Range"), content_range)
                if status == 200:
                    self.assertEqual(response.getheader("Content-Type"), "audio/ogg")

    def test_audio_only_from_audio_dir(self):
        self.add_transcript(audio="../abc.txt")
        status, _, _ = self.request("GET", "/audio?id=abc")
        self.assertEqual(status, 404)

    def test_audio_unknown_id(self):
        status, _, _ = self.request("GET", "/audio?id=gibtsnicht")
        self.assertEqual(status, 404)

    # ---------- Upload ----------

    def multipart(self, fields):
        boundary = "testgrenze"
        parts = []
        for name, value in fields.items():
            disposition = f'form-data; name="{name}"'
            if name == "file":
                disposition += '; filename="nachricht.ogg"'
            parts.append(f"--{boundary}\r\nContent-Disposition: {disposition}\r\n\r\n{value}\r\n")
        body = ("".join(parts) + f"--{boundary}--\r\n").encode()
        return {"Content-Type": f"multipart/form-data; boundary={boundary}"}, body

    def test_upload_rejects_invalid_fields(self):
        cases = [
            ({"engine": "openai"}, "no_file"),
            ({"file": "x", "engine": "gibtsnicht"}, "unknown_engine"),
            ({"file": "x", "model": "riesig"}, "unknown_model"),
            ({"file": "x", "language": "fr"}, "unknown_language"),
            ({"file": "x", "output_folder": str(self.out / "gibtsnicht")}, "folder_not_found"),
        ]
        for fields, error in cases:
            with self.subTest(fields=fields):
                headers, body = self.multipart(fields)
                status, _, response = self.request("POST", "/transcribe", headers, body)
                self.assertEqual(status, 400)
                self.assertEqual(json.loads(response)["error"], error)

    def test_upload_rejects_too_large_file(self):
        headers = {
            "Content-Type": "multipart/form-data; boundary=x",
            "Content-Length": str(transcribe.MAX_UPLOAD + 1),
        }
        status, _, body = self.request("POST", "/transcribe", headers, b"")
        self.assertEqual(status, 413)
        self.assertEqual(json.loads(body), {"error": "too_large", "detail": 2})

    def test_progress_of_unknown_job(self):
        status, _, body = self.request("GET", "/progress?job=gibtsnicht")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body.decode().removeprefix("data: ")), {"type": "error", "error": "job_gone"})

    def test_reset_only_in_app(self):
        status, _, _ = self.request("POST", "/reset")
        self.assertEqual(status, 404)

    def test_upload_goes_into_queue(self):
        headers, body = self.multipart({"file": "ogg-daten", "model": "tiny", "speaker_name": "Anna"})
        status, _, response = self.request("POST", "/transcribe", headers, body)
        self.assertEqual(status, 200)
        [(job_id, engine, model, tmp_path, language, speaker, _, file_name)] = self.enqueued
        self.assertEqual(json.loads(response)["job_id"], job_id)
        self.assertEqual((engine, model, language, speaker, file_name), ("openai", "tiny", "de", "Anna", "nachricht.ogg"))
        self.assertEqual(Path(tmp_path).read_bytes(), b"ogg-daten")

    # ---------- Fortschritt ----------

    def first_event(self, job_id):
        """Liest nur das erste Server-Sent Event; der Stream liefe sonst weiter, solange der Job wartet."""
        conn = http.client.HTTPConnection(transcribe.HOST, self.port, timeout=5)
        try:
            conn.request("GET", f"/progress?job={job_id}", headers={"Host": f"127.0.0.1:{self.port}"})
            response = conn.getresponse()
            return json.loads(response.readline().decode().removeprefix("data: "))
        finally:
            conn.close()

    def test_progress_shows_jobs_ahead(self):
        first, second, third = (transcribe._create_job(f"{n}.ogg") for n in "abc")
        transcribe._jobs[first]["state"] = "running"
        self.assertEqual(self.first_event(third)["ahead"], 2)
        self.assertEqual(self.first_event(second)["ahead"], 1)
        self.assertNotIn("ahead", self.first_event(first))

    def test_progress_shows_download(self):
        job_id = transcribe._create_job("a.ogg")
        transcribe._report_download(job_id, 512, 2048)
        event = self.first_event(job_id)
        self.assertEqual((event["state"], event["download"]), ("downloading", {"done": 512, "total": 2048}))

    # ---------- Bearbeiten ----------

    def put_text(self, transcript_id, text, headers=None):
        body = json.dumps({"text": text}).encode()
        return self.request("PUT", f"/transcripts?id={transcript_id}", {"Content-Type": "application/json", **(headers or {})}, body)[0]

    def test_edit_saves_text(self):
        txt = self.add_transcript()
        self.assertEqual(self.put_text("abc", "Hallo, Welt!"), 204)
        self.assertEqual(txt.read_text(encoding="utf-8"), "Hallo, Welt!")
        (self.out / "alt.txt").write_text("alt", encoding="utf-8")
        self.assertEqual(self.put_text("file:alt.txt", "neu"), 204)
        self.assertEqual((self.out / "alt.txt").read_text(encoding="utf-8"), "neu")

    def test_edit_rejects_invalid_requests(self):
        self.add_transcript()
        self.assertEqual(self.put_text("file:../abc.txt", "x"), 404)
        self.assertEqual(self.put_text("gibtsnicht", "x"), 404)
        self.assertEqual(self.put_text("abc", "x", {"Origin": "https://evil.example"}), 403)
        status, _, _ = self.request("PUT", "/transcripts?id=abc", {"Content-Type": "application/json"}, b"[1, 2]")
        self.assertEqual(status, 400)
        status, _, _ = self.request("PUT", "/transcripts?id=abc", {"Content-Length": str(transcribe.MAX_TEXT + 1)}, b"")
        self.assertEqual(status, 413)
        self.assertEqual((self.out / "abc.txt").read_text(encoding="utf-8"), "Hallo Welt.")

    # ---------- Geöffnete Dateien (Mac-App) ----------

    def test_opened_files_are_listed_once(self):
        audio = self.out / "Sprachnachricht.opus"
        audio.write_bytes(b"opus-daten")
        transcribe.register_opened_files([str(audio), str(self.out / "gibtsnicht.ogg")])
        status, _, body = self.request("GET", "/opened")
        [item] = json.loads(body)
        self.assertEqual((status, item["name"], item["size"]), (200, "Sprachnachricht.opus", 10))
        self.assertEqual(json.loads(self.request("GET", "/opened")[2]), [])

        headers, body = self.multipart({"opened": item["id"]})
        status, _, _ = self.request("POST", "/transcribe", headers, body)
        self.assertEqual(status, 200)
        [args] = self.enqueued
        self.assertEqual(args[7], "Sprachnachricht.opus")
        self.assertTrue(args[3].endswith(".opus"))
        self.assertEqual(Path(args[3]).read_bytes(), b"opus-daten")
        self.assertNotIn(item["id"], transcribe._opened)  # nur einmal verwendbar

    def test_unknown_opened_file(self):
        headers, body = self.multipart({"opened": "gibtsnicht"})
        status, _, response = self.request("POST", "/transcribe", headers, body)
        self.assertEqual((status, json.loads(response)["error"]), (400, "opened_gone"))
        self.assertEqual(self.enqueued, [])

    # ---------- Mitteilung (Mac-App) ----------

    def test_notify_without_app(self):
        status, _, _ = self.request("POST", "/notify", {"Content-Type": "application/json"}, b'{"title": "x"}')
        self.assertEqual(status, 404)

    def test_notify_calls_hook(self):
        hook = mock.Mock()
        with mock.patch.object(transcribe, "notify_hook", hook):
            self.assertTrue(json.loads(self.request("GET", "/config")[2])["notify"])
            body = json.dumps({"title": "Fertig", "body": "x" * 1000}).encode()
            status, _, _ = self.request("POST", "/notify", {"Content-Type": "application/json"}, body)
            hook.side_effect = RuntimeError("keine Erlaubnis")
            status_after_error, _, _ = self.request("POST", "/notify", {"Content-Type": "application/json"}, body)
        self.assertEqual((status, status_after_error), (204, 204))
        hook.assert_called_with("Fertig", "x" * 500)

    # ---------- Update-Hinweis (Mac-App) ----------

    def github_answer(self, tag, url):
        return io.BytesIO(json.dumps({"tag_name": tag, "html_url": url}).encode())

    def test_update_only_in_app(self):
        status, _, _ = self.request("GET", "/update")
        self.assertEqual(status, 404)

    def test_update_reports_newer_version(self):
        release_url = transcribe.RELEASES_URL + "tag/v9.0.0"
        with mock.patch.object(transcribe, "APP_DATA_DIR", self.out), \
                mock.patch("urllib.request.urlopen", return_value=self.github_answer("v9.0.0", release_url)) as urlopen:
            status, _, body = self.request("GET", "/update")
            self.request("GET", "/update")  # zweite Anfrage aus dem Zwischenspeicher
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"latest": "9.0.0", "url": release_url, "newer": True})
        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(urlopen.call_args.args[0].full_url, transcribe.UPDATE_API)

    def test_update_keeps_only_own_release_links(self):
        with mock.patch.object(transcribe, "APP_DATA_DIR", self.out), \
                mock.patch("urllib.request.urlopen", return_value=self.github_answer(transcribe.VERSION, "https://evil.example/")):
            answer = json.loads(self.request("GET", "/update")[2])
        self.assertEqual(answer, {"latest": transcribe.VERSION, "url": transcribe.RELEASES_URL + "latest", "newer": False})

    def test_update_offline(self):
        with mock.patch.object(transcribe, "APP_DATA_DIR", self.out), \
                mock.patch("urllib.request.urlopen", side_effect=OSError("offline")):
            status, _, body = self.request("GET", "/update")
        self.assertEqual((status, json.loads(body)["error"]), (502, "update_failed"))


if __name__ == "__main__":
    unittest.main()
