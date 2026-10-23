"""Erzeugt das App-Icon (Mikrofon in Akzentgelb auf dunklem, abgerundetem Quadrat) als .icns.

Aufruf: python make_icon.py <ziel.icns>   (braucht numpy und das macOS-Tool iconutil)
"""

import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

import numpy as np

SIZE = 1024
SUPERSAMPLE = 3  # Kantenglättung
BG = np.array([0x0f, 0x0f, 0x0f], float)
FG = np.array([0xe8, 0xff, 0x5a], float)

# macOS-Icon-Raster: Fläche 824 px mit 100 px Rand, Eckenradius ca. 185 px
BOX, MARGIN, RADIUS = 824, 100, 185


def seg_dist(x, y, ax, ay, bx, by):
    """Abstand zur Strecke a–b."""
    px, py, dx, dy = x - ax, y - ay, bx - ax, by - ay
    t = np.clip((px * dx + py * dy) / (dx * dx + dy * dy), 0, 1)
    return np.hypot(px - t * dx, py - t * dy)


def render():
    n = SIZE * SUPERSAMPLE
    c = (np.arange(n) + 0.5) / SUPERSAMPLE
    x, y = np.meshgrid(c, c)

    # Abgerundetes Quadrat
    half = BOX / 2
    qx = np.abs(x - SIZE / 2) - (half - RADIUS)
    qy = np.abs(y - SIZE / 2) - (half - RADIUS)
    outside = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0)
    shape = outside <= RADIUS

    # Mikrofon, entworfen in einem 512er-Raster und auf die Fläche skaliert
    u = (x - MARGIN) * 512 / BOX
    v = (y - MARGIN) * 512 / BOX
    capsule = seg_dist(u, v, 256, 164, 256, 248) <= 56
    arc = (np.abs(np.hypot(u - 256, v - 240) - 106) <= 13) & (v >= 240)
    arc_ends = (np.hypot(u - 150, v - 240) <= 13) | (np.hypot(u - 362, v - 240) <= 13)
    stem = seg_dist(u, v, 256, 346, 256, 404) <= 13
    base = seg_dist(u, v, 196, 404, 316, 404) <= 13
    mic = capsule | arc | arc_ends | stem | base

    def downsample(mask):
        return mask.astype(np.float32).reshape(SIZE, SUPERSAMPLE, SIZE, SUPERSAMPLE).mean(axis=(1, 3))

    alpha, glyph = downsample(shape), downsample(mic & shape)
    rgb = BG * (1 - glyph[..., None]) + FG * glyph[..., None]
    return np.dstack([rgb, alpha[..., None] * 255])


def write_png(path, rgba):
    img = np.round(rgba).astype(np.uint8)
    h, w = img.shape[:2]
    raw = b"".join(b"\x00" + row.tobytes() for row in img)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    Path(path).write_bytes(png)


def main():
    target = Path(sys.argv[1])
    full = render()
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "icon.iconset"
        iconset.mkdir()
        for base in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                px = base * scale
                f = SIZE // px
                img = full.reshape(px, f, px, f, 4).mean(axis=(1, 3))
                suffix = "@2x" if scale == 2 else ""
                write_png(iconset / f"icon_{base}x{base}{suffix}.png", img)
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(target)], check=True)
    print(f"Icon geschrieben: {target}")


if __name__ == "__main__":
    main()
