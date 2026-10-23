# PyInstaller-Spec für Transcribe.app, aufgerufen von packaging/macos/build.sh
import re
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

ROOT = Path(SPECPATH).parents[1]
BUILD = ROOT / "build"
VERSION = re.search(r'^VERSION = "([^"]+)"', (ROOT / "transcribe.py").read_text(), re.M).group(1)

datas = [
    (str(ROOT / "static"), "static"),
    (str(ROOT / "LICENSE"), "."),
    (str(Path(SPECPATH) / "THIRD_PARTY_NOTICES.md"), "."),
]
# Eigenes Audio-FFmpeg aus build_ffmpeg.sh, macos_app.py legt den Ordner in den PATH
binaries = [(str(BUILD / "ffmpeg" / "bin" / name), "bin") for name in ("ffmpeg", "ffprobe")]
# transcribe.py lädt die Engine per importlib, das sieht PyInstaller nicht von selbst
hiddenimports = ["transcribe", "mlx_whisper"]

# mlx braucht seine Metal-Shader (mlx.metallib) neben libmlx.dylib
mlx_datas, mlx_binaries, mlx_hidden = collect_all("mlx")
datas += mlx_datas + collect_data_files("mlx_whisper")  # Tokenizer und Mel-Filter
binaries += mlx_binaries
hiddenimports += mlx_hidden

a = Analysis(
    [str(ROOT / "macos_app.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    # openai-whisper und torch gehören nicht in die App
    excludes=["torch", "whisper", "tkinter", "matplotlib", "IPython", "pytest"],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Transcribe",
    console=False,
    target_arch="arm64",
)

coll = COLLECT(exe, a.binaries, a.datas, name="Transcribe")

app = BUNDLE(
    coll,
    name="Transcribe.app",
    icon=str(BUILD / "icon.icns"),
    bundle_identifier="io.github.sven-lyco.transcribe",
    version=VERSION,
    info_plist={
        "CFBundleDisplayName": "Transcribe",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSMinimumSystemVersion": "14.0",
        "LSApplicationCategoryType": "public.app-category.productivity",
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "MIT License",
        # Ohne das bremst macOS (App Nap) die Transkription, sobald das Fenster im Hintergrund ist
        "NSAppSleepDisabled": True,
        # Die Oberfläche kommt vom lokalen Server unter http://127.0.0.1
        "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
    },
)
