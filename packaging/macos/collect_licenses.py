"""Sammelt die Lizenztexte aller Bestandteile der Mac-App, damit sie im App-Bundle mitkommen.

Aufruf: python collect_licenses.py <FFmpeg-Ordner> <Zielordner>   (mit dem Python der Build-venv)

Ergebnis: <Zielordner>/<Bestandteil>/<Lizenzdateien>, z.B. FFmpeg/COPYING.LGPLv2.1 oder numpy/LICENSE.txt
"""

import re
import shutil
import sys
import sysconfig
from importlib.metadata import distributions
from pathlib import Path

# Lizenzdateien direkt im .dist-info-Ordner; alles unter .dist-info/licenses/ zählt ohnehin dazu
LICENSE_NAME = re.compile(r"(LICEN[CS]E|COPYING|NOTICE|AUTHORS)", re.I)
# Lizenztexte aus den Quell-Repositories für Pakete, deren Wheel keinen mitbringt: licenses/<Paketname>/
FALLBACK_DIR = Path(__file__).parent / "licenses"


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def main():
    ffmpeg_dir, target = Path(sys.argv[1]), Path(sys.argv[2])
    shutil.rmtree(target, ignore_errors=True)

    # Ohne diese beiden darf die App nicht weitergegeben werden
    required = {
        "Python": [Path(sysconfig.get_path("stdlib")) / "LICENSE.txt"],
        "FFmpeg": [ffmpeg_dir / "COPYING.LGPLv2.1", ffmpeg_dir / "LICENSE.md"],
    }
    for name, files in required.items():
        for file in files:
            if not file.is_file():
                sys.exit(f"Lizenztext fehlt: {file}")
            copy(file, target / name / file.name)

    without_license = []
    for dist in distributions():
        name = dist.metadata["Name"]
        found = False
        for file in dist.files or []:
            parts = file.parts
            if len(parts) < 2 or not parts[0].endswith(".dist-info"):
                continue
            if parts[1] == "licenses" and len(parts) > 2:
                rel = Path(*parts[2:])
            elif len(parts) == 2 and LICENSE_NAME.match(file.name):
                rel = Path(file.name)
            else:
                continue
            copy(file.locate(), target / name / rel)
            found = True
        if not found and (FALLBACK_DIR / name).is_dir():
            shutil.copytree(FALLBACK_DIR / name, target / name)
        elif not found:
            without_license.append(name)

    if without_license:
        sys.exit(
            f"Ohne Lizenztext: {', '.join(sorted(without_license))}\n"
            f"Den Lizenztext aus dem Quell-Repository nach {FALLBACK_DIR}/<Paketname>/ legen."
        )
    print(f"Lizenztexte gesammelt: {target}")


if __name__ == "__main__":
    main()
