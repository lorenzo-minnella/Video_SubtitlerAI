"""
Video SubtitlerAI — Interfaccia grafica (pro)
=============================================
Desktop app (Windows / macOS / Linux) per generare sottotitoli da uno o più
video usando faster-whisper in locale.

Funzioni:
  - Coda multi-file (batch) con drag & drop
  - Rilevamento lingua automatico o manuale (EN/IT/ES/FR/DE/PT)
  - Traduzione offline: salva SEMPRE sia l'originale sia il tradotto
  - Formati multipli SRT / VTT / TXT in un colpo
  - Spezzatura righe intelligente + word-level timestamp
  - Anteprima e MODIFICA dei segmenti prima del salvataggio
  - Masterizzazione (hardsub) dei sottotitoli nel video (se ffmpeg presente)
  - Preset velocità (Qualità / Veloce)
  - Impostazioni persistenti, tema chiaro/scuro
  - Barra avanzamento con tempo trascorso/ETA, "Apri cartella", log diagnostico

Avvio:
    python app_gui.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import traceback

import customtkinter as ctk
from tkinter import filedialog, messagebox

try:
    from core.subtitle_engine import (
        AVAILABLE_MODELS, SUPPORTED_LANGUAGES, TRANSLATION_TARGETS,
        SubtitleEngine, TranscriptionResult, Segment,
        translate_segments, write_subtitles, write_subtitles_multi,
        burn_subtitles, has_ffmpeg,
    )
    from core.logger import get_logger, log_path
    from core.settings import load_settings, save_settings
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from core.subtitle_engine import (
        AVAILABLE_MODELS, SUPPORTED_LANGUAGES, TRANSLATION_TARGETS,
        SubtitleEngine, TranscriptionResult, Segment,
        translate_segments, write_subtitles, write_subtitles_multi,
        burn_subtitles, has_ffmpeg,
    )
    from core.logger import get_logger, log_path
    from core.settings import load_settings, save_settings

log = get_logger()

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _HAS_DND = True
except Exception:
    _HAS_DND = False

APP_NAME = "Video SubtitlerAI"
APP_VERSION = "3.2"

VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v",
              ".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg")

BRAND = "#6C5CE7"
BRAND_HOVER = "#5a4bd4"
BG_CARD = "#1b1b24"
BG_CARD2 = "#232330"
TXT_DIM = "#9aa0b5"
DANGER = "#b23b3b"


def _fmt_elapsed(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    return f"{m}m {s:02d}s"


def _open_in_file_manager(path: str) -> None:
    folder = path if os.path.isdir(path) else os.path.dirname(path)
    try:
        if sys.platform.startswith("win"):
            os.startfile(folder)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", folder], check=False)
        else:
            subprocess.run(["xdg-open", folder], check=False)
    except Exception as exc:
        log.warning("Impossibile aprire la cartella %s: %s", folder, exc)


def _notify(title: str, message: str) -> None:
    """Notifica di sistema a fine elaborazione (best effort, non blocca)."""
    try:
        if sys.platform == "darwin":
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{message}" with title "{title}"'],
                check=False)
        elif sys.platform.startswith("win"):
            # Toast via PowerShell (best effort)
            ps = (f'[void][Windows.UI.Notifications.ToastNotificationManager];'
                  f'Write-Host "{message}"')
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False)
        else:
            subprocess.run(["notify-send", title, message], check=False)
    except Exception:
        pass


class SubtitlerApp:
    def __init__(self, root):
        self.root = root
        self.engine: SubtitleEngine | None = None
        self.worker: threading.Thread | None = None
        self.cancel_requested = False

        self.files: list[str] = []
        self.cfg = load_settings()
        self.output_dir: str | None = self.cfg.get("output_dir") or None
        self.last_output_dir: str | None = None
        # risultati trascritti per l'anteprima/modifica: media_path -> TranscriptionResult
        self.results: dict[str, TranscriptionResult] = {}

        ctk.set_appearance_mode(self.cfg.get("theme", "dark"))
        ctk.set_default_color_theme("dark-blue")

        root.title(f"{APP_NAME} {APP_VERSION}")
        root.geometry("760x820")
        root.minsize(700, 760)

        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        pad = 16
        top = ctk.CTkFrame(self.root, fg_color="transparent")
        top.pack(fill="x", padx=pad, pady=(pad, 0))
        ctk.CTkLabel(top, text="🎬  Video SubtitlerAI",
                     font=ctk.CTkFont(size=26, weight="bold")).pack(side="left")
        self.theme_btn = ctk.CTkButton(
            top, text="☀︎" if self.cfg.get("theme") == "dark" else "☾",
            width=40, command=self._toggle_theme,
            fg_color=BG_CARD2, hover_color="#33333f")
        self.theme_btn.pack(side="right")

        ctk.CTkLabel(
            self.root,
            text="Sottotitoli SRT/VTT/TXT da video — AI locale, gratuito, con traduzione",
            font=ctk.CTkFont(size=12), text_color=TXT_DIM,
        ).pack(pady=(0, pad))

        # --- Coda file ---
        fc = ctk.CTkFrame(self.root, fg_color=BG_CARD, corner_radius=14)
        fc.pack(fill="x", padx=pad, pady=(0, pad))
        row = ctk.CTkFrame(fc, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(row, text="File da elaborare",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        ctk.CTkButton(row, text="＋ Aggiungi", width=110, command=self._browse,
                      fg_color=BRAND, hover_color=BRAND_HOVER).pack(side="right")
        ctk.CTkButton(row, text="Cartella…", width=90, command=self._browse_dir,
                      fg_color=BG_CARD2, hover_color="#33333f").pack(side="right", padx=(0, 8))
        ctk.CTkButton(row, text="Svuota", width=80, command=self._clear_files,
                      fg_color=BG_CARD2, hover_color="#33333f").pack(side="right", padx=(0, 8))

        self.files_box = ctk.CTkTextbox(fc, height=90, fg_color=BG_CARD2, corner_radius=10)
        self.files_box.pack(fill="x", padx=14, pady=(0, 12))
        self.files_box.configure(state="disabled")
        self._refresh_files_box()
        if _HAS_DND:
            for w in (self.files_box, fc):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._on_drop)

        # --- Opzioni ---
        opts = ctk.CTkFrame(self.root, fg_color=BG_CARD, corner_radius=14)
        opts.pack(fill="x", padx=pad, pady=(0, pad))
        opts.grid_columnconfigure(1, weight=1)
        opts.grid_columnconfigure(3, weight=1)

        def lbl(t, r, c=0):
            ctk.CTkLabel(opts, text=t).grid(row=r, column=c, sticky="w", padx=14, pady=7)

        lbl("Lingua audio", 0)
        self.lang_var = ctk.StringVar(
            value=SUPPORTED_LANGUAGES.get(self.cfg["language"], SUPPORTED_LANGUAGES["auto"]))
        ctk.CTkOptionMenu(opts, values=list(SUPPORTED_LANGUAGES.values()),
                          variable=self.lang_var, fg_color=BRAND, button_color=BRAND,
                          button_hover_color=BRAND_HOVER).grid(row=0, column=1, sticky="ew", padx=14, pady=7)
        lbl("Traduci in", 0, 2)
        self.translate_var = ctk.StringVar(
            value=TRANSLATION_TARGETS.get(self.cfg["translate"], TRANSLATION_TARGETS["none"]))
        ctk.CTkOptionMenu(opts, values=list(TRANSLATION_TARGETS.values()),
                          variable=self.translate_var, fg_color=BRAND, button_color=BRAND,
                          button_hover_color=BRAND_HOVER).grid(row=0, column=3, sticky="ew", padx=14, pady=7)

        lbl("Qualità (modello)", 1)
        self.model_var = ctk.StringVar(value=self.cfg["model"])
        ctk.CTkOptionMenu(opts, values=list(AVAILABLE_MODELS.keys()),
                          variable=self.model_var, fg_color=BRAND, button_color=BRAND,
                          button_hover_color=BRAND_HOVER).grid(row=1, column=1, sticky="ew", padx=14, pady=7)
        lbl("Velocità", 1, 2)
        self.speed_var = ctk.StringVar(value=self.cfg["speed"])
        ctk.CTkSegmentedButton(opts, values=["Qualità", "Veloce"], variable=self.speed_var,
                               selected_color=BRAND, selected_hover_color=BRAND_HOVER
                               ).grid(row=1, column=3, sticky="w", padx=14, pady=7)

        # Formati (checkbox multipli)
        lbl("Formati", 2)
        fmt_row = ctk.CTkFrame(opts, fg_color="transparent")
        fmt_row.grid(row=2, column=1, sticky="w", padx=14, pady=7)
        self.fmt_vars = {}
        for f in ("srt", "vtt", "txt"):
            v = ctk.BooleanVar(value=f in self.cfg["formats"])
            ctk.CTkCheckBox(fmt_row, text=f.upper(), variable=v, width=60,
                            fg_color=BRAND, hover_color=BRAND_HOVER).pack(side="left", padx=(0, 10))
            self.fmt_vars[f] = v

        lbl("Cartella output", 2, 2)
        out_row = ctk.CTkFrame(opts, fg_color="transparent")
        out_row.grid(row=2, column=3, sticky="ew", padx=14, pady=7)
        self.out_label = ctk.CTkLabel(
            out_row, text=os.path.basename(self.output_dir) if self.output_dir else "Accanto al video",
            text_color=TXT_DIM, anchor="w")
        self.out_label.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(out_row, text="Scegli", width=70, command=self._choose_out_dir,
                      fg_color=BG_CARD2, hover_color="#33333f").pack(side="right")

        # Opzioni extra: wrap, burn, anteprima
        extra = ctk.CTkFrame(opts, fg_color="transparent")
        extra.grid(row=3, column=0, columnspan=4, sticky="w", padx=14, pady=(2, 10))
        self.wrap_var = ctk.BooleanVar(value=self.cfg.get("wrap_lines", True))
        ctk.CTkCheckBox(extra, text="Spezzatura righe intelligente", variable=self.wrap_var,
                        fg_color=BRAND, hover_color=BRAND_HOVER).pack(side="left", padx=(0, 16))
        self.burn_var = ctk.BooleanVar(value=self.cfg.get("burn", False))
        burn_cb = ctk.CTkCheckBox(extra, text="Masterizza nel video (hardsub)",
                                  variable=self.burn_var, fg_color=BRAND, hover_color=BRAND_HOVER)
        burn_cb.pack(side="left", padx=(0, 16))
        if not has_ffmpeg():
            burn_cb.configure(state="disabled", text="Hardsub (richiede ffmpeg)")
        self.preview_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(extra, text="Anteprima/modifica prima di salvare",
                        variable=self.preview_var, fg_color=BRAND,
                        hover_color=BRAND_HOVER).pack(side="left")

        # Riga dedicata: audio difficile (voci deboli/lontane/sussurrate)
        extra2 = ctk.CTkFrame(opts, fg_color="transparent")
        extra2.grid(row=4, column=0, columnspan=4, sticky="w", padx=14, pady=(0, 10))
        self.hard_var = ctk.BooleanVar(value=self.cfg.get("hard_audio", False))
        ctk.CTkCheckBox(extra2, text="🎚️  Audio difficile (voci deboli/lontane/sussurrate)",
                        variable=self.hard_var, fg_color=BRAND,
                        hover_color=BRAND_HOVER).pack(side="left")
        ctk.CTkLabel(extra2, text="— pre-amplifica l'audio e usa un rilevamento voce "
                     "più sensibile. Consigliato il modello «large-v3».",
                     font=ctk.CTkFont(size=11), text_color=TXT_DIM).pack(side="left", padx=(10, 0))

        # --- Azione ---
        self.run_btn = ctk.CTkButton(
            self.root, text="✨  Genera sottotitoli", command=self._start,
            fg_color=BRAND, hover_color=BRAND_HOVER, height=46,
            font=ctk.CTkFont(size=16, weight="bold"))
        self.run_btn.pack(fill="x", padx=pad, pady=(0, 8))

        self.progress = ctk.CTkProgressBar(self.root)
        self.progress.set(0)
        self.progress.pack(fill="x", padx=pad, pady=(4, 2))
        self.status = ctk.CTkLabel(self.root, text="Pronto.",
                                   font=ctk.CTkFont(size=12), text_color=TXT_DIM)
        self.status.pack(pady=(0, 4))
        self.open_btn = ctk.CTkButton(
            self.root, text="📂  Apri cartella output", command=self._open_output,
            fg_color=BG_CARD2, hover_color="#33333f", height=34)

    # ------------------------------------------------------------- Impostazioni
    def _collect_settings(self) -> dict:
        return {
            "language": self._label_to_code(SUPPORTED_LANGUAGES, self.lang_var.get()),
            "model": self.model_var.get(),
            "translate": self._label_to_code(TRANSLATION_TARGETS, self.translate_var.get()),
            "speed": self.speed_var.get(),
            "formats": [f for f, v in self.fmt_vars.items() if v.get()] or ["srt"],
            "output_dir": self.output_dir or "",
            "theme": ctk.get_appearance_mode().lower(),
            "burn": self.burn_var.get(),
            "wrap_lines": self.wrap_var.get(),
            "hard_audio": self.hard_var.get(),
        }

    def _persist(self):
        save_settings(self._collect_settings())

    def _toggle_theme(self):
        new = "light" if ctk.get_appearance_mode().lower() == "dark" else "dark"
        ctk.set_appearance_mode(new)
        self.theme_btn.configure(text="☀︎" if new == "dark" else "☾")
        self._persist()

    # ------------------------------------------------------------- File list
    def _refresh_files_box(self):
        self.files_box.configure(state="normal")
        self.files_box.delete("1.0", "end")
        if not self.files:
            ph = ("Trascina qui i video\noppure usa «＋ Aggiungi» / «Cartella…»"
                  if _HAS_DND else "Usa «＋ Aggiungi» o «Cartella…»")
            self.files_box.insert("1.0", ph)
        else:
            for i, f in enumerate(self.files, 1):
                self.files_box.insert("end", f"{i}.  {os.path.basename(f)}\n")
        self.files_box.configure(state="disabled")

    def _add_files(self, paths):
        added = 0
        for p in paths:
            p = p.strip().strip("{}")
            if os.path.isdir(p):
                for root, _, names in os.walk(p):
                    for n in names:
                        if n.lower().endswith(VIDEO_EXTS):
                            fp = os.path.join(root, n)
                            if fp not in self.files:
                                self.files.append(fp); added += 1
            elif os.path.isfile(p) and p not in self.files:
                self.files.append(p); added += 1
        if added:
            self._refresh_files_box()
            self.status.configure(text=f"{len(self.files)} file in coda.")

    def _browse(self):
        paths = filedialog.askopenfilenames(
            title="Seleziona uno o più video/audio",
            filetypes=[("Media", " ".join(f"*{e}" for e in VIDEO_EXTS)),
                       ("Tutti i file", "*.*")])
        if paths:
            self._add_files(list(paths))

    def _browse_dir(self):
        d = filedialog.askdirectory(title="Scegli una cartella di video")
        if d:
            self._add_files([d])

    def _on_drop(self, event):
        import re
        paths = re.findall(r"\{[^}]*\}|\S+", event.data.strip())
        self._add_files(paths)

    def _clear_files(self):
        self.files = []
        self.results.clear()
        self._refresh_files_box()
        self.status.configure(text="Coda svuotata.")

    def _choose_out_dir(self):
        d = filedialog.askdirectory(title="Scegli la cartella di output")
        self.output_dir = d or None
        self.out_label.configure(text=os.path.basename(d) if d else "Accanto al video")
        self._persist()

    def _open_output(self):
        if self.last_output_dir:
            _open_in_file_manager(self.last_output_dir)

    def _label_to_code(self, mapping, label):
        for code, lbl in mapping.items():
            if lbl == label:
                return code
        return label

    # ---------------------------------------------------------- Pipeline
    def _start(self):
        if self.worker and self.worker.is_alive():
            self.cancel_requested = True
            self.status.configure(text="Annullamento in corso...")
            return
        if not self.files:
            messagebox.showwarning(APP_NAME, "Aggiungi almeno un file video.")
            return
        self._persist()
        self.cancel_requested = False
        self.run_btn.configure(text="⏹  Annulla", fg_color=DANGER, hover_color="#953232")
        self.open_btn.pack_forget()
        self.progress.set(0)
        import time as _t
        self._start_ts = _t.monotonic()
        self._have_real = False
        self._running = True
        self._tick()
        self.worker = threading.Thread(target=self._run_pipeline, daemon=True)
        self.worker.start()

    def _tick(self):
        if not getattr(self, "_running", False):
            return
        import time as _t
        el = _t.monotonic() - self._start_ts
        if not self._have_real:
            ph = (el % 4) / 4.0
            pulse = ph if ph <= 0.5 else (1.0 - ph)
            self.progress.set(0.05 + pulse * 0.1)
            self.status.configure(
                text=f"Preparazione... · trascorso {_fmt_elapsed(el)} "
                     f"(il primo avvio carica il modello, può richiedere qualche minuto)")
        self.root.after(1000, self._tick)

    def _run_pipeline(self):
        try:
            cfg = self._collect_settings()
            src_lang = cfg["language"]
            target = cfg["translate"]
            model_size = cfg["model"]
            formats = cfg["formats"]
            fast = cfg["speed"] == "Veloce"
            wrap = cfg["wrap_lines"]
            burn = cfg["burn"]
            hard = cfg["hard_audio"]
            preview = self.preview_var.get()
            files = list(self.files)

            if self.engine is None or self.engine.model_size != model_size:
                self.engine = SubtitleEngine(model_size=model_size)

            def prog(frac, msg):
                self.root.after(0, lambda: self._update_progress(frac, msg))

            # Fase 1: trascrizione di tutti i file
            total = len(files)
            self.results.clear()
            for i, media in enumerate(files, 1):
                if self.cancel_requested:
                    raise InterruptedError()
                pfx = f"[{i}/{total}] " if total > 1 else ""
                self.root.after(0, lambda m=media, p=pfx: self._update_progress(
                    0.0, f"{p}Avvio: {os.path.basename(m)}"))
                res = self.engine.transcribe(
                    media, language=src_lang, task="transcribe", fast=fast,
                    hard_audio=hard,
                    progress=lambda fr, ms, p=pfx: prog(fr, p + ms),
                    cancel_check=lambda: self.cancel_requested)
                self.results[media] = res

            # Fase 2: anteprima/modifica (se richiesta) — sul thread UI
            if preview:
                self.root.after(0, self._open_preview_then_save,
                                files, target, formats, wrap, burn)
            else:
                produced = self._save_all(files, target, formats, wrap, burn, prog)
                self.root.after(0, lambda: self._done(produced))

        except InterruptedError:
            self.root.after(0, self._cancelled)
        except Exception as exc:  # noqa: BLE001
            tb = traceback.format_exc()
            self.root.after(0, lambda: self._error(str(exc), tb))

    def _save_all(self, files, target, formats, wrap, burn, prog) -> list[str]:
        """Scrive originale + tradotto in tutti i formati, più hardsub opzionale."""
        import core.subtitle_engine as eng
        produced: list[str] = []
        # applica la preferenza wrap globalmente
        eng_wrap = wrap
        for media in files:
            res = self.results[media]
            out_dir = self.output_dir or os.path.dirname(media)
            base = os.path.splitext(os.path.basename(media))[0]
            self.last_output_dir = out_dir

            # Originale
            produced += self._write_formats(res, out_dir, base, res.language, formats, eng_wrap)
            # Tradotto
            if target not in ("none", "") and target != res.language:
                prog(0.0, f"Traduco in '{target}'...")
                tr = TranscriptionResult(
                    language=target, language_probability=1.0, duration=res.duration,
                    segments=translate_segments(res.segments, res.language, target, prog))
                produced += self._write_formats(tr, out_dir, base, target, formats, eng_wrap)
            # Hardsub (usa l'SRT nella lingua originale se presente, altrimenti lo crea)
            if burn:
                srt_path = os.path.join(out_dir, f"{base}.{res.language}.srt")
                if not os.path.isfile(srt_path):
                    write_subtitles(res, srt_path, fmt="srt")
                out_video = os.path.join(out_dir, f"{base}.sub.mp4")
                try:
                    burn_subtitles(media, srt_path, out_video, progress=prog)
                    produced.append(out_video)
                except Exception as exc:
                    log.error("Hardsub fallito per %s: %s", media, exc)
        return produced

    def _write_formats(self, res, out_dir, base, lang, formats, wrap) -> list[str]:
        import core.subtitle_engine as eng
        paths = []
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
            paths.append(p)
        return paths

    def _open_preview_then_save(self, files, target, formats, wrap, burn):
        """Mostra l'editor dei segmenti del primo file, poi salva tutto."""
        media = files[0]
        res = self.results[media]
        PreviewEditor(self.root, res, on_confirm=lambda: self._after_preview(
            files, target, formats, wrap, burn))

    def _after_preview(self, files, target, formats, wrap, burn):
        def prog(frac, msg):
            self.root.after(0, lambda: self._update_progress(frac, msg))
        def worker():
            try:
                produced = self._save_all(files, target, formats, wrap, burn, prog)
                self.root.after(0, lambda: self._done(produced))
            except Exception as exc:  # noqa: BLE001
                tb = traceback.format_exc()
                self.root.after(0, lambda: self._error(str(exc), tb))
        threading.Thread(target=worker, daemon=True).start()

    def _update_progress(self, frac, msg):
        if frac > 0.02:
            self._have_real = True
        self.progress.set(max(0.0, min(1.0, frac)))
        self.status.configure(text=msg)

    def _reset_button(self):
        self.run_btn.configure(text="✨  Genera sottotitoli", fg_color=BRAND,
                               hover_color=BRAND_HOVER)

    def _done(self, produced):
        self._running = False
        self.progress.set(1.0)
        n = len(produced)
        self.status.configure(text=f"✅ Fatto: {n} file generati.")
        self._reset_button()
        if self.last_output_dir:
            self.open_btn.pack(fill="x", padx=16, pady=(0, 16))
        _notify(APP_NAME, f"Generati {n} file.")
        lst = "\n".join(f"• {os.path.basename(p)}" for p in produced[:14])
        if n > 14:
            lst += f"\n… e altri {n - 14}"
        messagebox.showinfo(APP_NAME, f"Generati {n} file:\n\n{lst}")

    def _cancelled(self):
        self._running = False
        self.progress.set(0)
        self.status.configure(text="Operazione annullata.")
        self._reset_button()

    def _error(self, msg, tb):
        self._running = False
        self.progress.set(0)
        self.status.configure(text="Errore durante l'elaborazione.")
        self._reset_button()
        log.error("Errore:\n%s", tb)
        messagebox.showerror(APP_NAME,
                             f"Si è verificato un errore:\n\n{msg}\n\n"
                             f"Dettagli nel log:\n{log_path()}")


class PreviewEditor(ctk.CTkToplevel):
    """Finestra per rivedere e modificare i segmenti prima di salvare."""

    def __init__(self, parent, result: TranscriptionResult, on_confirm):
        super().__init__(parent)
        self.result = result
        self.on_confirm = on_confirm
        self.title("Anteprima e modifica sottotitoli")
        self.geometry("720x560")
        self.transient(parent)

        ctk.CTkLabel(self, text="Rivedi e correggi i testi, poi conferma.",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(12, 6))

        self.scroll = ctk.CTkScrollableFrame(self, fg_color=BG_CARD)
        self.scroll.pack(fill="both", expand=True, padx=12, pady=6)

        self.entries: list[tuple[Segment, ctk.CTkTextbox]] = []
        for seg in result.segments:
            rowf = ctk.CTkFrame(self.scroll, fg_color=BG_CARD2, corner_radius=8)
            rowf.pack(fill="x", padx=4, pady=4)
            tstamp = f"{_fmt_ts(seg.start)} → {_fmt_ts(seg.end)}"
            ctk.CTkLabel(rowf, text=f"#{seg.index}  {tstamp}",
                         font=ctk.CTkFont(size=11), text_color=TXT_DIM
                         ).pack(anchor="w", padx=10, pady=(6, 0))
            box = ctk.CTkTextbox(rowf, height=48)
            box.insert("1.0", seg.text)
            box.pack(fill="x", padx=10, pady=(2, 8))
            self.entries.append((seg, box))

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=12, pady=10)
        ctk.CTkButton(btns, text="Annulla", command=self.destroy,
                      fg_color=BG_CARD2, hover_color="#33333f").pack(side="right", padx=(8, 0))
        ctk.CTkButton(btns, text="✅ Conferma e salva", command=self._confirm,
                      fg_color=BRAND, hover_color=BRAND_HOVER).pack(side="right")

    def _confirm(self):
        for seg, box in self.entries:
            seg.text = box.get("1.0", "end").strip()
        self.destroy()
        self.on_confirm()


def _fmt_ts(seconds: float) -> str:
    s = max(0, int(seconds))
    m, s = divmod(s, 60)
    return f"{m:02d}:{s:02d}"


def main():
    log.info("Avvio %s %s (dnd=%s)", APP_NAME, APP_VERSION, _HAS_DND)
    if _HAS_DND:
        root = TkinterDnD.Tk()
    else:
        root = ctk.CTk()
    SubtitlerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
