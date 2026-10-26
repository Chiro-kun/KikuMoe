# KikuMoe v1.11.0

Player desktop per [LISTEN.moe](https://listen.moe) basato su PyQt6.  
Supporta stream J-POP e K-POP in formato Vorbis o MP3, con backend audio FFmpeg (predefinito), MPV e VLC (fallback).

---

## Indice

- [Requisiti](#requisiti)
- [Installazione](#installazione)
- [Avvio](#avvio)
- [Interfaccia](#interfaccia)
- [Funzionalità](#funzionalità)
- [Impostazioni](#impostazioni)
- [Scorciatoie da tastiera](#scorciatoie-da-tastiera)
- [Tray di sistema](#tray-di-sistema)
- [Sleep timer](#sleep-timer)
- [Console sviluppatore](#console-sviluppatore)
- [Risoluzione problemi](#risoluzione-problemi)
- [Build](#build)

---

## Requisiti

| Componente | Versione minima | Note |
|---|---|---|
| Python | 3.8+ | Consigliato 3.10+ |
| FFmpeg | qualsiasi | Deve essere nel PATH. Alternativa: MPV o VLC |
| MPV | qualsiasi | Secondo fallback; richiede `libmpv` installato nel sistema |
| VLC Desktop | 3.x | Ultimo fallback se FFmpeg e MPV non sono disponibili |

**Dipendenze Python** (gestite via `poetry`):

```
PyQt6 >= 6.4.0
websocket-client >= 1.6.0
python-vlc >= 3.0.0
python-mpv >= 1.0.0
pyaudio >= 0.2.11
```

> **Nota su MPV:** `python-mpv` richiede `libmpv` installato nel sistema (`sudo apt install libmpv-dev` su Debian/Ubuntu, `sudo pacman -S mpv` su Arch).  
> **Nota su VLC:** Se usi il backend VLC, l'architettura di VLC deve corrispondere a quella di Python (entrambi x64 o entrambi x86).

---

## Installazione

### 1. Clona o scarica il repository

```bash
git clone https://git.alsogamer.com/chiro/kikumoe.git
cd kikumoe
```

### 2. Installa FFmpeg (se non è già nel PATH)

**Windows** — esegui lo script incluso (richiede privilegi amministratore):

```powershell
.\install-ffmpeg.bat
```

Dopo l'installazione **riavvia Windows** per aggiornare il PATH.

**Linux:**
```bash
sudo apt install ffmpeg        # Debian/Ubuntu
sudo pacman -S ffmpeg          # Arch
sudo dnf install ffmpeg        # Fedora
```

**macOS:**
```bash
brew install ffmpeg
```

> Se non puoi installare FFmpeg, usa il backend MPV (consigliato su Linux) o VLC, configurabile nelle [Impostazioni](#impostazioni).

### 3. Installa le dipendenze Python

```bash
poetry install
```

---

## Avvio

Dalla root del repository:

```bash
python KikuMoe.py

# Per avviare in modalità debug (mostra i log interni)
# Nota: in questa modalità i log di sistema (ALSA, VLC) non vengono silenziati
python KikuMoe.py --debug
```

---

## Interfaccia

La finestra principale è composta da tre sezioni:

**Header** — selettori Canale, Formato e Lingua nella parte alta della finestra.

**Now Playing** — mostra copertina album, titolo e artista del brano in corso, con barra di avanzamento e durata rimanente.

**Controlli** — pulsanti Play/Pausa, Stop, cursore volume e pulsante Muto. Il pulsante di Stop forzato interrompe immediatamente il processo audio in caso di blocco.

---

## Funzionalità

### Canali e formati

| Canale | Formato | URL stream |
|---|---|---|
| J-POP | Vorbis | `https://listen.moe/stream` |
| J-POP | Opus | `https://listen.moe/opus` |
| J-POP | MP3 | `https://listen.moe/fallback` |
| K-POP | Vorbis | `https://listen.moe/kpop/stream` |
| K-POP | Opus | `https://listen.moe/kpop/opus` |
| K-POP | MP3 | `https://listen.moe/kpop/fallback` |

Cambiare canale o formato riavvia automaticamente lo stream.

### Backend audio

**FFmpeg (predefinito):** avvia un sottoprocesso FFmpeg che decodifica lo stream e ne passa l'audio a PyAudio. Permette la selezione del dispositivo di uscita.

**MPV (secondo fallback):** usa le binding `python-mpv` (libmpv). Si attiva automaticamente se FFmpeg non è disponibile. Consigliato su Linux dove MPV è tipicamente installato nel sistema.

**VLC (ultimo fallback):** usa le binding `python-vlc`. Si attiva automaticamente se né FFmpeg né MPV sono disponibili.

### Metadati in tempo reale

I metadati (titolo, artista, durata, copertina) arrivano via WebSocket dal gateway LISTEN.moe (`wss://listen.moe/gateway_v2`). La copertina viene scaricata in background e memorizzata nella cache per tutta la sessione.

### Timer sessione

Mostra il tempo trascorso dall'avvio dell'applicazione. Può essere abilitato/disabilitato dalle Impostazioni.

---

## Impostazioni

Apri le Impostazioni dal menu del tray o dal pulsante nella finestra principale.

| Impostazione | Descrizione |
|---|---|
| Lingua | Italiano o English |
| Canale predefinito | J-POP o K-POP |
| Formato predefinito | Vorbis, Opus o MP3 |
| Riproduzione automatica | Avvia lo stream all'apertura dell'app |
| Backend audio | `Automatico` (FFmpeg → MPV → VLC), `FFmpeg`, `MPV` o `VLC` |
| Uscita audio | Dispositivo di output (enumerato da PyAudio) |
| Percorso libVLC | Cartella contenente `libvlc.dll` (es. `C:/Program Files/VideoLAN/VLC`) |
| Network caching | Buffer di rete in millisecondi (100–5000 ms, default 1000) |
| Tray: abilita icona | Mostra l'icona nell'area di notifica |
| Tray: notifiche | Notifica di sistema al cambio brano |
| Tray: nascondi su minimizza | Minimizza nella tray invece della barra delle applicazioni |
| Sleep timer: stop a scadenza | Interrompe la riproduzione allo scadere del timer |
| Timer sessione | Mostra il contatore del tempo di sessione |
| Console sviluppatore | Abilita la finestra di log interno |
| Filtro messaggi `[DEV]` | Mostra anche i messaggi di debug interni |

Le impostazioni vengono salvate tramite `QSettings` (registro di sistema su Windows).

---

## Scorciatoie da tastiera

| Tasto | Azione |
|---|---|
| `Space` | Play / Pausa |
| `S` | Stop |
| `M` | Muto / Unmute |
| `↑` oppure `+` oppure `=` | Volume +5% |
| `↓` oppure `-` | Volume −5% |

---

## Tray di sistema

L'icona nella tray offre accesso rapido a:

- Brano in riproduzione e tempo di sessione
- Play/Pausa, Stop
- Muto/Unmute
- Cambio canale e formato
- Mostra/Nascondi finestra
- Impostazioni
- Esci

Le notifiche di sistema mostrano il titolo e l'artista ad ogni cambio brano (se abilitate nelle Impostazioni).

---

## Sleep timer

Il sleep timer interrompe la riproduzione dopo un numero di minuti configurabile.

1. Imposta i minuti nel campo Sleep nella finestra principale.
2. Clicca **Start** per avviare il conto alla rovescia.
3. Negli ultimi 15 secondi il volume scende gradualmente a zero.
4. Se l'opzione **Stop a scadenza** è attiva nelle Impostazioni, lo stream si ferma automaticamente; altrimenti viene ripristinato il volume normale.

---

## Console sviluppatore

La console sviluppatore mostra i log interni dell'applicazione in tempo reale.

- Attivala dalle Impostazioni → *Console sviluppatore*.
- Puoi filtrare per livello (DEBUG, INFO, WARNING, ERROR) e mostrare/nascondere i messaggi `[DEV]`.
- I log possono essere copiati negli appunti o salvati su file.
- Usa **Pausa** per bloccare lo scorrimento e analizzare i messaggi.

---

## Risoluzione problemi

**FFmpeg non trovato dopo aver eseguito install-ffmpeg.bat**

Riavvia Windows per aggiornare il PATH di sistema.

Verifica manualmente:
```bash
ffmpeg -version
```

**Nessun suono / dispositivo audio non trovato**

Apri le Impostazioni e seleziona il dispositivo di uscita corretto dall'elenco.

**Backend MPV: errore di inizializzazione**

- Installa `libmpv` nel sistema (`sudo apt install libmpv-dev` su Debian/Ubuntu, `sudo pacman -S mpv` su Arch, `sudo dnf install mpv-libs` su Fedora).
- Verifica che `python-mpv` sia installato: `pip install python-mpv`.

**Backend VLC: errore di inizializzazione**

- Verifica che l'architettura di VLC corrisponda a quella di Python (`python -c "import struct; print(struct.calcsize('P')*8)"` restituisce 32 o 64).
- Imposta manualmente il percorso nelle Impostazioni (cartella che contiene `libvlc.dll`).

**Stream non si avvia / si blocca**

- Verifica la connessione a internet.
- Prova a cambiare formato (Vorbis ↔ MP3).
- Aumenta il **Network caching** nelle Impostazioni (es. 2000–3000 ms).
- Usa il pulsante **Stop forzato** per resettare il processo audio, poi riprova.

In caso di errore fatale l'applicazione scrive un log in:

**Windows:**
```
%LOCALAPPDATA%\KikuMoe\crash.log
```

**Linux:**
```
~/.local/share/KikuMoe/crash.log
```

---

## Build

La configurazione PyInstaller si trova in `kikumoe.spec`.

### Windows

```powershell
.\build.ps1
```

Produce `dist\KikuMoe-<versione>.exe`.

Se VLC non si trova nel percorso predefinito, imposta la variabile d'ambiente prima di eseguire il build:

```powershell
$env:VLC_DIR = "C:\Percorso\A\VLC"
.\build.ps1
```

### Linux

```bash
./build.sh
bash packaging/linux/build-appimage.sh   # Opzionale: pacchettizza in AppImage
```

Produce `dist/KikuMoe-<versione>`. VLC non viene incluso nel binario; deve essere installato a livello di sistema (`sudo pacman -S vlc`, `sudo apt install vlc`, ecc.) e verrà trovato automaticamente da `python-vlc`.

> [!NOTE]
> **Compatibilità glibc (AppImage precompilata):**  
> A partire dalla versione 1.11.0, l'AppImage precompilata rilasciata su GitHub viene generata su Ubuntu 26.04 LTS (glibc >= 2.41). Se utilizzi una distribuzione con una versione di glibc inferiore (ad esempio Ubuntu 22.04 LTS, Debian 12 o precedenti), l'AppImage precompilata potrebbe non avviarsi a causa della versione di glibc richiesta dal sistema.  
> In questo caso, per continuare a usare KikuMoe è sufficiente compilare il pacchetto direttamente sulla propria distribuzione clonando il repository ed eseguendo `./build.sh` (e opzionalmente `bash packaging/linux/build-appimage.sh`): il binario o AppImage generato utilizzerà nativamente la versione di glibc della propria macchina.

---

## Crediti

Sviluppato da:
- **Chiro**
- **alsog**

Homepage del progetto: [git.alsogamer.com/chiro/KikuMoe](https://git.alsogamer.com/chiro/KikuMoe)

## Licenza

Questo progetto è distribuito sotto licenza **MIT**. Consulta il file `LICENSE` per i dettagli.
