"""
Video SubtitlerAI — Interfaccia grafica
=======================================
Desktop app (Windows / macOS / Linux) per generare sottotitoli da un video
usando faster-whisper in locale. Interfaccia scura e pulita basata su
CustomTkinter.

Avvio:
    python app_gui.py
"""

from __future__ import annotations

import os
import sys
import threading
import traceback

import customtkinter as ctk
from tkinter import filedialog, messagebox

# Import del motore. Supporta sia esecuzione da sorgente che da bundle PyInstaller.
try:
    from core.subtitle_engine import (
        AVAILABLE_MODELS,
        SUPPORTED_LANGUAGES,
        TRANSLATION_TARGETS,
        SubtitleEngine,
        translate_segments,
        write_subtitles,
    )
    from core.logger import get_logger, log_path
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from core.subtitle_engine import (
        AVAILABLE_MODELS,
        SUPPORTED_LANGUAGES,
        TRANSLATION_TARGETS,
        SubtitleEngine,
        translate_segments,
        write_subtitles,
    )
    from core.logger import get_logger, log_path

log = get_logger()

# Drag & drop opzionale (tkinterdnd2). Se assente, si usa solo il pulsante "Sfoglia".
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _HAS_DND = True
except Exception:
    _HAS_DND = False

APP_NAME = "Video SubtitlerAI"
APP_VERSION = "1.1"


def _fmt_elapsed(seconds: float) -> str:
    """Tempo trascorso leggibile, es. '45s' o '2m 30s'."""
    seconds = max(0, int(round(seconds)))
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    return f"{minutes}m {secs:02d}s"

VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v",
              ".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg")

# Colori brand
BRAND = "#6C5CE7"       # viola
BRAND_HOVER = "#5a4bd4"
BG_CARD = "#1b1b24"


class SubtitlerApp:
    def __init__(self, root):
        self.root = root
        self.engine: SubtitleEngine | None = None
        self.worker: threading.Thread | None = None
        self.cancel_requested = False
        self.selected_file: str | None = None

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        root.title(f"{APP_NAME} {APP_VERSION}")
        root.geometry("640x680")
        root.minsize(560, 620)

        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        pad = 16

        header = ctk.CTkLabel(
            self.root, text="🎬  Video SubtitlerAI",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        header.pack(pady=(pad + 4, 2))

        subtitle = ctk.CTkLabel(
            self.root,
            text="Genera sottotitoli (.srt / .vtt) dai tuoi video — locale e gratuito",
            font=ctk.CTkFont(size=12), text_color="#9aa0b5",
        )
        subtitle.pack(pady=(0, pad))

        # --- Drop zone / selezione file ---
        self.drop_frame = ctk.CTkFrame(self.root, fg_color=BG_CARD, corner_radius=14)
        self.drop_frame.pack(fill="x", padx=pad, pady=(0, pad))

        self.drop_label = ctk.CTkLabel(
            self.drop_frame,
            text="Trascina qui un video\noppure usa «Sfoglia»"
            if _HAS_DND else "Seleziona un video con «Sfoglia»",
            font=ctk.CTkFont(size=14), text_color="#c7ccdb", justify="center",
        )
        self.drop_label.pack(pady=(22, 8), padx=16)

        browse_btn = ctk.CTkButton(
            self.drop_frame, text="📁  Sfoglia...", command=self._browse,
            fg_color=BRAND, hover_color=BRAND_HOVER, width=160,
        )
        browse_btn.pack(pady=(0, 20))

        if _HAS_DND:
            self.drop_frame.drop_target_register(DND_FILES)
            self.drop_frame.dnd_bind("<<Drop>>", self._on_drop)

        # --- Opzioni ---
        opts = ctk.CTkFrame(self.root, fg_color=BG_CARD, corner_radius=14)
        opts.pack(fill="x", padx=pad, pady=(0, pad))
        opts.grid_columnconfigure(1, weight=1)

        # Lingua sorgente
        ctk.CTkLabel(opts, text="Lingua audio").grid(
            row=0, column=0, sticky="w", padx=14, pady=(14, 6))
        self.lang_var = ctk.StringVar(value=SUPPORTED_LANGUAGES["auto"])
        self.lang_menu = ctk.CTkOptionMenu(
            opts, values=list(SUPPORTED_LANGUAGES.values()),
            variable=self.lang_var, fg_color=BRAND, button_color=BRAND,
            button_hover_color=BRAND_HOVER,
        )
        self.lang_menu.grid(row=0, column=1, sticky="ew", padx=14, pady=(14, 6))

        # Modello
        ctk.CTkLabel(opts, text="Qualità (modello)").grid(
            row=1, column=0, sticky="w", padx=14, pady=6)
        self.model_var = ctk.StringVar(value="small")
        self.model_menu = ctk.CTkOptionMenu(
            opts, values=list(AVAILABLE_MODELS.keys()),
            variable=self.model_var, fg_color=BRAND, button_color=BRAND,
            button_hover_color=BRAND_HOVER,
        )
        self.model_menu.grid(row=1, column=1, sticky="ew", padx=14, pady=6)

        # Traduzione
        ctk.CTkLabel(opts, text="Traduci in").grid(
            row=2, column=0, sticky="w", padx=14, pady=6)
        self.translate_var = ctk.StringVar(value=TRANSLATION_TARGETS["none"])
        self.translate_menu = ctk.CTkOptionMenu(
            opts, values=list(TRANSLATION_TARGETS.values()),
            variable=self.translate_var, fg_color=BRAND, button_color=BRAND,
            button_hover_color=BRAND_HOVER,
        )
        self.translate_menu.grid(row=2, column=1, sticky="ew", padx=14, pady=6)

        # Formato output
        ctk.CTkLabel(opts, text="Formato file").grid(
            row=3, column=0, sticky="w", padx=14, pady=(6, 14))
        self.fmt_var = ctk.StringVar(value="srt")
        self.fmt_menu = ctk.CTkSegmentedButton(
            opts, values=["srt", "vtt"], variable=self.fmt_var,
            selected_color=BRAND, selected_hover_color=BRAND_HOVER,
        )
        self.fmt_menu.grid(row=3, column=1, sticky="w", padx=14, pady=(6, 14))

        # --- Azione ---
        self.run_btn = ctk.CTkButton(
            self.root, text="✨  Genera sottotitoli", command=self._start,
            fg_color=BRAND, hover_color=BRAND_HOVER, height=44,
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        self.run_btn.pack(fill="x", padx=pad, pady=(0, 8))

        # --- Progress ---
        self.progress = ctk.CTkProgressBar(self.root)
        self.progress.set(0)
        self.progress.pack(fill="x", padx=pad, pady=(4, 2))

        self.status = ctk.CTkLabel(
            self.root, text="Pronto.", font=ctk.CTkFont(size=12),
            text_color="#9aa0b5",
        )
        self.status.pack(pady=(0, pad))

    # ------------------------------------------------------------- Eventi
    def _browse(self):
        path = filedialog.askopenfilename(
            title="Seleziona un video o audio",
            filetypes=[("Media", " ".join(f"*{e}" for e in VIDEO_EXTS)),
                       ("Tutti i file", "*.*")],
        )
        if path:
            self._set_file(path)

    def _on_drop(self, event):
        raw = event.data.strip()
        # tkinterdnd2 racchiude i path con spazi tra parentesi graffe
        if raw.startswith("{") and raw.endswith("}"):
            raw = raw[1:-1]
        self._set_file(raw.split("} {")[0])

    def _set_file(self, path: str):
        if not os.path.isfile(path):
            messagebox.showerror(APP_NAME, "File non valido.")
            return
        self.selected_file = path
        self.drop_label.configure(text=f"✅  {os.path.basename(path)}")
        self.status.configure(text="File pronto. Premi «Genera sottotitoli».")

    def _label_to_code(self, mapping: dict, label: str) -> str:
        for code, lbl in mapping.items():
            if lbl == label:
                return code
        return label

    # ---------------------------------------------------------- Pipeline
    def _start(self):
        if self.worker and self.worker.is_alive():
            # In corso -> il pulsante funge da annulla
            self.cancel_requested = True
            self.status.configure(text="Annullamento in corso...")
            return
        if not self.selected_file:
            messagebox.showwarning(APP_NAME, "Seleziona prima un file video.")
            return

        self.cancel_requested = False
        self.run_btn.configure(text="⏹  Annulla", fg_color="#b23b3b",
                               hover_color="#953232")
        self.progress.set(0)
        # Stato per il "battito" di avanzamento.
        import time as _time
        self._start_ts = _time.monotonic()
        self._have_real_progress = False
        self._running = True
        self._tick()  # avvia l'aggiornamento periodico del tempo trascorso
        self.worker = threading.Thread(target=self._run_pipeline, daemon=True)
        self.worker.start()

    def _tick(self):
        """
        Aggiornamento periodico (ogni secondo) indipendente dal motore.
        Serve a mostrare che l'app è viva durante le fasi lunghe senza segmenti
        (caricamento modello e analisi VAD iniziale), prima che arrivi una
        percentuale reale di avanzamento.
        """
        if not getattr(self, "_running", False):
            return
        import time as _time
        elapsed = _time.monotonic() - self._start_ts
        if not self._have_real_progress:
            # Barra "indeterminata": pulsa avanti e indietro per segnalare attività.
            phase = (elapsed % 4) / 4.0
            pulse = phase if phase <= 0.5 else (1.0 - phase)
            self.progress.set(0.05 + pulse * 0.1)
            self.status.configure(
                text=f"Preparazione... · trascorso {_fmt_elapsed(elapsed)} "
                     f"(il primo avvio carica il modello, può richiedere qualche minuto)")
        self.root.after(1000, self._tick)

    def _run_pipeline(self):
        try:
            src_lang = self._label_to_code(SUPPORTED_LANGUAGES, self.lang_var.get())
            target = self._label_to_code(TRANSLATION_TARGETS, self.translate_var.get())
            model_size = self.model_var.get()
            fmt = self.fmt_var.get()
            media = self.selected_file

            if self.engine is None or self.engine.model_size != model_size:
                self.engine = SubtitleEngine(model_size=model_size)

            def prog(frac, msg):
                self.root.after(0, lambda: self._update_progress(frac, msg))

            result = self.engine.transcribe(
                media, language=src_lang, task="transcribe",
                progress=prog, cancel_check=lambda: self.cancel_requested,
            )

            # Traduzione opzionale
            if target not in ("none", "") and target != result.language:
                self.root.after(0, lambda: self._update_progress(
                    0.0, "Preparo la traduzione..."))
                result.segments = translate_segments(
                    result.segments, source_lang=result.language,
                    target_lang=target, progress=prog,
                )
                lang_suffix = target
            else:
                lang_suffix = result.language

            base, _ = os.path.splitext(media)
            out_path = f"{base}.{lang_suffix}.{fmt}"
            write_subtitles(result, out_path, fmt=fmt)

            self.root.after(0, lambda: self._done(out_path, len(result.segments)))

        except InterruptedError:
            self.root.after(0, self._cancelled)
        except Exception as exc:  # noqa: BLE001
            tb = traceback.format_exc()
            self.root.after(0, lambda: self._error(str(exc), tb))

    def _update_progress(self, frac: float, msg: str):
        # Il primo aggiornamento con frazione reale (>2%) disattiva il battito.
        if frac > 0.02:
            self._have_real_progress = True
        self.progress.set(max(0.0, min(1.0, frac)))
        self.status.configure(text=msg)

    def _reset_button(self):
        self.run_btn.configure(text="✨  Genera sottotitoli", fg_color=BRAND,
                               hover_color=BRAND_HOVER)

    def _done(self, out_path: str, n_segments: int):
        self._running = False
        self.progress.set(1.0)
        self.status.configure(
            text=f"✅ Fatto: {n_segments} sottotitoli → {os.path.basename(out_path)}")
        self._reset_button()
        messagebox.showinfo(
            APP_NAME,
            f"Sottotitoli generati!\n\n{out_path}\n\nSegmenti: {n_segments}")

    def _cancelled(self):
        self._running = False
        self.progress.set(0)
        self.status.configure(text="Operazione annullata.")
        self._reset_button()

    def _error(self, msg: str, tb: str):
        self._running = False
        self.progress.set(0)
        self.status.configure(text="Errore durante l'elaborazione.")
        self._reset_button()
        log.error("Errore durante l'elaborazione:\n%s", tb)
        messagebox.showerror(
            APP_NAME,
            f"Si è verificato un errore:\n\n{msg}\n\n"
            f"Dettagli completi nel file di log:\n{log_path()}")


def main():
    log.info("Avvio %s %s (drag&drop=%s)", APP_NAME, APP_VERSION, _HAS_DND)
    if _HAS_DND:
        root = TkinterDnD.Tk()
        # CustomTkinter applica il tema anche su una root TkinterDnD
        ctk.set_appearance_mode("dark")
    else:
        root = ctk.CTk()
    SubtitlerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
