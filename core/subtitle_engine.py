"""
subtitle_engine.py
==================
Motore di generazione sottotitoli basato su faster-whisper (locale, gratuito).

Flusso:
  1. faster-whisper decodifica l'audio del video e lo trascrive con timestamp
     per segmento. La decodifica usa PyAV (libav/ffmpeg incluse nel pacchetto
     `av`): NON serve un ffmpeg installato sul sistema.
  2. I segmenti vengono convertiti in file di sottotitoli (.srt / .vtt).
  3. Opzionalmente i testi vengono tradotti in un'altra lingua con Argos Translate.

Il modulo NON dipende dalla GUI: espone funzioni e una classe usabili anche
da riga di comando o da altri script.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

try:
    from .logger import get_logger
except ImportError:  # esecuzione come modulo top-level
    from logger import get_logger

log = get_logger()

# -----------------------------------------------------------------------------
# Modelli disponibili (nome faster-whisper -> descrizione)
# -----------------------------------------------------------------------------
AVAILABLE_MODELS = {
    "tiny": "Velocissimo, qualità bassa (~1 GB)",
    "base": "Veloce, qualità modesta (~1 GB)",
    "small": "Buon compromesso (~2 GB)",
    "medium": "Qualità alta, più lento (~5 GB)",
    "distil-large-v3": "Quasi come large, molto più veloce (~5 GB)",
    "large-v3": "Qualità massima, il più lento (~10 GB)",
}

# Lingue esposte in UI (codice ISO -> etichetta leggibile)
SUPPORTED_LANGUAGES = {
    "auto": "Rileva automaticamente",
    "en": "Inglese",
    "it": "Italiano",
    "es": "Spagnolo",
    "fr": "Francese",
    "de": "Tedesco",
    "pt": "Portoghese",
}

# Lingue di destinazione per la traduzione
TRANSLATION_TARGETS = {
    "none": "Nessuna traduzione",
    "it": "Italiano",
    "en": "Inglese",
    "es": "Spagnolo",
    "fr": "Francese",
    "de": "Tedesco",
    "pt": "Portoghese",
}

# Parametri di spezzatura righe (standard sottotitolazione)
MAX_CHARS_PER_LINE = 42
MAX_LINES = 2
MIN_SEG_DURATION = 1.0   # secondi
MAX_SEG_DURATION = 7.0   # secondi


@dataclass
class Word:
    """Una parola con i suoi tempi (word-level timestamp)."""
    start: float
    end: float
    text: str


@dataclass
class Segment:
    """Un segmento di sottotitolo con tempi in secondi."""
    index: int
    start: float
    end: float
    text: str
    words: list["Word"] = field(default_factory=list)


@dataclass
class TranscriptionResult:
    language: str
    language_probability: float
    duration: float
    segments: list[Segment] = field(default_factory=list)


# -----------------------------------------------------------------------------
# Utility formato sottotitoli
# -----------------------------------------------------------------------------
def _format_timestamp(seconds: float, *, vtt: bool = False) -> str:
    """Converte secondi in timestamp SRT (00:00:00,000) o VTT (00:00:00.000)."""
    if seconds < 0:
        seconds = 0.0
    millis = int(round(seconds * 1000.0))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    sep = "." if vtt else ","
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{sep}{millis:03d}"


def _fmt_clock(seconds: float) -> str:
    """Posizione nell'audio in forma compatta mm:ss (o h:mm:ss se >= 1h)."""
    seconds = max(0, int(round(seconds)))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _fmt_duration(seconds: float) -> str:
    """Durata leggibile per tempo trascorso/rimanente, es. '2m 30s' o '45s'."""
    seconds = max(0, int(round(seconds)))
    if seconds < 60:
        return f"{seconds}s"
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m {secs:02d}s"


def _wrap_text(text: str, max_chars: int = MAX_CHARS_PER_LINE,
               max_lines: int = MAX_LINES) -> str:
    """
    Spezza il testo in righe di al più `max_chars` caratteri, bilanciando le
    parole, con un massimo di `max_lines` righe. È lo standard dei sottotitoli:
    righe corte e leggibili. Se il testo eccede, resta su max_lines righe
    (l'ultima più lunga) perché il taglio temporale è già gestito a monte.
    """
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text

    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for w in words:
        candidate = f"{current} {w}".strip()
        if len(candidate) <= max_chars or not current:
            current = candidate
        else:
            lines.append(current)
            current = w
            if len(lines) == max_lines - 1:
                # Ultima riga: ci mettiamo tutto il resto
                rest = w
                idx = words.index(w) + 1
                current = " ".join([rest] + words[idx:])
                break
    if current:
        lines.append(current)
    return "\n".join(lines[:max_lines])


def segments_to_srt(segments: Iterable[Segment], wrap: bool = True) -> str:
    """Serializza i segmenti in formato SubRip (.srt), con spezzatura righe."""
    lines: list[str] = []
    for seg in segments:
        txt = _wrap_text(seg.text.strip()) if wrap else seg.text.strip()
        lines.append(str(seg.index))
        lines.append(
            f"{_format_timestamp(seg.start)} --> {_format_timestamp(seg.end)}"
        )
        lines.append(txt)
        lines.append("")  # riga vuota separatore
    return "\n".join(lines).strip() + "\n"


def segments_to_vtt(segments: Iterable[Segment], wrap: bool = True) -> str:
    """Serializza i segmenti in formato WebVTT (.vtt), con spezzatura righe."""
    lines: list[str] = ["WEBVTT", ""]
    for seg in segments:
        txt = _wrap_text(seg.text.strip()) if wrap else seg.text.strip()
        lines.append(
            f"{_format_timestamp(seg.start, vtt=True)} --> "
            f"{_format_timestamp(seg.end, vtt=True)}"
        )
        lines.append(txt)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


# -----------------------------------------------------------------------------
# Traduzione offline (Argos Translate) — import lazy per non appesantire l'avvio
# -----------------------------------------------------------------------------
def translate_segments(
    segments: list[Segment],
    source_lang: str,
    target_lang: str,
    progress: Optional[Callable[[float, str], None]] = None,
) -> list[Segment]:
    """
    Traduce il testo dei segmenti da source_lang a target_lang usando Argos
    Translate (offline). Installa il pacchetto lingua al volo se mancante.

    Ritorna nuovi Segment con il testo tradotto (tempi invariati).
    """
    if target_lang in ("none", "", None) or source_lang == target_lang:
        return segments

    try:
        import argostranslate.package
        import argostranslate.translate
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Argos Translate non è installato. Esegui: pip install argostranslate"
        ) from exc

    _ensure_argos_package(source_lang, target_lang, progress)

    installed = argostranslate.translate.get_installed_languages()
    from_lang = next((l for l in installed if l.code == source_lang), None)
    to_lang = next((l for l in installed if l.code == target_lang), None)
    if from_lang is None or to_lang is None:
        raise RuntimeError(
            f"Coppia di traduzione {source_lang}->{target_lang} non disponibile."
        )
    translation = from_lang.get_translation(to_lang)

    total = len(segments) or 1
    out: list[Segment] = []
    for i, seg in enumerate(segments):
        translated_text = translation.translate(seg.text.strip())
        out.append(
            Segment(index=seg.index, start=seg.start, end=seg.end, text=translated_text)
        )
        if progress:
            progress((i + 1) / total, f"Traduzione {i + 1}/{total}")
    return out


def _ensure_argos_package(
    source_lang: str,
    target_lang: str,
    progress: Optional[Callable[[float, str], None]] = None,
) -> None:
    """Scarica e installa il pacchetto lingua Argos se non già presente."""
    import argostranslate.package
    import argostranslate.translate

    installed = argostranslate.translate.get_installed_languages()
    # Verifica che entrambe le lingue della coppia siano installate.
    from_ok = any(l.code == source_lang for l in installed)
    to_ok = any(l.code == target_lang for l in installed)
    if from_ok and to_ok:
        return

    if progress:
        progress(0.0, "Scarico pacchetto di traduzione...")

    # Usa i certificati certifi per l'HTTPS quando disponibili: evita gli errori
    # CERTIFICATE_VERIFY_FAILED comuni su macOS/Windows senza i certificati di sistema.
    _install_ssl_opener()

    log.info("Scarico il pacchetto di traduzione %s->%s...", source_lang, target_lang)
    try:
        argostranslate.package.update_package_index()
        available = argostranslate.package.get_available_packages()
    except Exception as exc:  # errori di rete/SSL nell'aggiornamento indice
        log.error("Errore aggiornando l'indice pacchetti Argos: %s", exc)
        raise RuntimeError(_NETWORK_HELP) from exc

    pkg = next(
        (p for p in available if p.from_code == source_lang and p.to_code == target_lang),
        None,
    )
    if pkg is None:
        raise RuntimeError(
            f"Nessun pacchetto di traduzione {source_lang}->{target_lang} disponibile."
        )

    try:
        download_path = pkg.download()
    except Exception as exc:
        # Argos può rilanciare in loop su errori di rete: lo convertiamo in un
        # messaggio chiaro e interrompiamo subito (niente RecursionError).
        log.error("Download del pacchetto di traduzione fallito: %s", exc)
        raise RuntimeError(_NETWORK_HELP) from exc

    argostranslate.package.install_from_path(download_path)
    log.info("Pacchetto di traduzione installato.")


# Messaggio d'aiuto condiviso per i fallimenti di download della traduzione.
_NETWORK_HELP = (
    "Impossibile scaricare il pacchetto di traduzione. Al primo uso serve una "
    "connessione internet (senza proxy/firewall che intercetti i certificati HTTPS). "
    "Riprova su una rete aperta: il pacchetto viene scaricato una sola volta."
)


def _install_ssl_opener() -> None:
    """
    Imposta un opener urllib che usa i certificati 'certifi' se presenti.
    Risolve i CERTIFICATE_VERIFY_FAILED senza disabilitare la verifica SSL.
    Non solleva eccezioni: in caso di problemi lascia il comportamento di default.
    """
    try:
        import ssl
        import urllib.request
        import certifi

        ctx = ssl.create_default_context(cafile=certifi.where())
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
        urllib.request.install_opener(opener)
    except Exception:
        # certifi non disponibile o altro: si prosegue col default di sistema.
        pass


# -----------------------------------------------------------------------------
# Motore principale
# -----------------------------------------------------------------------------
class SubtitleEngine:
    """
    Incapsula il modello faster-whisper e produce sottotitoli da un file media.

    Il modello viene caricato pigramente al primo uso e riusato per i file
    successivi (evita ricaricamenti costosi).
    """

    def __init__(self, model_size: str = "small", device: str = "auto",
                 compute_type: str = "auto"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None

    def _load_model(self, progress: Optional[Callable[[float, str], None]] = None):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "faster-whisper non è installato. Esegui: pip install faster-whisper"
            ) from exc

        if progress:
            progress(0.0, f"Carico il modello '{self.model_size}'...")

        import time
        t0 = time.monotonic()
        log.info("Carico il modello '%s' (device=%s, compute=%s)...",
                 self.model_size, self.device, self.compute_type)

        device = self.device
        compute_type = self.compute_type
        if device == "auto":
            # Prova GPU CUDA, altrimenti CPU. In caso di errore CUDA ricadi su CPU.
            try:
                self._model = WhisperModel(
                    self.model_size, device="cuda",
                    compute_type="float16" if compute_type == "auto" else compute_type,
                )
                log.info("Modello caricato su GPU (CUDA) in %.1fs.",
                         time.monotonic() - t0)
                return self._model
            except Exception as exc:
                log.info("GPU CUDA non disponibile (%s): uso la CPU.", exc)
                device = "cpu"
                compute_type = "int8" if compute_type == "auto" else compute_type
        if compute_type == "auto":
            compute_type = "int8" if device == "cpu" else "float16"

        self._model = WhisperModel(self.model_size, device=device, compute_type=compute_type)
        log.info("Modello caricato su %s (compute=%s) in %.1fs.",
                 device, compute_type, time.monotonic() - t0)
        return self._model

    def transcribe(
        self,
        media_path: str,
        language: str = "auto",
        task: str = "transcribe",
        fast: bool = False,
        progress: Optional[Callable[[float, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> TranscriptionResult:
        """
        Trascrive (o traduce verso l'inglese, se task='translate') il file media.

        Args:
            media_path: percorso del video/audio.
            language: codice lingua sorgente o 'auto'.
            task: 'transcribe' (lingua originale) o 'translate' (-> inglese, nativo Whisper).
            fast: se True usa parametri più rapidi (beam_size=1, greedy) a lieve
                  scapito della qualità; utile su CPU o video lunghi.
            progress: callback(frazione 0..1, messaggio).
            cancel_check: ritorna True per interrompere.
        """
        if not os.path.isfile(media_path):
            raise FileNotFoundError(media_path)

        import time

        log.info("=== Nuova trascrizione ===")
        log.info("File: %s", media_path)
        log.info("Lingua richiesta: %s | task: %s | modello: %s",
                 language, task, self.model_size)

        model = self._load_model(progress)

        if progress:
            progress(0.02, "Analizzo l'audio (rilevo le parti parlate)...")
        log.info("Analizzo l'audio (VAD) e avvio la trascrizione...")

        lang_arg = None if language == "auto" else language
        # Parametri: in modalità "fast" usiamo greedy (beam_size=1) che su CPU è
        # sensibilmente più veloce; altrimenti beam search per qualità migliore.
        beam = 1 if fast else 5
        segments_iter, info = model.transcribe(
            media_path,
            language=lang_arg,
            task=task,
            vad_filter=True,  # rimuove silenzi lunghi -> segmenti più puliti
            beam_size=beam,
            condition_on_previous_text=False,  # evita loop di ripetizioni, più stabile
            word_timestamps=True,  # tempi parola per parola (per split preciso)
        )
        log.info("Parametri: beam_size=%d, fast=%s, word_timestamps=True", beam, fast)

        duration = float(getattr(info, "duration", 0.0) or 0.0)
        result = TranscriptionResult(
            language=getattr(info, "language", language) or language,
            language_probability=float(getattr(info, "language_probability", 0.0) or 0.0),
            duration=duration,
        )
        log.info("Durata audio: %.1fs | lingua rilevata: %s (%.0f%%)",
                 duration, result.language, result.language_probability * 100)

        start_time = time.monotonic()
        idx = 1
        last_audio_pos = 0.0
        last_log = 0.0
        for seg in segments_iter:
            if cancel_check and cancel_check():
                log.info("Trascrizione annullata dall'utente a %.1fs.", last_audio_pos)
                raise InterruptedError("Operazione annullata dall'utente.")
            text = (seg.text or "").strip()
            if not text:
                continue
            words = []
            for w in (getattr(seg, "words", None) or []):
                wt = (w.word or "").strip()
                if wt:
                    words.append(Word(start=float(w.start), end=float(w.end), text=wt))
            result.segments.append(
                Segment(index=idx, start=float(seg.start), end=float(seg.end),
                        text=text, words=words)
            )
            idx += 1
            last_audio_pos = float(seg.end)

            # Log periodico (ogni ~10s di audio) per tracciare l'avanzamento nel file.
            if last_audio_pos - last_log >= 10.0:
                elapsed = time.monotonic() - start_time
                speed = last_audio_pos / elapsed if elapsed > 0 else 0.0
                log.debug("Avanzamento: audio %.0fs/%.0fs | trascorso %.0fs | "
                          "velocità %.2fx", last_audio_pos, duration, elapsed, speed)
                last_log = last_audio_pos

            if progress and duration > 0:
                frac = min(0.98, 0.02 + 0.96 * (last_audio_pos / duration))
                elapsed = time.monotonic() - start_time
                # Velocità di elaborazione: secondi di audio processati al secondo.
                speed = last_audio_pos / elapsed if elapsed > 0 else 0.0
                remaining_audio = max(0.0, duration - last_audio_pos)
                eta = remaining_audio / speed if speed > 0 else 0.0
                progress(
                    frac,
                    f"Trascrivo {_fmt_clock(last_audio_pos)}/{_fmt_clock(duration)}  "
                    f"· trascorso {_fmt_duration(elapsed)}  "
                    f"· stimato restante {_fmt_duration(eta)}",
                )

        total_elapsed = time.monotonic() - start_time
        log.info("Trascrizione completata: %d segmenti in %.1fs.",
                 len(result.segments), total_elapsed)

        # Ri-segmentazione: spezza i segmenti troppo lunghi (durata o caratteri)
        # usando i word-level timestamp, per sottotitoli più leggibili.
        before = len(result.segments)
        result.segments = resegment(result.segments)
        log.info("Ri-segmentazione: %d -> %d segmenti.", before, len(result.segments))

        if progress:
            progress(1.0, f"Trascrizione completata in {_fmt_duration(total_elapsed)}.")
        return result


def resegment(segments: list[Segment]) -> list[Segment]:
    """
    Suddivide i segmenti che superano MAX_SEG_DURATION o che sarebbero troppo
    lunghi da leggere, sfruttando i tempi parola per parola. Rinumera l'indice.
    Se un segmento non ha word-level, lo lascia invariato.
    """
    out: list[Segment] = []
    for seg in segments:
        too_long = (seg.end - seg.start) > MAX_SEG_DURATION
        too_wide = len(seg.text) > MAX_CHARS_PER_LINE * MAX_LINES
        if not seg.words or not (too_long or too_wide):
            out.append(seg)
            continue

        # Accumula parole finché non si supera durata o larghezza, poi spezza.
        chunk: list[Word] = []
        chunk_chars = 0
        for w in seg.words:
            add_len = len(w.text) + 1
            dur = (w.end - chunk[0].start) if chunk else 0.0
            if chunk and (dur > MAX_SEG_DURATION
                          or chunk_chars + add_len > MAX_CHARS_PER_LINE * MAX_LINES):
                out.append(_chunk_to_segment(chunk))
                chunk, chunk_chars = [], 0
            chunk.append(w)
            chunk_chars += add_len
        if chunk:
            out.append(_chunk_to_segment(chunk))

    # Fonde i micro-segmenti (più corti di MIN_SEG_DURATION) col vicino, se la
    # fusione non supera i limiti di durata/larghezza. Evita sottotitoli-lampo.
    merged = _merge_tiny(out)
    for i, s in enumerate(merged, 1):
        s.index = i
    return merged


def _merge_tiny(segments: list[Segment]) -> list[Segment]:
    """Fonde i segmenti più brevi di MIN_SEG_DURATION col precedente o, in
    mancanza, col successivo, se la fusione rispetta i limiti."""
    def _fits(a: Segment, b: Segment) -> bool:
        return ((b.end - a.start) <= MAX_SEG_DURATION
                and len(a.text) + len(b.text) + 1 <= MAX_CHARS_PER_LINE * MAX_LINES)

    out: list[Segment] = []
    i = 0
    n = len(segments)
    while i < n:
        seg = segments[i]
        short = (seg.end - seg.start) < MIN_SEG_DURATION
        if short and out and _fits(out[-1], seg):
            prev = out[-1]
            prev.end = seg.end
            prev.text = (prev.text + " " + seg.text).strip()
            prev.words = prev.words + seg.words
            i += 1
            continue
        if short and i + 1 < n and _fits(seg, segments[i + 1]):
            nxt = segments[i + 1]
            merged = Segment(index=0, start=seg.start, end=nxt.end,
                             text=(seg.text + " " + nxt.text).strip(),
                             words=seg.words + nxt.words)
            out.append(merged)
            i += 2
            continue
        out.append(seg)
        i += 1
    return out


def _chunk_to_segment(words: list[Word]) -> Segment:
    text = " ".join(w.text for w in words).strip()
    return Segment(index=0, start=words[0].start, end=words[-1].end,
                   text=text, words=list(words))


def write_subtitles(result: TranscriptionResult, output_path: str,
                    fmt: str = "srt") -> str:
    """Scrive i segmenti su file nel formato richiesto ('srt', 'vtt' o 'txt')."""
    fmt = fmt.lower()
    if fmt == "vtt":
        content = segments_to_vtt(result.segments)
    elif fmt == "txt":
        content = segments_to_text(result.segments)
    else:
        content = segments_to_srt(result.segments)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return output_path


def write_subtitles_multi(result: TranscriptionResult, out_dir: str, base: str,
                          lang: str, formats: list[str]) -> list[str]:
    """Scrive gli stessi sottotitoli in più formati. Ritorna i path prodotti."""
    import os as _os
    paths = []
    for fmt in formats:
        p = _os.path.join(out_dir, f"{base}.{lang}.{fmt}")
        write_subtitles(result, p, fmt=fmt)
        paths.append(p)
    return paths


def has_ffmpeg() -> bool:
    """True se un eseguibile ffmpeg è disponibile (per l'hardsub)."""
    import shutil
    return shutil.which("ffmpeg") is not None


def burn_subtitles(video_path: str, srt_path: str, output_path: str,
                   progress: Optional[Callable[[float, str], None]] = None) -> str:
    """
    Masterizza (hardsub) i sottotitoli SRT dentro il video, producendo un nuovo
    file. Richiede ffmpeg nel PATH. Solleva RuntimeError se ffmpeg manca o fallisce.
    """
    import subprocess
    if not has_ffmpeg():
        raise RuntimeError(
            "ffmpeg non trovato: serve per masterizzare i sottotitoli nel video. "
            "Installa ffmpeg e riprova (l'estrazione sottotitoli non lo richiede)."
        )
    if progress:
        progress(0.0, "Masterizzo i sottotitoli nel video (ffmpeg)...")

    # Il filtro subtitles vuole il path con escape particolare su Windows.
    srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")
    vf = f"subtitles='{srt_escaped}'"
    cmd = ["ffmpeg", "-y", "-i", video_path, "-vf", vf,
           "-c:a", "copy", output_path]
    log.info("Hardsub: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log.error("ffmpeg fallito: %s", proc.stderr[-800:])
        raise RuntimeError("Masterizzazione fallita. Vedi il log per i dettagli.")
    if progress:
        progress(1.0, "Video con sottotitoli creato.")
    return output_path


def segments_to_text(segments: Iterable[Segment]) -> str:
    """
    Trascrizione come testo leggibile (senza timestamp), formattata in
    paragrafi. Utile per avere il parlato come documento, oltre ai sottotitoli.
    """
    text = " ".join(seg.text.strip() for seg in segments if seg.text.strip())
    # Spezza in paragrafi ogni ~4 frasi per leggibilità.
    import re
    sentences = re.split(r"(?<=[.!?])\s+", text)
    paragraphs, chunk = [], []
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        chunk.append(s)
        if len(chunk) >= 4:
            paragraphs.append(" ".join(chunk))
            chunk = []
    if chunk:
        paragraphs.append(" ".join(chunk))
    return "\n\n".join(paragraphs) + "\n"
