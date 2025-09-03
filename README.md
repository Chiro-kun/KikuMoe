# KikuMoe

Un semplice player desktop per LISTEN.moe basato su PyQt5 e VLC (python-vlc). Fornisce riproduzione dei flussi J-POP/K-POP, scorciatoie da tastiera, tray icon, indicatore stato di VLC e dettagli (versione e percorso libVLC), con testi in Italiano e Inglese.

## Requisiti
- Python 3.8+
- VLC Desktop installato (stessa architettura di Python: x64 con x64, x86 con x86),
  oppure percorso di libVLC configurato manualmente dall’app.

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
- Se VLC è correttamente rilevato, vedrai l’indicatore “VLC è presente” in verde.
- Se non viene trovato, premi “Imposta percorso VLC…” e seleziona la cartella di installazione di VLC
  (quella che contiene `libvlc.dll`, ad es. `C:/Program Files/VideoLAN/VLC`).
- Seleziona Canale (J-POP/K-POP) e Formato (Vorbis/MP3), quindi premi Riproduci.
- La Tray Icon (area di notifica) offre un menu rapido con Play/Pausa, Stop, Muto/Unmute e Esci.

### Scorciatoie da tastiera
- Spazio: Avvia se fermo, altrimenti Pausa/Resume
- S: Stop
- M: Muto/Unmute

## Internazionalizzazione (i18n)
L’app supporta Italiano e Inglese. Cambiando lingua, i testi di UI, Tray e indicatori si aggiornano istantaneamente.

## Dettagli VLC
L’interfaccia mostra:
- Versione libVLC (se disponibile)
- Percorso configurato (o “Sistema/PATH” quando usa quello di sistema)

## Risoluzione problemi
- Se compare “VLC non inizializzato” o non parte la riproduzione:
  - Verifica di avere VLC Desktop installato.
  - Assicurati che l’architettura (x64/x86) corrisponda a quella di Python.
  - In alternativa, usa “Imposta percorso VLC…” e scegli la cartella dove risiede `libvlc.dll`.

## Stato attuale
- Implementati: Tray icon con menu, indicatore stato VLC testuale, dettagli VLC, scorciatoie, i18n IT/EN.
- In cantiere: Icone SVG dedicate per tray/stato, pagina Impostazioni per opzioni aggiuntive.