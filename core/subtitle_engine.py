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
    "large-v3": "Qualità massima, il più lento (~10 GB)",
}

# Lingue esposte in UI (codice ISO -> etichetta leggibile)
SUPPORTED_LANGUAGES = {
    "auto": "Rileva automaticamente",
    "en": "Inglese",
    "it": "Italiano",
}

# Lingue di destinazione per la traduzione
TRANSLATION_TARGETS = {
    "none": "Nessuna traduzione",
    "it": "Italiano",
    "en": "Inglese",
}


@dataclass
class Segment:
    """Un segmento di sottotitolo con tempi in secondi."""
    index: int
    start: float
    end: float
    text: str


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


def segments_to_srt(segments: Iterable[Segment]) -> str:
    """Serializza i segmenti in formato SubRip (.srt)."""
    lines: list[str] = []
    for seg in segments:
        lines.append(str(seg.index))
        lines.append(
            f"{_format_timestamp(seg.start)} --> {_format_timestamp(seg.end)}"
        )
        lines.append(seg.text.strip())
        lines.append("")  # riga vuota separatore
    return "\n".join(lines).strip() + "\n"


def segments_to_vtt(segments: Iterable[Segment]) -> str:
    """Serializza i segmenti in formato WebVTT (.vtt)."""
    lines: list[str] = ["WEBVTT", ""]
    for seg in segments:
        lines.append(
            f"{_format_timestamp(seg.start, vtt=True)} --> "
            f"{_format_timestamp(seg.end, vtt=True)}"
        )
        lines.append(seg.text.strip())
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
        progress: Optional[Callable[[float, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> TranscriptionResult:
        """
        Trascrive (o traduce verso l'inglese, se task='translate') il file media.

        Args:
            media_path: percorso del video/audio.
            language: codice lingua sorgente o 'auto'.
            task: 'transcribe' (lingua originale) o 'translate' (-> inglese, nativo Whisper).
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
        segments_iter, info = model.transcribe(
            media_path,
            language=lang_arg,
            task=task,
            vad_filter=True,  # rimuove silenzi lunghi -> segmenti più puliti
            beam_size=5,
        )

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
            result.segments.append(
                Segment(index=idx, start=float(seg.start), end=float(seg.end), text=text)
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
        if progress:
            progress(1.0, f"Trascrizione completata in {_fmt_duration(total_elapsed)}.")
        return result


def write_subtitles(result: TranscriptionResult, output_path: str,
                    fmt: str = "srt") -> str:
    """Scrive i segmenti su file nel formato richiesto ('srt' o 'vtt')."""
    fmt = fmt.lower()
    if fmt == "vtt":
        content = segments_to_vtt(result.segments)
    else:
        content = segments_to_srt(result.segments)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return output_path
