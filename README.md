# 🎬 Video SubtitlerAI

# 🎬 Video SubtitlerAI

Genera **sottotitoli** (`.srt` / `.vtt` / `.txt`) con timestamp a partire da uno o più
video/audio, usando **faster-whisper** in locale. Gratuito, offline, nessuna API key.

- 🧠 Riconoscimento vocale AI (faster-whisper) con **timestamp parola per parola**
- ✂️ **Spezzatura righe intelligente** (max ~42 caratteri, 2 righe) e **ri-segmentazione**
  automatica: sottotitoli brevi e leggibili, standard professionale
- 🌍 Lingue: **inglese, italiano, spagnolo, francese, tedesco, portoghese** +
  **rilevamento automatico**
- 🔁 **Traduzione** offline via Argos Translate: salva **SEMPRE sia l'originale sia
  il tradotto**
- 👀 **Anteprima e modifica** dei segmenti prima del salvataggio
- 🔥 **Masterizzazione (hardsub)**: crea un video con i sottotitoli impressi (se ffmpeg presente)
- 📦 **Coda multi-file** (batch) + aggiunta di **cartelle intere**
- 📄 **Formati multipli** in un colpo: `.srt`, `.vtt`, `.txt`
- ⚡ **Preset velocità** (Qualità / Veloce) e modello `distil-large-v3` (veloce e accurato)
- ⚙️ **Impostazioni persistenti** (ricorda modello, lingua, cartella, tema…)
- 🌗 **Tema chiaro/scuro**, 📂 "Apri cartella" a fine lavoro, 🔔 notifica di sistema
- 🪟 **Installabile su Windows** come eseguibile `.exe`

---

## Interfaccia

1. Trascina uno o più video nella finestra (o «＋ Aggiungi»).
2. Scegli **lingua audio** (o *Rileva automaticamente*), **qualità** del modello,
   **velocità**, l'eventuale **traduzione**, il **formato** e la **cartella output**.
3. Premi **Genera sottotitoli**. I file vengono salvati con il suffisso della lingua
   (es. `film.en.srt`). Con la traduzione attiva ottieni sia `film.en.srt`
   sia `film.it.srt`.

---

## Requisiti

- Python 3.9+ (per eseguire da sorgente; **non serve** se usi l'`.exe` su Windows)
- **ffmpeg NON è richiesto**: faster-whisper decodifica l'audio con PyAV (il
  pacchetto `av`), che include già le librerie FFmpeg. Niente da installare.

Al primo utilizzo il modello Whisper viene **scaricato automaticamente** (una tantum).

---

## Esecuzione da sorgente

```bash
cd "2. Video_SubtitlerAI"
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# GUI
python app_gui.py

# oppure da riga di comando
python cli.py video.mp4 --model small
python cli.py video.mp4 --language en --translate it --format srt   # orig + tradotto
python cli.py *.mp4 --model small --fast                            # batch, modalità veloce
```

### Opzioni CLI

| Flag | Descrizione | Default |
|------|-------------|---------|
| `-l, --language` | Lingua audio (`auto`, `en`, `it`, `es`, `fr`, `de`, `pt`) | `auto` |
| `-m, --model` | Modello (`tiny`/`base`/`small`/`medium`/`distil-large-v3`/`large-v3`) | `small` |
| `-f, --format` | Uno o più formati (`srt vtt txt`) | `srt` |
| `-t, --translate` | Traduci anche in questa lingua (salva orig + tradotto) | nessuna |
| `--fast` | Modalità rapida (beam=1): più veloce, qualità lievemente inferiore | off |
| `--no-wrap` | Disabilita la spezzatura righe intelligente | off |
| `--burn` | Masterizza i sottotitoli nel video (richiede ffmpeg) | off |
| `-d, --output-dir` | Cartella di output | accanto a ogni file |

---

## Modelli

| Modello | Qualità | Velocità | Note |
|---------|---------|----------|------|
| `tiny` / `base` | ⭐ / ⭐⭐ | ⚡⚡⚡⚡ | per prove rapide |
| `small` | ⭐⭐⭐ | ⚡⚡⚡ | **default**, buon compromesso |
| `medium` | ⭐⭐⭐⭐ | ⚡⚡ | qualità alta |
| `large-v3` | ⭐⭐⭐⭐⭐ | ⚡ | qualità massima, richiede più RAM/tempo |

Su CPU conviene `small`/`medium`; con GPU NVIDIA (CUDA) l'app la usa in automatico.

---

## Traduzione

- Whisper traduce **nativamente solo verso l'inglese** (`task=translate`).
- Per tradurre verso l'**italiano** (o altre lingue) si usa **Argos Translate** (offline):
  Whisper trascrive nella lingua originale, poi i sottotitoli vengono tradotti.
- Al primo uso di una coppia di lingue, Argos scarica il relativo pacchetto (una tantum).

---

## Creare l'eseguibile per Windows

Su una macchina **Windows**, dentro la cartella del progetto:

```bat
build_windows.bat
```

Produce `dist\VideoSubtitlerAI\VideoSubtitlerAI.exe`. Per distribuirlo, comprimi la
cartella `dist\VideoSubtitlerAI` in uno ZIP.

Lo script genera anche lo ZIP `VideoSubtitlerAI-<versione>-win64.zip`, già pronto
per la distribuzione (ffmpeg incluso via PyAV, nessuna installazione sul PC utente).

> Nota: l'eseguibile va costruito **su Windows** (PyInstaller non fa cross-compile da
> macOS a Windows). Vedi `DISTRIBUZIONE.md` per i dettagli e l'upload su Google Drive.

---

## Log di diagnostica

L'app scrive un file **`video_subtitler.log`** accanto all'eseguibile (o alla
cartella del progetto, da sorgente). Contiene i tempi di ogni fase (caricamento
modello, analisi, trascrizione, traduzione), la velocità di elaborazione e gli
eventuali errori col dettaglio completo. Se qualcosa "sembra bloccato" o va in
errore, quel file dice cosa sta succedendo.

## Struttura

```
2. Video_SubtitlerAI/
├─ app_gui.py              # interfaccia grafica
├─ cli.py                  # versione riga di comando
├─ core/
│  └─ subtitle_engine.py   # motore trascrizione + traduzione + export SRT/VTT
├─ assets/icon/icon.svg    # icona sorgente (rigenerabile)
├─ tools/make_ico.py       # genera icon.ico dalla SVG
├─ build_windows.bat       # build .exe per Windows
├─ requirements.txt
├─ README.md
└─ DISTRIBUZIONE.md        # come rilasciare su Google Drive
```
