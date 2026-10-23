"""Regenerate fonts/ from a Source A4 one-pager saved as HTML with its assets embedded.

fonts/ already holds the final files, so this is only needed if the brand files change.

Usage: python3 extract_assets.py <source-one-pager.html> [out_dir]

Writes, into out_dir (default: fonts/ next to this script):
  source-400.ttf      the embedded Source typeface, weight 400
  source-600.ttf      the embedded Source typeface, weight 600
  source-wordmark.*   the Source wordmark from the page header (original format kept)

Only these three assets are taken. Any other image in the file (logos of other firms,
illustrations) is never extracted.
Python 3 standard library only. Running it twice gives byte-identical files.
"""

import base64
import hashlib
import pathlib
import re
import sys

FONT_FACE = re.compile(r"@font-face\s*\{([^}]*)\}", re.S)
FONT_SRC = re.compile(r"url\(\s*['\"]?data:font/(?:ttf|truetype|sfnt);base64,([A-Za-z0-9+/=]+)")
FONT_WEIGHT = re.compile(r"font-weight\s*:\s*(\d+)")
HEADER_IMG = re.compile(
    r"<header\b[^>]*>.*?<img\b[^>]*\bsrc=\"data:image/(png|jpeg|gif|webp|svg\+xml);base64,([A-Za-z0-9+/=]+)\"",
    re.S,
)
EXT = {"png": "png", "jpeg": "jpg", "gif": "gif", "webp": "webp", "svg+xml": "svg"}


def write(path, data):
    path.write_bytes(data)
    print(f"{path.name:<22} {len(data):>7} bytes  sha256 {hashlib.sha256(data).hexdigest()[:16]}")


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    html = pathlib.Path(argv[1]).read_text(encoding="utf-8")
    out = pathlib.Path(argv[2]) if len(argv) > 2 else pathlib.Path(__file__).resolve().parent / "fonts"
    out.mkdir(parents=True, exist_ok=True)

    found = {}
    for block in FONT_FACE.findall(html):
        if "Source" not in block:
            continue
        weight, src = FONT_WEIGHT.search(block), FONT_SRC.search(block)
        if weight and src:
            found[weight.group(1)] = base64.b64decode(src.group(1))
    for weight in ("400", "600"):
        data = found.get(weight)
        if not data or data[:4] not in (b"\x00\x01\x00\x00", b"true"):
            sys.exit(f"no TrueType Source font with font-weight {weight} in {argv[1]}")
        write(out / f"source-{weight}.ttf", data)

    logo = HEADER_IMG.search(html)
    if not logo:
        sys.exit(f"no wordmark image inside <header> in {argv[1]}")
    for old in out.glob("source-wordmark.*"):
        old.unlink()
    write(out / f"source-wordmark.{EXT[logo.group(1)]}", base64.b64decode(logo.group(2)))


if __name__ == "__main__":
    main(sys.argv)
