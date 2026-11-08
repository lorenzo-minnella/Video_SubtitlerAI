"""
Video SubtitlerAI — Interfaccia grafica (PySide6 / Qt)
======================================================
UI moderna a due colonne: sidebar impostazioni + area principale con drop zone,
coda file, avanzamento. Look nativo e scuro/chiaro.

Tutte le funzioni del motore restano invariate:
  coda multi-file, lingua auto/EN/IT/ES/FR/DE/PT, traduzione (orig + tradotto),
  formati SRT/VTT/TXT, spezzatura righe, audio difficile, hardsub, anteprima,
  impostazioni persistenti, tema chiaro/scuro, log diagnostico.

Avvio:
    python app_gui.py
"""

from __future__ import annotations

import os
import sys
import traceback

from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QLabel, QPushButton, QComboBox,
    QCheckBox, QProgressBar, QFileDialog, QMessageBox, QHBoxLayout, QVBoxLayout,
    QFrame, QListWidget, QListWidgetItem, QButtonGroup, QScrollArea, QTextEdit,
    QDialog, QDialogButtonBox, QSizePolicy,
)

try:
    import core.subtitle_engine as eng
    from core.subtitle_engine import (
        AVAILABLE_MODELS, SUPPORTED_LANGUAGES, TRANSLATION_TARGETS,
        SubtitleEngine, TranscriptionResult, translate_segments,
        write_subtitles, burn_subtitles, has_ffmpeg,
    )
    from core.logger import get_logger, log_path
    from core.settings import load_settings, save_settings
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import core.subtitle_engine as eng
    from core.subtitle_engine import (
        AVAILABLE_MODELS, SUPPORTED_LANGUAGES, TRANSLATION_TARGETS,
        SubtitleEngine, TranscriptionResult, translate_segments,
        write_subtitles, burn_subtitles, has_ffmpeg,
    )
    from core.logger import get_logger, log_path
    from core.settings import load_settings, save_settings

log = get_logger()

APP_NAME = "Video SubtitlerAI"
APP_VERSION = "3.4"

VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v",
              ".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg")

BRAND = "#7C6CF0"


# -----------------------------------------------------------------------------
# Fogli di stile (QSS) per tema scuro e chiaro
# -----------------------------------------------------------------------------
def qss(theme: str) -> str:
    if theme == "light":
        bg, panel, card, text, dim, border, field = (
            "#f3f4f8", "#ffffff", "#eef0f6", "#1b1d26",
            "#6b7085", "#d8dbe6", "#ffffff")
    else:
        bg, panel, card, text, dim, border, field = (
            "#13131b", "#1b1b26", "#232330", "#e8ebf5",
            "#8b90a6", "#33333f", "#262633")
    return f"""
    QMainWindow, QWidget#root {{ background: {bg}; }}
    QLabel {{ color: {text}; font-size: 13px; }}
    QLabel#title {{ font-size: 20px; font-weight: 700; }}
    QLabel#version {{ color: {dim}; font-size: 12px; }}
    QLabel#section {{ color: {dim}; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
    QLabel#dim {{ color: {dim}; font-size: 12px; }}
    QFrame#panel {{ background: {panel}; border-radius: 14px; }}
    QFrame#drop {{ background: {card}; border: 2px dashed {border}; border-radius: 14px; }}
    QComboBox {{
        background: {field}; color: {text}; border: 1px solid {border};
        border-radius: 9px; padding: 8px 12px; font-size: 13px; min-height: 20px;
    }}
    QComboBox::drop-down {{ border: 0; width: 24px; }}
    QComboBox QAbstractItemView {{
        background: {panel}; color: {text}; border: 1px solid {border};
        selection-background-color: {BRAND}; outline: 0;
    }}
    QPushButton#primary {{
        background: {BRAND}; color: white; border: 0; border-radius: 11px;
        padding: 14px; font-size: 15px; font-weight: 700;
    }}
    QPushButton#primary:hover {{ background: #6a5ae0; }}
    QPushButton#ghost {{
        background: {card}; color: {text}; border: 1px solid {border};
        border-radius: 9px; padding: 8px 14px; font-size: 13px;
    }}
    QPushButton#ghost:hover {{ background: {border}; }}
    QPushButton#brandbtn {{
        background: {BRAND}; color: white; border: 0; border-radius: 9px;
        padding: 9px 16px; font-size: 13px; font-weight: 600;
    }}
    QPushButton#brandbtn:hover {{ background: #6a5ae0; }}
    QCheckBox {{ color: {text}; font-size: 12.5px; spacing: 8px; }}
    QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px;
        border: 1px solid {border}; background: {field}; }}
    QCheckBox::indicator:checked {{ background: {BRAND}; border: 1px solid {BRAND}; }}
    QListWidget {{ background: {panel}; border: 0; border-radius: 12px;
        padding: 6px; font-size: 13px; color: {text}; outline: 0; }}
    QListWidget::item {{ background: {card}; border-radius: 8px; padding: 10px;
        margin: 3px; }}
    QListWidget::item:selected {{ background: {BRAND}; color: white; }}
    QProgressBar {{ background: {card}; border: 0; border-radius: 5px; height: 10px;
        text-align: center; color: transparent; }}
    QProgressBar::chunk {{ background: {BRAND}; border-radius: 5px; }}
    QTextEdit {{ background: {field}; color: {text}; border: 1px solid {border};
        border-radius: 8px; font-size: 13px; }}
    """


# -----------------------------------------------------------------------------
# Worker in thread separato (non blocca la UI)
# -----------------------------------------------------------------------------
class Worker(QObject):
    progress = Signal(float, str)
    done = Signal(list)
    error = Signal(str, str)
    cancelled = Signal()

    def __init__(self, engine, files, cfg):
        super().__init__()
        self.engine = engine
        self.files = files
        self.cfg = cfg
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            cfg = self.cfg
            produced: list[str] = []
            total = len(self.files)
            for i, media in enumerate(self.files, 1):
                if self._cancel:
                    self.cancelled.emit(); return
                pfx = f"[{i}/{total}] " if total > 1 else ""
                self.progress.emit(0.0, f"{pfx}Avvio: {os.path.basename(media)}")
                res = self.engine.transcribe(
                    media, language=cfg["language"], task="transcribe",
                    fast=(cfg["speed"] == "Veloce"), hard_audio=cfg["hard_audio"],
                    progress=lambda fr, ms, p=pfx: self.progress.emit(fr, p + ms),
                    cancel_check=lambda: self._cancel)

                out_dir = cfg["output_dir"] or os.path.dirname(media)
                base = os.path.splitext(os.path.basename(media))[0]
                wrap = cfg["wrap_lines"]

                produced += self._write(res, out_dir, base, res.language,
                                        cfg["formats"], wrap)
                tgt = cfg["translate"]
                if tgt not in ("none", "") and tgt != res.language:
                    self.progress.emit(0.0, f"{pfx}Traduco in '{tgt}'...")
                    tr = TranscriptionResult(
                        language=tgt, language_probability=1.0, duration=res.duration,
                        segments=translate_segments(
                            res.segments, res.language, tgt,
                            lambda fr, ms: self.progress.emit(fr, ms)))
                    produced += self._write(tr, out_dir, base, tgt, cfg["formats"], wrap)

                if cfg["burn"] and has_ffmpeg():
                    srt = os.path.join(out_dir, f"{base}.{res.language}.srt")
                    if not os.path.isfile(srt):
                        write_subtitles(res, srt, fmt="srt")
                    outv = os.path.join(out_dir, f"{base}.sub.mp4")
                    try:
                        burn_subtitles(media, srt, outv,
                                       progress=lambda fr, ms: self.progress.emit(fr, ms))
                        produced.append(outv)
                    except Exception as exc:
                        log.error("Hardsub fallito: %s", exc)
            self.done.emit(produced)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc), traceback.format_exc())

    def _write(self, res, out_dir, base, lang, formats, wrap):
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


# -----------------------------------------------------------------------------
# Finestra principale
# -----------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.engine: SubtitleEngine | None = None
        self.files: list[str] = []
        self.cfg = load_settings()
        self.output_dir = self.cfg.get("output_dir") or None
        self.last_output_dir = None
        self.thread = None
        self.worker = None

        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(920, 640)
        self.setMinimumSize(860, 600)
        self.setAcceptDrops(True)

        self._build()
        self._apply_theme(self.cfg.get("theme", "dark"))

    # ------------------------------------------------------------- costruzione
    def _build(self):
        root = QWidget(); root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root); outer.setContentsMargins(20, 16, 20, 20); outer.setSpacing(14)

        # Header
        head = QHBoxLayout()
        t = QLabel("🎬  Video SubtitlerAI"); t.setObjectName("title")
        v = QLabel(APP_VERSION); v.setObjectName("version")
        head.addWidget(t); head.addWidget(v); head.addStretch()
        self.theme_btn = QPushButton("☾"); self.theme_btn.setObjectName("ghost")
        self.theme_btn.setFixedWidth(44); self.theme_btn.clicked.connect(self._toggle_theme)
        head.addWidget(self.theme_btn)
        outer.addLayout(head)

        body = QHBoxLayout(); body.setSpacing(14); outer.addLayout(body, 1)

        # ===== Sidebar impostazioni =====
        side = QFrame(); side.setObjectName("panel"); side.setFixedWidth(300)
        sl = QVBoxLayout(side); sl.setContentsMargins(18, 16, 18, 16); sl.setSpacing(8)
        sec = QLabel("IMPOSTAZIONI"); sec.setObjectName("section"); sl.addWidget(sec)

        sl.addWidget(QLabel("Lingua audio"))
        self.lang_cb = QComboBox(); self.lang_cb.addItems(list(SUPPORTED_LANGUAGES.values()))
        self.lang_cb.setCurrentText(SUPPORTED_LANGUAGES.get(self.cfg["language"],
                                                            SUPPORTED_LANGUAGES["auto"]))
        sl.addWidget(self.lang_cb)

        sl.addWidget(QLabel("Traduci in"))
        self.tr_cb = QComboBox(); self.tr_cb.addItems(list(TRANSLATION_TARGETS.values()))
        self.tr_cb.setCurrentText(TRANSLATION_TARGETS.get(self.cfg["translate"],
                                                          TRANSLATION_TARGETS["none"]))
        sl.addWidget(self.tr_cb)

        sl.addWidget(QLabel("Qualità modello"))
        self.model_cb = QComboBox()
        for k, desc in AVAILABLE_MODELS.items():
            self.model_cb.addItem(k)
        self.model_cb.setCurrentText(self.cfg["model"])
        sl.addWidget(self.model_cb)

        sl.addWidget(QLabel("Velocità"))
        speed_row = QHBoxLayout(); speed_row.setSpacing(0)
        self.speed_group = QButtonGroup(self)
        self.btn_quality = QPushButton("Qualità"); self.btn_fast = QPushButton("Veloce")
        for b in (self.btn_quality, self.btn_fast):
            b.setCheckable(True); b.setObjectName("ghost"); self.speed_group.addButton(b)
            speed_row.addWidget(b)
        (self.btn_fast if self.cfg["speed"] == "Veloce" else self.btn_quality).setChecked(True)
        self.btn_quality.clicked.connect(lambda: self._set_speed("Qualità"))
        self.btn_fast.clicked.connect(lambda: self._set_speed("Veloce"))
        sl.addLayout(speed_row)

        sl.addSpacing(6)
        self.cb_wrap = QCheckBox("Spezzatura righe intelligente")
        self.cb_wrap.setChecked(self.cfg.get("wrap_lines", True)); sl.addWidget(self.cb_wrap)
        self.cb_hard = QCheckBox("Audio difficile (voci deboli/lontane)")
        self.cb_hard.setChecked(self.cfg.get("hard_audio", False)); sl.addWidget(self.cb_hard)
        self.cb_burn = QCheckBox("Masterizza nel video (hardsub)")
        self.cb_burn.setChecked(self.cfg.get("burn", False))
        if not has_ffmpeg():
            self.cb_burn.setEnabled(False); self.cb_burn.setText("Hardsub (richiede ffmpeg)")
        sl.addWidget(self.cb_burn)
        sl.addSpacing(6)
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Formati:"))
        self.fmt_boxes = {}
        for f in ("srt", "vtt", "txt"):
            cb = QCheckBox(f.upper()); cb.setChecked(f in self.cfg["formats"])
            self.fmt_boxes[f] = cb; fmt_row.addWidget(cb)
        fmt_row.addStretch()
        sl.addLayout(fmt_row)
        sl.addStretch()
        body.addWidget(side)

        # ===== Area principale =====
        main = QVBoxLayout(); main.setSpacing(12); body.addLayout(main, 1)

        # Drop zone
        self.drop = QFrame(); self.drop.setObjectName("drop"); self.drop.setFixedHeight(170)
        dl = QVBoxLayout(self.drop); dl.setAlignment(Qt.AlignCenter)
        icon = QLabel("⬇"); icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(f"font-size: 34px; color: {BRAND};")
        t1 = QLabel("Trascina qui i tuoi video"); t1.setAlignment(Qt.AlignCenter)
        t1.setStyleSheet("font-size: 16px; font-weight: 600;")
        t2 = QLabel("oppure"); t2.setObjectName("dim"); t2.setAlignment(Qt.AlignCenter)
        browse = QPushButton("Sfoglia file…"); browse.setObjectName("brandbtn")
        browse.setFixedWidth(150); browse.clicked.connect(self._browse)
        dl.addWidget(icon); dl.addWidget(t1); dl.addWidget(t2)
        hb = QHBoxLayout(); hb.addStretch(); hb.addWidget(browse); hb.addStretch(); dl.addLayout(hb)
        main.addWidget(self.drop)

        # Coda
        qhead = QHBoxLayout()
        self.queue_label = QLabel("IN CODA (0)"); self.queue_label.setObjectName("section")
        qhead.addWidget(self.queue_label); qhead.addStretch()
        clear = QPushButton("Svuota"); clear.setObjectName("ghost"); clear.clicked.connect(self._clear)
        folder = QPushButton("Cartella…"); folder.setObjectName("ghost"); folder.clicked.connect(self._browse_dir)
        qhead.addWidget(folder); qhead.addWidget(clear)
        main.addLayout(qhead)
        self.queue = QListWidget(); main.addWidget(self.queue, 1)

        # Output dir
        orow = QHBoxLayout()
        orow.addWidget(QLabel("Cartella output:"))
        self.out_label = QLabel(os.path.basename(self.output_dir) if self.output_dir
                                else "Accanto al video"); self.out_label.setObjectName("dim")
        orow.addWidget(self.out_label); orow.addStretch()
        obtn = QPushButton("Scegli…"); obtn.setObjectName("ghost"); obtn.clicked.connect(self._choose_out)
        orow.addWidget(obtn)
        main.addLayout(orow)

        # CTA + progress
        self.run_btn = QPushButton("✨  Genera sottotitoli"); self.run_btn.setObjectName("primary")
        self.run_btn.clicked.connect(self._start); main.addWidget(self.run_btn)
        self.bar = QProgressBar(); self.bar.setRange(0, 100); self.bar.setValue(0)
        main.addWidget(self.bar)
        self.status = QLabel("Pronto."); self.status.setObjectName("dim")
        main.addWidget(self.status)
        self.open_btn = QPushButton("📂  Apri cartella output"); self.open_btn.setObjectName("ghost")
        self.open_btn.clicked.connect(self._open_output); self.open_btn.hide()
        main.addWidget(self.open_btn)

    # ------------------------------------------------------------- tema
    def _apply_theme(self, theme):
        self.setStyleSheet(qss(theme))
        self.theme_btn.setText("☀" if theme == "dark" else "☾")

    def _toggle_theme(self):
        new = "light" if self.cfg.get("theme", "dark") == "dark" else "dark"
        self.cfg["theme"] = new
        self._apply_theme(new); self._persist()

    def _set_speed(self, val):
        self.cfg["speed"] = val

    # ------------------------------------------------------------- file / DnD
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls()]
        self._add(paths)

    def _add(self, paths):
        added = 0
        for p in paths:
            if os.path.isdir(p):
                for r, _, names in os.walk(p):
                    for n in names:
                        if n.lower().endswith(VIDEO_EXTS):
                            fp = os.path.join(r, n)
                            if fp not in self.files:
                                self.files.append(fp); added += 1
            elif os.path.isfile(p) and p.lower().endswith(VIDEO_EXTS) and p not in self.files:
                self.files.append(p); added += 1
        if added:
            self._refresh_queue()

    def _refresh_queue(self):
        self.queue.clear()
        for f in self.files:
            QListWidgetItem(f"🎞  {os.path.basename(f)}", self.queue)
        self.queue_label.setText(f"IN CODA ({len(self.files)})")
        self.status.setText(f"{len(self.files)} file in coda." if self.files else "Pronto.")

    def _browse(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Seleziona video/audio", "",
            "Media (" + " ".join(f"*{e}" for e in VIDEO_EXTS) + ");;Tutti (*.*)")
        if paths:
            self._add(paths)

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Scegli una cartella di video")
        if d:
            self._add([d])

    def _clear(self):
        self.files = []; self._refresh_queue()

    def _choose_out(self):
        d = QFileDialog.getExistingDirectory(self, "Cartella di output")
        self.output_dir = d or None
        self.out_label.setText(os.path.basename(d) if d else "Accanto al video")
        self._persist()

    def _open_output(self):
        if self.last_output_dir:
            import subprocess
            if sys.platform.startswith("win"):
                os.startfile(self.last_output_dir)  # type: ignore
            elif sys.platform == "darwin":
                subprocess.run(["open", self.last_output_dir], check=False)
            else:
                subprocess.run(["xdg-open", self.last_output_dir], check=False)

    def _label_to_code(self, mapping, label):
        for c, l in mapping.items():
            if l == label:
                return c
        return label

    def _collect(self):
        return {
            "language": self._label_to_code(SUPPORTED_LANGUAGES, self.lang_cb.currentText()),
            "model": self.model_cb.currentText(),
            "translate": self._label_to_code(TRANSLATION_TARGETS, self.tr_cb.currentText()),
            "speed": self.cfg.get("speed", "Qualità"),
            "formats": [f for f, cb in self.fmt_boxes.items() if cb.isChecked()] or ["srt"],
            "output_dir": self.output_dir or "",
            "theme": self.cfg.get("theme", "dark"),
            "burn": self.cb_burn.isChecked(),
            "wrap_lines": self.cb_wrap.isChecked(),
            "hard_audio": self.cb_hard.isChecked(),
        }

    def _persist(self):
        save_settings(self._collect())

    # ------------------------------------------------------------- run
    def _start(self):
        if self.thread and self.thread.isRunning():
            if self.worker:
                self.worker.cancel()
            self.status.setText("Annullamento in corso...")
            return
        if not self.files:
            QMessageBox.warning(self, APP_NAME, "Aggiungi almeno un file video.")
            return
        self._persist()
        cfg = self._collect()
        model = cfg["model"]
        if self.engine is None or self.engine.model_size != model:
            self.engine = SubtitleEngine(model_size=model)

        self.run_btn.setText("⏹  Annulla")
        self.open_btn.hide(); self.bar.setValue(0)

        self.thread = QThread()
        self.worker = Worker(self.engine, list(self.files), cfg)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._on_done)
        self.worker.error.connect(self._on_error)
        self.worker.cancelled.connect(self._on_cancelled)
        self.thread.start()

    def _on_progress(self, frac, msg):
        self.bar.setValue(int(max(0, min(1, frac)) * 100))
        self.status.setText(msg)

    def _finish_thread(self):
        if self.thread:
            self.thread.quit(); self.thread.wait()
        self.run_btn.setText("✨  Genera sottotitoli")

    def _on_done(self, produced):
        self.last_output_dir = (os.path.dirname(produced[0]) if produced else None)
        self.bar.setValue(100)
        self.status.setText(f"✅ Fatto: {len(produced)} file generati.")
        self._finish_thread()
        if self.last_output_dir:
            self.open_btn.show()
        lst = "\n".join(f"• {os.path.basename(p)}" for p in produced[:14])
        QMessageBox.information(self, APP_NAME, f"Generati {len(produced)} file:\n\n{lst}")

    def _on_cancelled(self):
        self.bar.setValue(0); self.status.setText("Operazione annullata.")
        self._finish_thread()

    def _on_error(self, msg, tb):
        self.bar.setValue(0); self.status.setText("Errore durante l'elaborazione.")
        self._finish_thread()
        log.error("Errore:\n%s", tb)
        QMessageBox.critical(self, APP_NAME,
                             f"Si è verificato un errore:\n\n{msg}\n\nLog:\n{log_path()}")


def main():
    log.info("Avvio %s %s (Qt/PySide6)", APP_NAME, APP_VERSION)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
