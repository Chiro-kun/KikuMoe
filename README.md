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

## Build/Packaging (PyInstaller)

Vuoi creare un eseguibile Windows (.exe) senza dipendenze esterne di Python? Ecco come fare con PyInstaller.

- Requisiti (da eseguire nell'ambiente dove hai installato le dipendenze del progetto):
  - pip install --upgrade pyinstaller pyinstaller-hooks-contrib
- Nota: l'app carica automaticamente le icone dal bundle grazie al fallback su sys._MEIPASS, quindi funziona sia in onefile che onedir.

Build "onefile" (singolo .exe):

- pyinstaller --noconfirm --clean --windowed --onefile --name "KikuMoe" --add-data "KikuMoe\icons;icons" KikuMoe\KikuMoe.py

Build "onedir" (cartella con eseguibile e risorse a fianco):

- pyinstaller --noconfirm --clean --windowed --onedir --name "KikuMoe" --add-data "KikuMoe\icons;icons" KikuMoe\KikuMoe.py

Dove trovare l'eseguibile:

- Al termine, l'eseguibile sarà in dist\KikuMoe\KikuMoe.exe (onedir) oppure dist\KikuMoe.exe (onefile).

Suggerimenti e note:

- Se all'avvio non parte l'audio, apri Impostazioni e imposta correttamente il percorso di libVLC (es: C:\\Program Files\\VideoLAN\\VLC). L'app mostrerà lo stato nella barra (VLC presente / non trovato).
- Per includere anche il runtime VLC direttamente nel pacchetto (opzionale e avanzato), puoi aggiungere:
  - --add-binary "C:\\Program Files\\VideoLAN\\VLC\\libvlc.dll;."
  - --add-binary "C:\\Program Files\\VideoLAN\\VLC\\plugins;plugins"
  In questo caso, ti conviene mantenere impostato in Impostazioni un percorso libVLC lasciato vuoto (userà quello bundled) o configurarlo verso la cartella estratta. In alcune configurazioni potrebbe essere necessario impostare la variabile d'ambiente VLC_PLUGIN_PATH al percorso dei plugins all'avvio tramite uno script o un runtime hook.
- Le icone dell'app sono SVG. Se vuoi assegnare un'icona al file .exe, fornisci un .ico a PyInstaller con --icon "path\\to\\icon.ico" (opzionale).

### Build con file .spec e script PowerShell

Sono stati aggiunti un file .spec e uno script di build per semplificare il packaging:

- kikumoe.spec: definisce gli asset da includere (icone) e un runtime hook per VLC.
- build.ps1: esegue PyInstaller in modalità onefile e/o onedir, con opzione per includere libVLC e plugins.

Esempi d’uso:

- Esegui entrambe le build:
  ./build.ps1
- Solo onefile:
  ./build.ps1 -OneFile
- Solo onedir:
  ./build.ps1 -Onedir
- Includi VLC dal percorso predefinito (o da $env:VLC_DIR):
  ./build.ps1 -BundleVlc
- Includi VLC da un percorso specifico:
  ./build.ps1 -BundleVlc -VlcDir "C:\\Program Files\\VideoLAN\\VLC"

Nota: lo script usa il runtime hook pyi_rthook_vlc.py per impostare PATH e VLC_PLUGIN_PATH quando si esegue dal bundle, così libVLC e i plugins vengono risolti correttamente se sono stati inclusi.