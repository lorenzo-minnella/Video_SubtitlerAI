"""
make_ico.py — Converte assets/icon/icon.svg in icon.ico (multi-risoluzione).

Usa cairosvg + Pillow se disponibili. Se cairosvg non è installato, prova a
cercare un PNG già pronto (icon.png) e lo converte in .ico. Non blocca la build
se l'icona non è generabile: in quel caso stampa un avviso.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = os.path.join(HERE, "..", "assets", "icon")
SVG = os.path.join(ICON_DIR, "icon.svg")
PNG = os.path.join(ICON_DIR, "icon.png")
ICO = os.path.join(ICON_DIR, "icon.ico")

SIZES = [16, 24, 32, 48, 64, 128, 256]


def _svg_to_png() -> bool:
    try:
        import cairosvg  # type: ignore
    except ImportError:
        return False
    cairosvg.svg2png(url=SVG, write_to=PNG, output_width=512, output_height=512)
    return True


def main() -> int:
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        print("⚠️  Pillow non installato: salto la generazione dell'icona.")
        print("    (pip install pillow cairosvg per abilitarla)")
        return 0

    if not os.path.isfile(PNG):
        if os.path.isfile(SVG) and _svg_to_png():
            print(f"PNG generato da SVG: {PNG}")
        else:
            print("⚠️  Nessun icon.png e cairosvg non disponibile: "
                  "salto l'icona .ico.")
            print("    (pip install cairosvg, oppure metti un icon.png in assets/icon/)")
            return 0

    img = Image.open(PNG).convert("RGBA")
    img.save(ICO, format="ICO", sizes=[(s, s) for s in SIZES])
    print(f"✅  Icona generata: {ICO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
