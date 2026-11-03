"""
logger.py — Logging condiviso dell'app.

Scrive su:
  - console (stderr)
  - un file di log ruotato accanto all'eseguibile/script

Il file di log serve a capire cosa è successo quando qualcosa "sembra bloccato"
o va in errore: contiene i tempi di ogni fase (caricamento modello, analisi,
trascrizione, traduzione) e l'eventuale traceback completo.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

_LOGGER_NAME = "video_subtitler"
_CONFIGURED = False


def _log_dir() -> str:
    """
    Cartella dove scrivere il log.
    - Da sorgente: la cartella del progetto.
    - Da eseguibile PyInstaller: la cartella che contiene l'.exe.
    """
    if getattr(sys, "frozen", False):  # bundle PyInstaller
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_logger() -> logging.Logger:
    """Ritorna il logger dell'app, configurandolo al primo uso."""
    global _CONFIGURED
    logger = logging.getLogger(_LOGGER_NAME)
    if _CONFIGURED:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    logger.addHandler(console)

    # File (rotazione a 1 MB, 3 backup)
    try:
        log_path = os.path.join(_log_dir(), "video_subtitler.log")
        fileh = RotatingFileHandler(
            log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        fileh.setLevel(logging.DEBUG)
        fileh.setFormatter(fmt)
        logger.addHandler(fileh)
        logger.debug("Logger inizializzato. File di log: %s", log_path)
    except Exception as exc:  # il file di log non deve mai bloccare l'app
        logger.warning("Impossibile aprire il file di log: %s", exc)

    _CONFIGURED = True
    return logger


def log_path() -> str:
    """Percorso del file di log (per mostrarlo all'utente)."""
    return os.path.join(_log_dir(), "video_subtitler.log")
