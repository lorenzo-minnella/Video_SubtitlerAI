# 🎬 Video SubtitlerAI

Genera **sottotitoli** (`.srt` / `.vtt`) con timestamp a partire da un video o audio,
usando **faster-whisper** in locale. Gratuito, offline, nessuna API key.

- 🧠 Riconoscimento vocale AI (faster-whisper) con **timestamp per segmento**
- 🌍 Lingue: **inglese** e **italiano** + **rilevamento automatico**
- 🔁 **Traduzione** offline dei sottotitoli (es. inglese → italiano) via Argos Translate
- 🖥️ **Interfaccia grafica** scura e pulita (CustomTkinter) con drag & drop
- 📄 Output **.srt** o **.vtt**
- 🪟 **Installabile su Windows** come eseguibile `.exe`

---

## Interfaccia

1. Trascina il video nella finestra (o «Sfoglia»).
2. Scegli **lingua audio** (o lascia *Rileva automaticamente*), **qualità** del modello,
   l'eventuale **traduzione** e il **formato** file.
3. Premi **Genera sottotitoli**. Il file viene salvato accanto al video
   (es. `film.en.srt`).

---

## Requisiti

- Python 3.9+ (per eseguire da sorgente; **non serve** se usi l'`.exe` su Windows)
- **ffmpeg NON è richiesto**: faster-whisper decodifica l'audio con PyAV (il
  pacchetto `av`), che include già le librerie FFmpeg. Niente da installare.

Al primo utilizzo il modello Whisper viene **scaricato automaticamente** (una tantum).

---

## Esecuzione da sorgente

```bash
cd "10. Video_SubtitlerAI"
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# GUI
python app_gui.py

# oppure da riga di comando
python cli.py video.mp4 --model small
python cli.py video.mp4 --language en --translate it --format srt
```

### Opzioni CLI

| Flag | Descrizione | Default |
|------|-------------|---------|
| `-l, --language` | Lingua audio (`auto`, `en`, `it`, ...) | `auto` |
| `-m, --model` | Modello (`tiny`/`base`/`small`/`medium`/`large-v3`) | `small` |
| `-f, --format` | Formato output (`srt`/`vtt`) | `srt` |
| `-t, --translate` | Traduci i sottotitoli in questa lingua (`it`, `en`, ...) | nessuna |
| `-o, --output` | Path output (solo singolo file) | accanto al video |

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
10. Video_SubtitlerAI/
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
