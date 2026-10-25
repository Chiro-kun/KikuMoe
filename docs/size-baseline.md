# KikuMoe Linux Build Size Baseline & Optimization Log

## Contesto e Metriche di Riferimento (Baseline)

Prima delle ottimizzazioni introdotte nel piano di riproducibilità (`linux-build-opx`), la pipeline di packaging Linux presentava le seguenti dimensioni e criticità architetturali:

### 1. Dimensioni Misurate Pre-Ottimizzazione
- **Eseguibile PyInstaller (`onefile`)**: ~273 MB
- **AppImage Finale (`x86_64`)**: ~200-210 MB
- **Binario statico FFmpeg (`gpl` unstripped da yt-dlp)**: ~92 MB (non compresso)
- **Tempo di avvio e overhead runtime**: Doppio disimballaggio all'avvio (squashfs AppImage montato con FUSE / estratto + PyInstaller bootloader che estrae l'intero payload in `/tmp/_MEIxxxxxx`).

### 2. Cause Principali del Gonfiore (Size Bloat)
1. **Doppia Inclusione di FFmpeg**:
   - `build.sh` copiava `packaging/linux/ffmpeg` in `dist/ffmpeg`.
   - `kikumoe.spec` includeva automaticamente o implicitamente binari statici senza escluderli da `a.binaries` in modalità `onefile`.
   - `build-appimage.sh` copiava nuovamente FFmpeg in `$APPDIR/usr/bin/ffmpeg`.
2. **PyInstaller `onefile` dentro AppImage**:
   - Una AppImage è già un filesystem compresso ad alte prestazioni (SquashFS).
   - Inserire un file `onefile` autolimitato all'interno di una AppImage forzava una doppia compressione inutile e raddoppiava i tempi di avvio e lo spazio su disco temporaneo (`/tmp`).
3. **Moduli PyQt6 Inutilizzati**:
   - Bundling predefinito di moduli Qt non impiegati dal player: `QtQml`, `QtQuick`, `QtQuickWidgets`, `QtPdf`, `QtPdfWidgets`, `QtSql`, `QtXml`, `QtWebEngine*`, `QtBluetooth`, `QtSensors`, `QtPositioning`, `QtPrintSupport`, `QtDesigner`, `QtHelp`, `QtCharts`, `QtOpenGLWidgets`.
   - Traduzioni Qt incorporate in blocco in `PyQt6/Qt6/translations` (~15-20 MB di file `.qm` non necessari).
4. **Build FFmpeg `gpl` Non Ottimizzata**:
   - Download da branch instabile `latest` di una build `gpl` contenente codec video/encoder non utilizzati da KikuMoe (player solo audio).
   - Assenza di stripping dei simboli (`strip --strip-unneeded`).
5. **Algoritmo di Compressione Squashfs**:
   - `appimagetool` con compressione gzip predefinita a livello standard invece di `zstd` con livello massimo (19).

---

## Piano di Riduzione e Risultati

| Componente | Configurazione Baseline | Nuova Configurazione | Risparmio Previsto |
|---|---|---|---|
| **Modalità PyInstaller** | `onefile` (273 MB) | `onedir` (`dist/KikuMoe/`) | Elimina duplicazione / estrazione `/tmp` |
| **FFmpeg Backend** | `gpl` latest unstripped (~92 MB) | `linux64-lgpl` pinned + stripped (~35-42 MB) | ~50 MB risparmiati |
| **Compressione AppImage** | gzip standard | `zstd -Xcompression-level 19` | Compressione superiore + decompress. ultra-veloce |
| **Moduli Qt & Traduzioni** | Tutti i moduli PyQt6 inclusi | Exclude mirati + potatura translations in `a.datas` | ~30-45 MB risparmiati |
| **Dimensione AppImage Stimata** | ~200-210 MB | **~75-95 MB** | **Riduzione >50%** |

---

## Dettaglio Implementazione e Verifiche per Task

### Task 0 — Baseline e Documentazione
- Creazione della presente analisi in `docs/size-baseline.md`.
- Censimento dei pesi storici di build e delle cause del footprint eccessivo.

### Task 1 — `packaging/linux/fetch-ffmpeg.sh`
- **Script**: Bash con `set -euo pipefail`.
- **Repository e Tag**: Fissato a `BtbN/FFmpeg-Builds` con tag `autobuild-2026-10-22-13-06` (fornisce release `linux64-lgpl` statiche, a differenza del fork `yt-dlp/FFmpeg-Builds` che compila esclusivamente `gpl`).
- **Verifica e Ottimizzazione**:
  - Download di `checksums.sha256` e verifica rigorosa con `sha256sum -c`.
  - Estrazione esclusiva di `*/bin/ffmpeg`.
  - Esecuzione di `strip --strip-unneeded` per rimuovere tabelle di debug ed ELF headers ridondanti.
  - Installazione con permessi 755 in `packaging/linux/ffmpeg`.
  - Idempotenza completa: se il binario esiste ed è eseguibile, l'operazione termina con successo immediato.
- **Integrazione**: Sostituito il download manuale inline in `build.sh` e nei workflow CI.

### Task 2 — `kikumoe.spec`: onedir su Linux
- **Linux**: Configurato con `EXE(..., exclude_binaries=True, name="KikuMoe", upx=False, strip=False)` e `COLLECT(..., strip=False, upx=False, name="KikuMoe")`. Genera la cartella `dist/KikuMoe/` contenente l'eseguibile e `_internal/`.
- **Windows**: Invariato come eseguibile singolo portatile (`onefile`), con `upx=False, strip=False`.
- **Beneficio**: Elimina l'estrazione a runtime da parte del bootloader PyInstaller verso cartelle temporanee `/tmp/_MEI*` dentro l'AppImage montata.

### Task 3 — `packaging/linux/build-appimage.sh`
- Accetta la directory del bundle (default `dist/KikuMoe`).
- Copia l'intero bundle in `$APPDIR/usr/bin/` con `cp -a`.
- Posiziona `ffmpeg` in `usr/bin/ffmpeg` (già nel PATH esportato da `AppRun`) e symlink a `usr/bin/_internal/ffmpeg` per soddisfare ricerche relative sia a `sys.executable` sia a `sys._MEIPASS`.
- `appimagetool`: Pinned alla versione `1.9.1` con checksum SHA256 (`ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0`).
- Compressione: Chiamata con `--comp zstd --mksquashfs-opt -Xcompression-level --mksquashfs-opt 19`.
- Metainfo: Consolidata singola copia in `usr/share/metainfo/me.chiro.kikumoe.metainfo.xml`.

### Task 4 — Gruppo Poetry `build` e `build.sh`
- Aggiunto in `pyproject.toml` il gruppo dedicato `[tool.poetry.group.build.dependencies]` contenente `pyinstaller` e `pyinstaller-hooks-contrib`.
- Aggiornato `poetry.lock`.
- `build.sh` esegue `cd "$PROJECT_ROOT"` prima di invocare `poetry install --only main,build` (escludendo `pytest`, `mypy`, `ruff` dal setup di build).
- Al termine copia `packaging/linux/ffmpeg` in `dist/KikuMoe/ffmpeg` se presente e notifica il percorso finale.

### Task 5 — Workflow CI Modernizzati (GitHub Actions & Forgejo)
- **Permessi minimi**: `permissions: contents: read` a livello workflow; `contents: write` circoscritto esclusivamente al job `release`.
- **Concorrenza**: `concurrency: group: ${{ github.workflow }}-${{ github.ref }}`, con `cancel-in-progress: ${{ github.event_name == 'pull_request' }}`.
- **Cache**: `setup-python` con `cache: poetry` e Poetry fissato a `2.5.1` via `pipx`.
- **Job Linux**: Rimosso `ffmpeg` da `apt-get install`, utilizzo di `fetch-ffmpeg.sh`, e smoke test automatico:
  `chmod +x dist/*.AppImage && QT_QPA_PLATFORM=offscreen timeout 20 dist/*.AppImage --appimage-extract-and-run --version`
- **Supporto `--version` in KikuMoe.py**: Aggiunto parsing CLI di `--version` e `-v` che stampa nome e versione ritornando codice 0 senza caricare la GUI o i thread audio. Aggiunto test dedicato in `tests/test_cli.py`.
- **Job Windows**: Aggiunta verifica hash SHA256 (`d16ea67bcc46d4ee9170f05b322d7184768f216f458bef089c3397a6beaff83e`) del pacchetto 7z di MPV scaricato da shinchiro.
- **Upload Artifact**: Configurato `if-no-files-found: error` e `retention-days: 7`.
- **Job Release**: Step di validazione che richiede corrispondenza esatta tra tag Git (`GITHUB_REF_NAME`) e `v` + versione in `version.yml`.

### Task 6 — Potatura Qt e Filtro Traduzioni
- **Moduli esclusi**: Esclusi da `Analysis` i moduli non importati dal progetto (`QtPrintSupport`, `QtDesigner`, `QtHelp`, `QtCharts`, `QtOpenGLWidgets` oltre a quelli multimediali/webengine/qml già potati). `QtSvg` e `QtDBus` mantenuti per rendering icone SVG e tray/notifiche desktop.
- **Filtro traduzioni**: Filtrate da `a.datas` tutte le voci `.qm` e percorsi `translations/` di Qt, dato che KikuMoe impiega il proprio modulo `core/i18n.py` (dizionari IT/EN).

---

## Note e Ipotesi Esplicite
1. **Repository FFmpeg LGPL**: Il repository upstream `BtbN/FFmpeg-Builds` è stato impiegato come default poiché il fork `yt-dlp/FFmpeg-Builds` distribuisce solo pacchetti `gpl`. Lo script `fetch-ffmpeg.sh` supporta comunque `FFMPEG_REPO` e `FFMPEG_VARIANT` configurabili con fallback trasparente a `gpl`.
2. **Ricerca runtime FFmpeg**: KikuMoe controlla in ordine: variabile d'ambiente `FFMPEG_PATH`, cartella dell'eseguibile (`exe_dir`), cartella `_MEIPASS`, e infine `PATH` di sistema. Con il layout AppImage onedir + symlink `_internal/ffmpeg`, la compatibilità è garantita in qualsiasi scenario di invocazione.
3. **Argomento `--version`**: Implementato direttamente all'ingresso di `main()` in `KikuMoe.py`, consentendo smoke test istantanei in ambienti headless CI senza dipendere da server display X11/Wayland.
