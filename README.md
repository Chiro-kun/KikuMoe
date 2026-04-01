# KikuMoe

Player desktop per LISTEN.moe basato su PyQt5, con backend audio predefinito FFmpeg e fallback VLC.

## Requisiti
- Python 3.8+
- FFmpeg installato e disponibile nel PATH (consigliato)
- Se FFmpeg non è installato, esegui prima `KikuMoe\FFMPEG.bat` (richiede privilegi amministratore)
- In alternativa a FFmpeg: VLC Desktop installato (architettura coerente con Python) oppure percorso `libvlc.dll` impostato nelle Impostazioni

## Installazione
1. Clona o scarica il repository.
2. Se non hai FFmpeg nel PATH, esegui:

```powershell
./KikuMoe/FFMPEG.bat
```

3. Installa le dipendenze:

```bash
pip install -r requirements.txt
```

## Avvio
Dalla root del repository:

```bash
python KikuMoe/KikuMoe.py
```

## Funzionalità principali
- Riproduzione stream J-POP/K-POP (Vorbis/MP3)
- Controlli Play, Pausa, Stop, Volume, Muto
- Tray icon con menu rapido
- Impostazioni IT/EN
- Riavvio automatico stream quando cambi canale/formato/backend
- Sleep timer e timer sessione
- Console sviluppatore opzionale

## Impostazioni disponibili
- Lingua
- Canale e formato di default
- Uscita audio
- Percorso libVLC
- Network caching (ms)
- Avvio automatico
- Opzioni tray (abilitazione, notifiche, hide on minimize)
- Sleep timer: stop a scadenza
- Timer sessione
- Console sviluppatore + filtro messaggi `[DEV]`

## Scorciatoie
- `Space`: Play/Pausa
- `S`: Stop
- `M`: Muto/Unmute
- `↑` / `+`: Volume su
- `↓` / `-`: Volume giù

## Risoluzione problemi
- Verifica FFmpeg:

```bash
ffmpeg -version
```

- Se FFmpeg non viene rilevato dopo `FFMPEG.bat`, riavvia Windows (refresh PATH).
- Se usi VLC fallback, imposta nelle Impostazioni la cartella che contiene `libvlc.dll` (es. `C:/Program Files/VideoLAN/VLC`).

## Build Windows (onefile)
Usa solo lo script di build dalla root:

```powershell
./build.ps1
```

Output:
- `dist\KikuMoe-1.9.0.exe`

Se VLC non è nel path predefinito in fase di build, imposta prima:

```powershell
$env:VLC_DIR = "C:\Percorso\VLC"
```
