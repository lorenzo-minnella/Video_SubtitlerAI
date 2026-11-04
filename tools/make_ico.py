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
    """Prova a rasterizzare la SVG con cairosvg (spesso assente su Windows)."""
    try:
        import cairosvg  # type: ignore
    except Exception:
        return False
    try:
        cairosvg.svg2png(url=SVG, write_to=PNG, output_width=512, output_height=512)
        return True
    except Exception:
        return False


def _draw_png_fallback(size: int = 512) -> bool:
    """
    Disegna l'icona direttamente con Pillow, senza cairosvg.
    Riproduce il tema della SVG: gradiente viola + schermo video con play
    + due barre di sottotitoli. Serve a garantire un'icona anche su Windows.
    """
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return False

    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Gradiente verticale viola (#6C5CE7 -> #3A2FA0)
    top = (0x6C, 0x5C, 0xE7)
    bot = (0x3A, 0x2F, 0xA0)
    for y in range(s):
        t = y / (s - 1)
        r = int(top[0] + (bot[0] - top[0]) * t)
        g = int(top[1] + (bot[1] - top[1]) * t)
        b = int(top[2] + (bot[2] - top[2]) * t)
        d.line([(0, y), (s, y)], fill=(r, g, b, 255))

    # Angoli arrotondati: maschera
    radius = int(s * 0.22)
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s, s], radius=radius, fill=255)
    img.putalpha(mask)

    # Disegno schermo + play su un layer separato, così l'alpha si fonde
    # correttamente col gradiente (niente bianco pieno che "mangia" il play).
    overlay = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)

    # Schermo video: riquadro velato con bordo bianco marcato
    sx0, sy0, sx1, sy1 = int(s*0.19), int(s*0.25), int(s*0.81), int(s*0.64)
    od.rounded_rectangle([sx0, sy0, sx1, sy1], radius=int(s*0.05),
                         fill=(255, 255, 255, 40),
                         outline=(255, 255, 255, 230), width=max(3, int(s*0.016)))
    # Play pieno e opaco, ben visibile sul velo
    cx, cy, h = int(s*0.49), int(s*0.445), int(s*0.085)
    od.polygon([(cx - h, cy - h), (cx + int(h*1.1), cy), (cx - h, cy + h)],
               fill=(255, 255, 255, 255))

    img = Image.alpha_composite(img, overlay)
    d = ImageDraw.Draw(img)
    # Barre sottotitoli (opache)
    d.rounded_rectangle([int(s*0.29), int(s*0.70), int(s*0.71), int(s*0.745)],
                        radius=int(s*0.022), fill=(255, 255, 255, 255))
    d.rounded_rectangle([int(s*0.35), int(s*0.775), int(s*0.65), int(s*0.82)],
                        radius=int(s*0.022), fill=(255, 255, 255, 185))

    img.save(PNG)
    return True


def main() -> int:
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        print("⚠️  Pillow non installato: salto la generazione dell'icona.")
        print("    (pip install pillow per abilitarla)")
        return 0

    if not os.path.isfile(PNG):
        if os.path.isfile(SVG) and _svg_to_png():
            print(f"PNG generato da SVG (cairosvg): {PNG}")
        elif _draw_png_fallback():
            print(f"PNG generato con Pillow (fallback): {PNG}")
        else:
            print("⚠️  Impossibile generare un PNG per l'icona: salto icon.ico.")
            return 0

    img = Image.open(PNG).convert("RGBA")
    img.save(ICO, format="ICO", sizes=[(s, s) for s in SIZES])
    print(f"✅  Icona generata: {ICO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
