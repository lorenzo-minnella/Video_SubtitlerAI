"""
cli.py — Generazione sottotitoli da riga di comando.

Esempi:
    python cli.py video.mp4
    python cli.py video.mp4 --language en --model medium --format vtt
    python cli.py video.mp4 --translate it          # trascrivi + traduci in italiano
    python cli.py *.mp4 --model small
"""

from __future__ import annotations

import argparse
import os
import sys

from core.subtitle_engine import (
    AVAILABLE_MODELS,
    SubtitleEngine,
    translate_segments,
    write_subtitles,
)
from core.logger import get_logger, log_path

log = get_logger()


def _progress(frac: float, msg: str):
    bar_len = 28
    filled = int(bar_len * frac)
    bar = "█" * filled + "░" * (bar_len - filled)
    print(f"\r[{bar}] {frac * 100:5.1f}%  {msg[:40]:<40}", end="", flush=True)
    if frac >= 1.0:
        print()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Genera sottotitoli (.srt/.vtt) da video/audio con faster-whisper.")
    parser.add_argument("inputs", nargs="+", help="File video/audio da elaborare.")
    parser.add_argument("-l", "--language", default="auto",
                        help="Lingua audio: auto, en, it, ... (default: auto)")
    parser.add_argument("-m", "--model", default="small",
                        choices=list(AVAILABLE_MODELS.keys()),
                        help="Modello Whisper (default: small)")
    parser.add_argument("-f", "--format", default="srt", choices=["srt", "vtt"],
                        help="Formato di output (default: srt)")
    parser.add_argument("-t", "--translate", default="none",
                        help="Traduci i sottotitoli in questa lingua (es. it, en). "
                             "Default: nessuna traduzione.")
    parser.add_argument("-o", "--output", default=None,
                        help="Path di output (solo con un singolo input).")
    args = parser.parse_args(argv)

    if args.output and len(args.inputs) > 1:
        parser.error("--output è ammesso solo con un singolo file di input.")

    engine = SubtitleEngine(model_size=args.model)

    for media in args.inputs:
        if not os.path.isfile(media):
            print(f"⚠️  File non trovato: {media}", file=sys.stderr)
            continue
        print(f"\n🎬  {os.path.basename(media)}")
        result = engine.transcribe(media, language=args.language,
                                   task="transcribe", progress=_progress)
        print(f"   Lingua rilevata: {result.language} "
              f"(confidenza {result.language_probability:.0%})")

        lang_suffix = result.language
        if args.translate not in ("none", "") and args.translate != result.language:
            print(f"   Traduco in '{args.translate}'...")
            result.segments = translate_segments(
                result.segments, source_lang=result.language,
                target_lang=args.translate, progress=_progress)
            lang_suffix = args.translate

        if args.output:
            out_path = args.output
        else:
            base, _ = os.path.splitext(media)
            out_path = f"{base}.{lang_suffix}.{args.format}"
        write_subtitles(result, out_path, fmt=args.format)
        print(f"   ✅  Salvato: {out_path}  ({len(result.segments)} segmenti)")


if __name__ == "__main__":
    main()
