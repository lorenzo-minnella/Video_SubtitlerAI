# Distribuzione su Windows + Google Drive

## 1. Perché serve una macchina Windows per la build

PyInstaller **non fa cross-compile**: un `.exe` per Windows va generato **su Windows**.
Dal Mac posso preparare tutto il codice e lo script di build, ma il passo finale
(`build_windows.bat`) va eseguito su un PC Windows (o una VM Windows).

## 2. Build su Windows

1. Copia la cartella `10. Video_SubtitlerAI` sul PC Windows.
2. Installa **Python 3.10+** (da python.org, spunta "Add to PATH").
3. Doppio clic su **`build_windows.bat`** (o eseguilo da `cmd`).
4. Al termine trovi:
   - l'app in `dist\VideoSubtitlerAI\VideoSubtitlerAI.exe`
   - lo ZIP di distribuzione `VideoSubtitlerAI-<versione>-win64.zip` già pronto.

> **ffmpeg NON serve.** faster-whisper decodifica l'audio con PyAV (il pacchetto
> `av`), che include già le librerie FFmpeg; `build_windows.bat` le impacchetta
> nell'`.exe` con `--collect-all av`. Il pacchetto è quindi autosufficiente.

## 3. Pacchetto da distribuire

Lo ZIP `VideoSubtitlerAI-<versione>-win64.zip` prodotto dalla build contiene tutto
il necessario. L'utente finale scompatta lo ZIP e avvia `VideoSubtitlerAI.exe`:
nessuna installazione di Python né di ffmpeg.

## 4. Upload su Google Drive (rclone)

Seguendo lo standard delle app personali, ogni app ha la sua cartella sotto
`13. KIRO/APP/` su Drive. Per questa app la cartella proposta è:

```
13. KIRO/APP/<N>. VideoSubtitlerAI/
```

Procedura (da macOS, dove rclone è configurato con il remote `gdrive`):

```bash
export PATH="$HOME/.homebrew/bin:$PATH"

# 1. individua/elenca le cartelle app su Drive
rclone lsd gdrive:"13. KIRO/APP/"

# 2. rimuovi la versione precedente dello ZIP in quella cartella
APP_DIR="13. KIRO/APP/<N>. VideoSubtitlerAI"
rclone delete gdrive:"$APP_DIR/" --include "VideoSubtitlerAI-*.zip"

# 3. carica lo ZIP corrente
rclone copy "VideoSubtitlerAI-<versione>-win64.zip" gdrive:"$APP_DIR/" -P

# 4. verifica che resti solo lo ZIP corrente
rclone ls gdrive:"$APP_DIR/" | grep -i VideoSubtitlerAI
```

Deve restare **una sola** versione dello ZIP nella cartella dell'app.

## 5. Versionamento

A ogni rilascio: versione `+0.1` (1.0 → 1.1 → ...), ZIP rinominato di
conseguenza, e la versione precedente rimossa da Drive.

## 6. Installazione lato utente (Windows)

1. Scarica lo ZIP dalla cartella Drive dell'app.
2. Estrai la cartella in una posizione a scelta.
3. Avvia `VideoSubtitlerAI.exe`.
4. Al primo utilizzo, il modello Whisper viene scaricato automaticamente
   (serve connessione solo la prima volta).
