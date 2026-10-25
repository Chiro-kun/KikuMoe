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
   - Inserire un file `onefile` autolimitato all'interno di una AppImage forza una doppia compressione inutile e raddoppia i tempi di avvio e lo spazio su disco temporaneo (`/tmp`).
3. **Moduli PyQt6 Inutilizzati**:
   - Bundling predefinito di moduli Qt non impiegati dal player: `QtQml`, `QtQuick`, `QtQuickWidgets`, `QtPdf`, `QtPdfWidgets`, `QtSql`, `QtXml`, `QtWebEngine*`, `QtBluetooth`, `QtSensors`, `QtPositioning`, ecc.
   - Traduzioni Qt incorporate in blocco in `PyQt6/Qt6/translations`.
4. **Build FFmpeg `gpl` Non Ottimizzata**:
   - Download da branch instabile `latest` di una build `gpl` contenente codec video/encoder non utilizzati da KikuMoe (player solo audio).
   - Assenza di stripping dei simboli (`strip --strip-unneeded`).
5. **Algoritmo di Compressione Squashfs**:
   - `appimagetool` con compressione gzip predefinita a livello standard invece di `zstd` con livello massimo (19).

---

## Piano di Riduzione Obiettivo

| Componente | Configurazione Baseline | Nuova Configurazione | Risparmio Previsto |
|---|---|---|---|
| **Modalità PyInstaller** | `onefile` (273 MB) | `onedir` (`dist/KikuMoe/`) | Elimina duplicazione / estrazione `/tmp` |
| **FFmpeg Backend** | `gpl` latest unstripped (~92 MB) | `linux64-lgpl` pinned + stripped (~35-42 MB) | ~50 MB risparmiati |
| **Compressione AppImage** | gzip standard | `zstd -Xcompression-level 19` | Compressione superiore + decompress. ultra-veloce |
| **Moduli Qt & Traduzioni** | Tutti i moduli PyQt6 inclusi | Exclude mirati + potatura translations in `a.datas` | ~30-45 MB risparmiati |
| **Dimensione AppImage Stimata** | ~200-210 MB | **~75-95 MB** | **Riduzione >50%** |

---

## Log delle Verifiche per Task
- **Task 0**: Documentazione baseline e metriche di partenza.
- **Task 1**: Script `packaging/linux/fetch-ffmpeg.sh` con verifica sha256 e stripping.
- **Task 2**: Passaggio a PyInstaller `onedir` su Linux in `kikumoe.spec`.
- **Task 3**: Riorganizzazione di `packaging/linux/build-appimage.sh` con zstd-19 e appimagetool fissato.
- **Task 4**: Creazione gruppo Poetry `build` isolato e pulizia `build.sh`.
- **Task 5**: Modernizzazione workflow CI GitHub e Forgejo con smoke test `--version` e concurrency.
- **Task 6**: Potatura selettiva traduzioni e moduli Qt.
