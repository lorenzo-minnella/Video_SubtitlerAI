"""
settings.py — Impostazioni persistenti dell'app.

Salva le preferenze dell'utente (ultimo modello, lingua, cartella output, tema,
formati, ecc.) in un file JSON nella cartella di configurazione dell'utente,
così vengono ricordate tra un avvio e l'altro.
"""

from __future__ import annotations

import json
import os
import sys

try:
    from .logger import get_logger
except ImportError:
    from logger import get_logger

log = get_logger()

APP_DIR_NAME = "VideoSubtitlerAI"

DEFAULTS = {
    "language": "auto",
    "model": "small",
    "translate": "none",
    "speed": "Qualità",
    "formats": ["srt"],      # uno o più tra srt/vtt/txt
    "output_dir": "",          # "" = accanto al video
    "theme": "dark",          # dark | light
    "burn": False,             # masterizza sottotitoli nel video
    "wrap_lines": True,        # spezzatura righe intelligente
    "hard_audio": False,       # modalità audio difficile (voci deboli/lontane)
}


def _config_path() -> str:
    """Percorso del file di configurazione, per OS."""
    if os.name == "nt":  # Windows
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    elif sys.platform == "darwin":  # macOS
        base = os.path.expanduser("~/Library/Application Support")
    else:  # Linux
        base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    d = os.path.join(base, APP_DIR_NAME)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "settings.json")


def load_settings() -> dict:
    """Carica le impostazioni, completando i campi mancanti coi default."""
    path = _config_path()
    data = dict(DEFAULTS)
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as fh:
                saved = json.load(fh)
            if isinstance(saved, dict):
                data.update({k: saved[k] for k in saved if k in DEFAULTS})
    except Exception as exc:
        log.warning("Impossibile leggere le impostazioni (%s): uso i default.", exc)

    # Validazione: 'formats' deve essere una lista non vuota di formati validi.
    valid_fmt = {"srt", "vtt", "txt"}
    fmts = [f for f in data.get("formats", []) if f in valid_fmt]
    data["formats"] = fmts or ["srt"]
    # 'theme' deve essere uno dei valori ammessi.
    if data.get("theme") not in ("dark", "light"):
        data["theme"] = "dark"
    return data


def save_settings(settings: dict) -> None:
    """Salva le impostazioni su file (silenzioso in caso di errore)."""
    path = _config_path()
    try:
        clean = {k: settings.get(k, DEFAULTS[k]) for k in DEFAULTS}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(clean, fh, indent=2)
        log.debug("Impostazioni salvate in %s", path)
    except Exception as exc:
        log.warning("Impossibile salvare le impostazioni: %s", exc)
