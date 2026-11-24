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

## Mappatura dei File nel Bundle (Risultati Misurati in CI - Run 40240250958)

L'analisi dell'impronta (`AppDir Footprint Analysis`) ha rivelato che il bundle decompresso conteneva ~390 MB di file:

1. **FFmpeg Statico LGPL** (140 MB):
   - `/usr/bin/ffmpeg`: 140 MB uncompressed (la voce principale dell'intero pacchetto).
2. **Codec e Librerie Transitive di Sistema** (~159 MB uncompressed):
   - `libicudata.so.70` (29 MB - doppione dell'ICU di sistema)
   - `libflite_cmu_us_*` (16.5 MB - sintesi vocale text-to-speech)
   - `libx265.so.199` (16 MB - encoder video HEVC)
   - `libcodec2.so.1.0` (15 MB - codec vocale radio)
   - `libavcodec.so.58` (15 MB - codec video di Ubuntu)
   - `librsvg-2.so.2` (11 MB - rendering SVG GNOME)
   - `libgtk-3.so.0` (8.2 MB - toolkit grafico GTK3)
   - `libplacebo.so.192` (7.3 MB - shader GPU per MPV)
   - `liblapack.so.3` (7.3 MB - algebra lineare scientifica)
   - `libaom.so.3` (5.2 MB - decoder video AV1)
   - `libQt6Pdf.so.6` (5.2 MB - modulo PDF Qt)
   - `libavfilter.so.7` (4.6 MB - filtri video di sistema)
   - `libvpx.so.7` (3.1 MB - decoder video VP8/VP9)
   - `libgfortran.so.5` (2.9 MB - runtime GNU Fortran)
   - `libavformat.so.58` (2.6 MB - demuxer di sistema)
3. **Runtime Essenziale di KikuMoe & PyQt6** (~75 MB uncompressed):
   - `libicudata.so.73` (31 MB) + `libicui18n.so.73` (4.3 MB) + `libicuuc.so.73` (2.5 MB) di Qt6
   - `libpython3.12.so.1.0` (29 MB)
   - `libQt6Gui.so.6` (10 MB) + `libQt6Widgets.so.6` (7.4 MB) + `libQt6Core.so.6` (6.6 MB)
   - Binding PyQt6 (`QtWidgets`, `QtCore`, `QtGui` = ~16 MB)
   - `libcrypto.so.3` (4.3 MB)

---

## Interventi di Bonifica (Commit `73a21f8`)
- **Rimozione di `libmpv-dev` dal job `build-linux`**: PyInstaller non ha più accesso a `libmpv.so` dell'ambiente CI di compilazione, troncando l'albero di dipendenze di tutte le 15 librerie video parassite.
- **Filtro `_should_exclude_binary` in `kikumoe.spec`**: Esclusione categorica di `libmpv`, `libav*`, `libx26*`, `libcodec2`, `libplacebo`, `libflite*`, `liblapack`, `libgfortran`, `libgtk*`, `librsvg*`, `libQt6Pdf*`, e di `libicu*.so.70` di sistema (preservando l'ICU `.73` di PyQt6).
- **Risultato atteso**: Riduzione di ~160 MB decompressi (~40-50 MB compressi), portando l'AppImage a **~120-130 MB**.

---

## Task 7 (Opzionale) — FFmpeg Minimale solo-audio
- Qualora si desideri ridurre ulteriormente le dimensioni sotto i **~60-70 MB**, la voce #1 rimasta è `usr/bin/ffmpeg` (140 MB).
- Compilando un binario statico dedicato con `--disable-everything` e solo i decoder MP3/Vorbis/Opus e supporto HTTPS (GnuTLS/mbedTLS), la dimensione scenderebbe a soli **~5-8 MB**.
