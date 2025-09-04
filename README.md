# KikuMoe

Un semplice player desktop per LISTEN.moe basato su PyQt5 e VLC (python-vlc). Offre riproduzione dei flussi J-POP/K-POP, scorciatoie da tastiera, tray icon, indicatore di stato di VLC e interfaccia bilingue (Italiano/Inglese). Supporta il riavvio automatico dello stream quando cambi canale, formato o percorso di libVLC dalle Impostazioni.

## Requisiti
- Python 3.8+
- VLC Desktop installato (stessa architettura di Python: x64 con x64, x86 con x86),
  oppure percorso di libVLC configurato manualmente dalle Impostazioni dell’app.

## Installazione
1. Clona o scarica il repository.
2. Installa le dipendenze:

```bash
pip install -r requirements.txt
```

## Avvio
Esegui l’applicazione:

```bash
python KikuMoe.py
```

## Uso
- Se libVLC è correttamente rilevato, vedrai l’indicatore in verde ("VLC è presente"). In caso contrario, apri Impostazioni e imposta il percorso libVLC (la cartella che contiene `libvlc.dll`, ad es. `C:/Program Files/VideoLAN/VLC`).
- I valori di Canale (J-POP/K-POP) e Formato (Vorbis/MP3) sono mostrati nella finestra principale come etichette non modificabili: per cambiarli, apri Impostazioni.
- Premi Riproduci per avviare lo stream. Puoi usare Pausa/Riprendi, Stop, il controllo Volume e il pulsante Muto.
- La Tray Icon (area di notifica) offre un menu rapido con Mostra/Nascondi, Play/Pausa, Stop, Muto/Unmute ed Esci.

### Scorciatoie da tastiera
- Spazio: Avvia se fermo, altrimenti Pausa/Riprendi
- S: Stop
- M: Muto/Unmute

## Impostazioni
- Lingua (IT/EN)
- Canale e Formato dello stream
- Percorso libVLC (opzionale, se VLC non è nel PATH)
- Avvio automatico all’apertura (se abilitato)
- Tray Icon abilitata e notifiche tray

Quando chiudi la finestra delle Impostazioni con OK, se lo stream era in riproduzione e hai cambiato Canale, Formato o il percorso di libVLC, l’app mostra "Riavvio dello stream…" e riavvia automaticamente la riproduzione.

## Indicatore stato VLC
L’interfaccia mostra uno stato testuale e un’icona che indicano se libVLC è disponibile. Se non lo è, passa il mouse sull’indicatore per leggere un suggerimento su come configurarlo.

## Risoluzione problemi
- Se compare "VLC non pronto" o la riproduzione non parte:
  - Verifica di avere VLC Desktop installato.
  - Assicurati che l’architettura (x64/x86) corrisponda a quella di Python.
  - In alternativa, imposta il percorso libVLC nelle Impostazioni (cartella contenente `libvlc.dll`).

## Stato attuale
- Implementati: Tray icon con menu, indicatore stato VLC, scorciatoie, i18n IT/EN, percorso libVLC configurabile dalle Impostazioni, riavvio automatico dello stream dopo modifica impostazioni.
- Note: I dettagli avanzati di VLC (versione, percorso) non sono più mostrati nella finestra principale; è presente un indicatore di stato semplice e chiaro.

## Packaging (OneFile, zero-config)

Da ora in poi è supportata e consigliata solo la build "onefile" (singolo .exe), che include automaticamente libVLC e i plugins per un'esperienza zero-config.

Prerequisiti (nell’ambiente in cui hai installato le dipendenze del progetto):
- `pip install --upgrade pyinstaller pyinstaller-hooks-contrib` (lo script di build lo esegue comunque in automatico)

Come creare il pacchetto:
1. Facoltativo: se VLC non è installato nel percorso predefinito `C:\\Program Files\\VideoLAN\\VLC`, imposta la variabile d’ambiente prima del build:
   - PowerShell:
     ```powershell
     $env:VLC_DIR = "C:\\Percorso\\alla\\tua\\installazione\\VLC"
     ```
2. Esegui lo script dalla root del repository:
   ```powershell
   ./build.ps1
   ```

Output:
- L’eseguibile sarà in `dist\KikuMoe-1.5.exe`.

Dettagli tecnici:
- Il file `kikumoe.spec` forza la modalità onefile e include automaticamente:
  - `libvlc.dll` e `libvlccore.dll`
  - l’intera cartella `plugins` di VLC
- Il runtime hook `pyi_rthook_vlc.py` imposta le variabili d’ambiente necessarie (`PATH` e `VLC_PLUGIN_PATH`) durante l’esecuzione del bundle, così non è richiesta alcuna configurazione aggiuntiva lato utente.
- In caso di antivirus troppo aggressivi, l’eseguibile onefile può richiedere un’approvazione/whitelist. Il primo avvio potrebbe essere leggermente più lento perché i contenuti vengono estratti in una cartella temporanea.

Nota: le precedenti istruzioni per build manuali con `pyinstaller ... --onefile/--onedir` e le opzioni dello script (es. `-OneFile`, `-Onedir`, `-BundleVlc`) non sono più necessarie né supportate: usare esclusivamente `./build.ps1`, che esegue `pyinstaller kikumoe.spec`.