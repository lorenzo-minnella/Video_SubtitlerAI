"""
cli.py — Generazione sottotitoli da riga di comando.

Esempi:
    python cli.py video.mp4
    python cli.py video.mp4 --language en --model medium --format vtt
    python cli.py video.mp4 --translate it --format srt vtt txt   # orig + tradotto, multi
    python cli.py *.mp4 --model small --fast
    python cli.py video.mp4 --burn                                 # hardsub (serve ffmpeg)
"""

from __future__ import annotations

import argparse
import os
import sys

import core.subtitle_engine as eng
from core.subtitle_engine import (
    AVAILABLE_MODELS, TranscriptionResult, SubtitleEngine,
    translate_segments, write_subtitles, burn_subtitles, has_ffmpeg,
)
from core.logger import get_logger

log = get_logger()


def _progress(frac: float, msg: str):
    bar_len = 28
    filled = int(bar_len * frac)
    bar = "█" * filled + "░" * (bar_len - filled)
    print(f"\r[{bar}] {frac * 100:5.1f}%  {msg[:48]:<48}", end="", flush=True)
    if frac >= 1.0:
        print()


def _write(res, out_dir, base, lang, formats, wrap):
    produced = []
    for fmt in formats:
        p = os.path.join(out_dir, f"{base}.{lang}.{fmt}")
        if fmt == "srt":
            content = eng.segments_to_srt(res.segments, wrap=wrap)
        elif fmt == "vtt":
            content = eng.segments_to_vtt(res.segments, wrap=wrap)
        else:
            content = eng.segments_to_text(res.segments)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(content)
        produced.append(p)
    return produced


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Genera sottotitoli (.srt/.vtt/.txt) da video/audio con faster-whisper.")
    parser.add_argument("inputs", nargs="+", help="File video/audio da elaborare.")
    parser.add_argument("-l", "--language", default="auto",
                        help="Lingua audio: auto, en, it, es, fr, de, pt (default: auto)")
    parser.add_argument("-m", "--model", default="small",
                        choices=list(AVAILABLE_MODELS.keys()),
                        help="Modello Whisper (default: small)")
    parser.add_argument("-f", "--format", nargs="+", default=["srt"],
                        choices=["srt", "vtt", "txt"],
                        help="Uno o più formati di output (default: srt)")
    parser.add_argument("-t", "--translate", default="none",
                        help="Traduci anche in questa lingua (salva orig + tradotto).")
    parser.add_argument("--fast", action="store_true",
                        help="Modalità rapida (beam=1).")
    parser.add_argument("--hard-audio", action="store_true",
                        help="Audio difficile: pre-amplifica e usa VAD sensibile "
                             "(voci deboli/lontane/sussurrate).")
    parser.add_argument("--no-wrap", action="store_true",
                        help="Disabilita la spezzatura righe intelligente.")
    parser.add_argument("--burn", action="store_true",
                        help="Masterizza i sottotitoli nel video (richiede ffmpeg).")
    parser.add_argument("-d", "--output-dir", default=None,
                        help="Cartella di output (default: accanto a ogni file).")
    args = parser.parse_args(argv)

    wrap = not args.no_wrap
    engine = SubtitleEngine(model_size=args.model)

    for media in args.inputs:
        if not os.path.isfile(media):
            print(f"⚠️  File non trovato: {media}", file=sys.stderr)
            continue
        print(f"\n🎬  {os.path.basename(media)}")
        res = engine.transcribe(media, language=args.language, task="transcribe",
                                fast=args.fast, hard_audio=args.hard_audio,
                                progress=_progress)
        print(f"   Lingua rilevata: {res.language} "
              f"(confidenza {res.language_probability:.0%}) · {len(res.segments)} segmenti")

        out_dir = args.output_dir or os.path.dirname(media)
        base = os.path.splitext(os.path.basename(media))[0]

        for p in _write(res, out_dir, base, res.language, args.format, wrap):
            print(f"   ✅  {p}")

        if args.translate not in ("none", "") and args.translate != res.language:
            print(f"   Traduco in '{args.translate}'...")
            tr = TranscriptionResult(
                language=args.translate, language_probability=1.0, duration=res.duration,
                segments=translate_segments(res.segments, res.language,
                                            args.translate, _progress))
            for p in _write(tr, out_dir, base, args.translate, args.format, wrap):
                print(f"   ✅  {p}")

        if args.burn:
            if not has_ffmpeg():
                print("   ⚠️  ffmpeg non trovato: salto l'hardsub.", file=sys.stderr)
            else:
                srt_path = os.path.join(out_dir, f"{base}.{res.language}.srt")
                if not os.path.isfile(srt_path):
                    write_subtitles(res, srt_path, fmt="srt")
                out_video = os.path.join(out_dir, f"{base}.sub.mp4")
                burn_subtitles(media, srt_path, out_video, progress=_progress)
                print(f"   ✅  {out_video}")


if __name__ == "__main__":
    main()
