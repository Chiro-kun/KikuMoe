from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

I18N: dict[str, dict[str, str]] = {
    "it": {
        "lyrics_button": "Testo",
        "lyrics_loading": "Cerco il testo…",
        "lyrics_missing": "Testo non disponibile per questo brano.",
        "lyrics_error": "Impossibile caricare il testo. Riprova più tardi.",
        "lyrics_instrumental": "Brano strumentale",
        "lyrics_plain": "Testo non sincronizzato",
        "lyrics_no_timing": "Sincronizzazione non disponibile",
        "app_title": "KikuMoe",
        "header": "LISTEN.moe - {channel} - {format}",
        "channel_label": "Canale:",
        "format_label": "Formato:",
        "language_label": "Lingua:",
        "play": "Riproduci",
        "play_active": "In riproduzione!",
        "pause": "Pausa",
        "stop": "Stop",
        "volume": "Volume",
        "mute": "Muto",
        "unmute": "Riattiva audio",
        "now_playing_prefix": "In riproduzione:",
        "status_opening": "Apertura…",
        "status_buffering": "Buffering…",
        "status_buffering_pct": "Buffering… {pct}% ",
        "status_playing": "In riproduzione!",
        "status_paused": "In pausa.",
        "status_stopped": "Fermo.",
        "status_ended": "Stream terminato.",
        "status_error": "Errore di riproduzione.",
        "status_restarting": "Riavvio dello stream…",
        "status_no_backend": "Nessun backend audio disponibile",
        "backend_missing_detail": (
            "Nessun backend audio pronto (MPV, VLC o FFmpeg). "
            "Avvia tramite run.ps1 o verifica le dipendenze."
        ),
        "ws_closed_reconnect": "In riproduzione: WS chiuso, riconnessione...",
        "ws_error_prefix": "In riproduzione: errore WS: ",
        "unknown": "Sconosciuto",
        "live_mode": "LIVE",
        # Timer di sessione
        "session_timer": "Sessione: {time}",
        "settings_session_timer_enable": "Mostra timer di sessione",
        "settings_session_timer_tip": (
            "Mostra il tempo trascorso dall’avvio dell’app (si azzera alla chiusura)."
        ),
        "libvlc_not_ready": (
            "Backend non inizializzato. Installa FFmpeg (consigliato) "
            "o imposta il percorso di libVLC dalle Impostazioni."
        ),
        "libvlc_init_failed": (
            "Impossibile inizializzare il backend. Verifica FFmpeg/libVLC e la "
            "compatibilità (x64/x86)."
        ),
        "libvlc_button": "Imposta percorso VLC…",
        "libvlc_choose_title": "Seleziona cartella VLC",
        "libvlc_saved_ok": "Percorso VLC salvato. Prova a riprodurre lo stream.",
        "libvlc_saved_fail": "Impossibile inizializzare VLC con il percorso selezionato.",
        "libvlc_hint": (
            "Suggerimento: installa FFmpeg e assicurati che sia nel PATH. In alternativa, "
            "scegli la cartella che contiene libvlc.dll (es. C:/Program Files/VideoLAN/VLC) "
            "e verifica che l’architettura corrisponda a Python."
        ),
        # Nuove chiavi per indicatori/Tray/dettagli VLC
        "vlc_present": "Backend disponibile",
        "vlc_not_found": "Backend non disponibile",
        "vlc_version_label": "Versione backend:",
        "vlc_path_label": "Percorso backend:",
        "vlc_path_system": "Sistema/PATH",
        "tray_show": "Mostra finestra",
        "tray_hide": "Nascondi finestra",
        "tray_play_pause": "Play/Pausa",
        "tray_stop": "Stop",
        "tray_mute": "Muto",
        "tray_unmute": "Riattiva audio",
        "tray_station": "Stazione",
        "tray_channel": "Canale",
        "tray_format": "Formato (codec)",
        "tray_quit": "Esci",
        "tray_open_app": "Apri KikuMoe ↗",
        "tray_no_track": "Nessun brano in riproduzione",
        # Intestazioni di sezione per il menu Tray
        "tray_section_playback": "Riproduzione",
        "tray_section_window": "Finestra",
        "tray_section_preferences": "Preferenze",
        # Chiavi per finestra impostazioni
        "settings_button": "Impostazioni",
        "settings_title": "Impostazioni",
        "settings_autoplay": "Avvio automatico playback all’apertura",
        "settings_autoplay_tip": "Avvia automaticamente la musica all’apertura del programma.",
        "settings_discord_rpc": "Abilita Discord Rich Presence",
        "settings_discord_id": "ID applicazione Discord",
        "discord_open_kikumoe": "Apri KikuMoe",
        "settings_language": "Selezione lingua",
        "settings_appearance_section": "ASPETTO & TEMA",
        "settings_theme": "Tema interfaccia",
        "theme_cyber_moe": "Cyber Moe",
        "theme_midnight_amoled": "Midnight AMOLED",
        "theme_sakura_bloom": "Sakura Bloom",
        "theme_neon_matrix": "Neon Matrix",
        "theme_ocean_cyan": "Ocean Cyan",
        "settings_custom_accent_enable": "Colore accento personalizzato",
        "settings_custom_accent_color": "Colore accento",
        "settings_custom_accent_pick": "Scegli…",
        "settings_custom_accent_dialog_title": "Scegli colore accento",
        "settings_custom_accent_reset": "Ripristina",
        "settings_custom_accent_reset_tip": "Ripristina il colore predefinito del tema",
        "color_picker_eyedropper": "Pipetta",
        "color_picker_eyedropper_tip": "Cattura un colore da qualsiasi punto dello schermo",
        "color_picker_copy_tip": "Copia codice HEX",
        "color_picker_restore_initial_tip": "Ripristina colore iniziale ({hex})",
        "color_picker_presets": "PALETTE RAPIDA",
        "color_picker_saved": "COLORI SALVATI",
        "color_picker_save_btn": "+ Salva",
        "color_picker_save_tip": "Salva il colore attuale nei colori personalizzati",
        "color_picker_empty_slot_tip": "Slot vuoto — clicca per salvare il colore attuale",
        "color_picker_saved_slot_tip": "{hex} — clic sinistro per applicare, destro per rimuovere",
        "color_picker_red": "Rosso (0–255)",
        "color_picker_green": "Verde (0–255)",
        "color_picker_blue": "Blu (0–255)",
        "color_picker_hue": "Tonalità (0–359°)",
        "color_picker_sat": "Saturazione (0–100%)",
        "color_picker_val": "Luminosità (0–100%)",
        "settings_station": "Stazione radio",
        "settings_station_tip": "Seleziona la stazione radio da ascoltare",
        "settings_channel": "Canale di default",
        "settings_format": "Formato di default",
        "settings_volume": "Volume di default",
        "settings_mute": "Muto di default",
        "settings_vlc_path": "Percorso VLC",
        "settings_browse": "Sfoglia…",
        "settings_tray_enable": "Abilita tray",
        "settings_tray_notifications": "Notifiche brano in tray",
        "settings_tray_hide_on_minimize": "Nascondi in tray quando minimizzata",
        "settings_network_caching": "Caching di rete (ms)",
        "settings_ok": "OK",
        "settings_cancel": "Annulla",
        "settings_apply": "Applica",
        "settings_saved": "Impostazioni salvate",
        "settings_unchanged": "Nessuna modifica da applicare",
        # Audio backend selection
        "settings_audio_backend": "Backend audio",
        "settings_audio_backend_auto": "Automatico (FFmpeg → MPV → VLC)",
        "settings_audio_backend_ffmpeg": "FFmpeg",
        "settings_audio_backend_mpv": "MPV",
        "settings_audio_backend_vlc": "VLC",
        # Audio device selection
        "settings_audio_output": "Uscita audio",
        "settings_audio_default": "Sistema (predefinito)",
        "settings_audio_refresh": "Aggiorna",
        # Sleep Timer
        "sleep_timer": "Sleeptimer",
        "sleep_minutes": "Minuti:",
        "sleep_start": "Avvia",
        "sleep_cancel": "Annulla",
        "sleep_remaining": "Sleep tra {time}",
        # Opzione: stop allo scadere Sleep Timer
        "settings_sleep_stop_on_end": "Alla scadenza Sleep Timer: ferma riproduzione",
        "settings_show_sleep_timer": "Mostra pannello Sleep Timer",
        "settings_show_sleep_timer_tip": (
            "Mostra o nascondi il riquadro Sleep Timer nella finestra principale"
        ),
        # Dev console
        "settings_dev_console": "Abilita console sviluppatore",
        "settings_dev_console_show_dev": "Mostra messaggi con tag [DEV]",
        "dev_console_button": "Console",
        "dev_console_title": "Console sviluppatore",
        "dev_console_clear": "Pulisci",
        "dev_console_copy": "Copia tutto",
        "dev_console_pause": "Pausa",
        "dev_console_resume": "Riprendi",
        "dev_console_save": "Salva...",
        "dev_console_autoscroll": "Autoscroll",
        "close_dialog_title": "Chiudere l'app?",
        "close_dialog_text": "Vuoi chiudere l’app o ridurla nella tray?",
        "close_option_quit": "Esci dall’app",
        "close_option_tray": "Riduci nella tray",
        "close_remember": "Ricorda scelta",
        # Cronologia brani & Ricerca rapida
        "history_button": "Cronologia brani",
        "history_title": "Cronologia sessione",
        "history_empty": "Nessun brano riprodotto in questa sessione",
        "history_clear": "Svuota",
        "history_count": "{n} brani",
        "search_spotify": "Cerca su Spotify",
        "search_youtube": "Cerca su YouTube",
        "search_apple_music": "Cerca su Apple Music",
        "search_menu_tooltip": "Cerca brano / Azioni...",
        "copy_title": "Copia titolo",
        "copy_artist": "Copia artista",
        "copy_formatted": "Copia 'Artista - Titolo'",
        "copied_feedback": "Copiato negli appunti!",
        "dev_console_wrap": "A capo automatico",
        "dev_console_level": "Filtro livello",
        "dev_console_level_short": "LIVELLO",
        "dev_console_status_live": "LIVE",
        "dev_console_status_paused": "IN PAUSA",
        "dev_console_ready": "Console pronta. I log appariranno qui.",
        "dev_console_placeholder": "I log appariranno qui...",
        "tray_audio_restarted": "Audio riavviato: il timer di sessione continua",
        "tray_persistent_error": "Errore persistente: ricarica interrotta.",
        # Volume zero safeguard
        "volume_zero_title": "Volume a zero",
        "volume_zero_text": "Il volume è impostato a 0. Vuoi ripristinarlo al 60%?",
        "restore": "Ripristina",
        "mini_mode": "Apri Mini player (F9)",
        "mini_restore": "Ripristina finestra (F9)",
        "mini_pin": "Sempre in primo piano",
        "mini_volume": "Volume",
        "tt_play": "Riproduci",
        "tt_pause": "Pausa/Riprendi",
        "tt_stop": "Ferma riproduzione",
        "tt_mute": "Disattiva audio",
        "tt_unmute": "Riattiva audio",
        # Settings Tab Labels
        "settings_tab_general": "Generale",
        "settings_tab_audio": "Audio",
        "settings_tab_advanced": "Avanzate",
        "settings_tab_info": "Info",
        # About & Info
        "about_title": "Informazioni su KikuMoe",
        "about_tagline": "Player desktop moderno per web radio, musica e ascolto locale",
        "about_authors_section": "AUTORI & SVILUPPO",
        "about_authors_names": "Chirokun & alsogamer",
        "about_license": "Licenza MIT",
        "about_links_section": "REPOSITORY & LINK",
        "about_link_forgejo": "Forgejo",
        "about_link_github": "GitHub",
        "about_link_telegram": "Telegram",
        "about_link_telegram_tip": "Canale aggiornamenti su Telegram (t.me/Chiro_kun)",
        "about_powered_by_section": "POWERED BY / RADIO",
        "about_link_listenmoe": "LISTEN.moe",
        "about_link_listenmoe_tip": "LISTEN.moe (listen.moe)",
        "about_link_gensokyo": "Gensokyo",
        "about_link_gensokyo_tip": "Gensokyo Radio (gensokyoradio.net)",
        "about_link_anison": "Anison",
        "about_link_anison_tip": "Anison.FM (en.anison.fm)",
        "about_link_neuro21": "Neuro 21",
        "about_link_neuro21_tip": "Neuro 21 Radio (radio.twinskaraoke.com)",
        "about_link_truckersfm": "TruckersFM",
        "about_link_truckersfm_tip": "TruckersFM (truckers.fm)",
        "about_sys_section": "INFORMAZIONI DI SISTEMA",
        "about_sys_backend": "Motore Audio:",
        "about_sys_python": "Python:",
        "about_sys_pyqt": "PyQt:",
        "about_sys_os": "Sistema Operativo:",
        "about_copy_sys_info": "Copia info di sistema",
        "about_copied": "Copiato negli appunti! ✓",
        "tray_about": "Informazioni su KikuMoe...",
        # Aggiornamenti OTA
        "updates_title": "Aggiornamento disponibile",
        "updates_new_version_available": "Nuova versione disponibile: {version}",
        "updates_current_version": "Versione installata: {version}",
        "updates_check_now": "Verifica aggiornamenti",
        "updates_checking": "Verifica in corso…",
        "updates_up_to_date": "KikuMoe è già aggiornato all'ultima versione!",
        "updates_section": "AGGIORNAMENTI APPLICAZIONE",
        "updates_channel_label": "Canale aggiornamenti:",
        "updates_channel_stable": "Stabile",
        "updates_channel_beta": "Beta / Anteprima",
        "updates_startup_check": "Controlla aggiornamenti all'avvio",
        "updates_startup_check_tip": (
            "Controlla automaticamente nuove versioni su GitHub all'avvio dell'app."
        ),
        "updates_download": "Scarica aggiornamento",
        "updates_downloading": "Download in corso ({pct}%)…",
        "updates_download_complete": "Download completato con successo!",
        "updates_open_folder": "Apri cartella download",
        "updates_view_github": "Note su GitHub",
        "updates_remind_later": "Più tardi",
        "updates_ignore_version": "Non notificarmi più per questa versione",
        "updates_error": "Impossibile verificare gli aggiornamenti: {error}",
        "updates_badge_stable": "STABILE",
        "updates_badge_beta": "BETA",
        # Musica Locale
        "station_local": "Musica Locale",
        "local_prompt_title": "Musica Locale",
        "local_prompt_subtitle": (
            "Nessun brano presente nella coda locale.\n"
            "Seleziona una cartella o dei file per iniziare l'ascolto."
        ),
        "local_select_folder": "Seleziona Cartella…",
        "local_select_files": "Seleziona File…",
        "local_open_queue": "Gestisci Coda",
        "queue_empty_hint": "Coda vuota · Seleziona cartella o trascina file",
        "local_queue_title": "Coda Locale",
        "local_queue_empty": "Trascina file o cartelle audio qui per iniziare l'ascolto",
        "local_add_files": "Aggiungi File…",
        "local_add_folder": "Aggiungi Cartella…",
        "local_clear_queue": "Svuota coda",
        "local_remove_track": "Rimuovi traccia",
        "local_play_now": "Riproduci subito",
        "local_open_directory": "Apri cartella file",
        "local_shuffle": "Casuale",
        "local_repeat_all": "Ripeti: Tutti",
        "local_repeat_one": "Ripeti: Brano",
        "local_repeat_off": "Ripeti: No",
        "local_tracks_summary": "{count} brani · {duration}",
        "local_prev_track": "Brano precedente",
        "local_next_track": "Brano successivo",
        "local_search_placeholder": "Cerca traccia o artista…",
        "local_audio_files_filter": (
            "File audio (*.mp3 *.flac *.ogg *.opus *.m4a *.aac *.wav);;Tutti i file (*.*)"
        ),
        "local_tracks_zero": "0 brani",
        # Controlli finestra & riproduzione
        "window_minimize": "Minimizza",
        "window_maximize": "Ingrandisci",
        "window_restore": "Ripristina",
        "window_close": "Chiudi",
        "tt_force_stop": "Riavvio forzato audio",
        "tt_force_stop_menu": "Ferma / Riavvia audio",
        "tt_stop_shortcut": "Stop (S)",
        "tt_prev_track": "Brano precedente (F5)",
        "tt_play_pause": "Riproduci / Pausa (Spazio)",
        "tt_next_track": "Brano successivo (F6)",
        "tt_queue": "Coda / Playlist (Q)",
        "tt_sleep_timer": "Sleep Timer",
        "tt_sleep_toggle_drawer": "Nascondi Sleep Timer",
        "tt_autoplay": "Autoplay",
        "tt_mute_toggle": "Muto / Riattiva audio (M)",
        "sleep_custom_minutes_tip": "Minuti personalizzati",
        "station_switch_tooltip": "Cambia stazione radio",
        "history_unknown_track": "Brano sconosciuto",
        "about_badge": "INFO & CREDITI",
        "backend_ok": "Backend audio OK",
        "dev_console_log_files_filter": (
            "File di log (*.log);;File di testo (*.txt);;Tutti i file (*)"
        ),
        # Aggiornamenti (dettagli dialog)
        "updates_release_notes": "Note di rilascio:",
        "updates_no_release_notes": "Nessuna nota di rilascio dettagliata disponibile.",
        "updates_package_info": "Pacchetto: {name} ({size_mb} MB)",
        "updates_available_github": "Disponibile su GitHub Releases",
        "updates_launch_installer": "Avvia Installer",
        "updates_download_error": "Errore download: {error}",
        # Impostazioni (sezioni & controlli mancanti)
        "settings_radio_prefs_section": "PREFERENZE RADIO",
        "settings_ambient_mode": "Ambient Mode (sfondo dinamico)",
        "settings_ambient_mode_tip": (
            "Mostra uno sfondo sfocato dinamico ispirato alla copertina dell'album"
        ),
        "settings_visualizer": "Visualizzatore audio radiale",
        "settings_visualizer_tip": (
            "Mostra un alone audio-reattivo attorno alla copertina dell'album"
        ),
        "settings_playback_section": "COMPORTAMENTO RIPRODUZIONE",
        "settings_discord_id_placeholder": "KikuMoe (predefinito)",
        "settings_audio_engine_section": "MOTORE AUDIO & USCITA",
        "settings_force_reset_audio_btn": "Riavvia audio",
        "settings_force_reset_audio_done": "Audio riavviato",
        "settings_force_reset_audio_tip": "Forza l'arresto e la pulizia completa del backend audio",
        "settings_network_libvlc_section": "BUFFER DI RETE & LIBVLC",
        "settings_vlc_path_placeholder": "Auto / PATH di sistema",
        "settings_tray_section": "SYSTEM TRAY",
        "settings_dev_console_section": "CONSOLE SVILUPPATORE",
        "settings_back_to_player": "Player",
        # Volume dinamico (audio ducking)
        "settings_dynamic_volume_section": "VOLUME DINAMICO",
        "settings_dynamic_volume_enable": "Riduci volume con app / giochi",
        "settings_dynamic_volume_tip": (
            "Riduce temporaneamente il volume di KikuMoe quando le app o i giochi "
            "elencati sono aperti o in primo piano"
        ),
        "settings_dynamic_volume_mode": "Quando ridurre",
        "settings_dynamic_volume_mode_any": "App in lista aperta",
        "settings_dynamic_volume_mode_fg": "App in primo piano",
        "settings_dynamic_volume_level": "Volume target",
        "settings_dynamic_volume_level_tip": (
            "Percentuale del volume attuale mantenuta durante la riduzione (es. 25%)"
        ),
        "settings_dynamic_volume_apps": "App / processi",
        "settings_dynamic_volume_apps_placeholder": "es. VALORANT-Win64-Shipping, cs2, discord",
        "settings_dynamic_volume_apps_tip": (
            "Nomi di processi separati da virgola (con o senza .exe; supporta *)"
        ),
        "settings_dynamic_volume_pick_app": "Scegli app aperta…",
        "settings_dynamic_volume_no_apps": "Nessuna app rilevata",
        "dynamic_volume_ducked_tooltip": (
            "Volume ridotto al {effective}% per {app} (volume base: {base}%)"
        ),
    },
    "en": {
        "lyrics_button": "Lyrics",
        "lyrics_loading": "Searching for lyrics…",
        "lyrics_missing": "No lyrics found for this track.",
        "lyrics_error": "Could not load lyrics. Please try again later.",
        "lyrics_instrumental": "Instrumental track",
        "lyrics_plain": "Unsynchronized lyrics",
        "lyrics_no_timing": "Synchronization unavailable",
        "app_title": "KikuMoe",
        "header": "LISTEN.moe - {channel} - {format}",
        "channel_label": "Channel:",
        "format_label": "Format:",
        "language_label": "Language:",
        "play": "Play",
        "play_active": "Playing!",
        "pause": "Pause",
        "stop": "Stop",
        "volume": "Volume",
        "mute": "Mute",
        "unmute": "Unmute",
        "now_playing_prefix": "Now Playing:",
        "status_opening": "Opening…",
        "status_buffering": "Buffering…",
        "status_buffering_pct": "Buffering… {pct}% ",
        "status_playing": "Playing!",
        "status_paused": "Paused.",
        "status_stopped": "Stopped.",
        "status_ended": "Stream ended.",
        "status_error": "Playback error.",
        "status_restarting": "Restarting stream…",
        "status_no_backend": "No audio backend available",
        "backend_missing_detail": (
            "No audio backend ready (MPV, VLC, or FFmpeg). "
            "Launch via run.ps1 or check dependencies."
        ),
        "ws_closed_reconnect": "Now Playing: WS closed, reconnecting...",
        "ws_error_prefix": "Now Playing: WS error: ",
        "unknown": "Unknown",
        "live_mode": "LIVE",
        # Session timer
        "session_timer": "Session: {time}",
        "settings_session_timer_enable": "Show session timer",
        "settings_session_timer_tip": "Display elapsed time since app start (resets on close).",
        "libvlc_not_ready": (
            "Backend not initialized. Install FFmpeg (recommended) or set libVLC path in Settings."
        ),
        "libvlc_init_failed": (
            "Failed to initialize backend. Check FFmpeg/libVLC and architecture (x64/x86)."
        ),
        "libvlc_button": "Set VLC Path…",
        "libvlc_choose_title": "Select VLC folder",
        "libvlc_saved_ok": "VLC path saved. Try playing the stream.",
        "libvlc_saved_fail": "Failed to initialize VLC with the selected path.",
        "libvlc_hint": (
            "Hint: install FFmpeg and ensure it is in PATH. Alternatively, choose the folder "
            "containing libvlc.dll (e.g., C:/Program Files/VideoLAN/VLC) and ensure "
            "architecture matches Python."
        ),
        # New keys for indicators/Tray/VLC details
        "vlc_present": "Backend available",
        "vlc_not_found": "Backend not available",
        "vlc_version_label": "Backend Version:",
        "vlc_path_label": "Backend Path:",
        "vlc_path_system": "System/PATH",
        "tray_show": "Show window",
        "tray_hide": "Hide window",
        "tray_play_pause": "Play/Pause",
        "tray_stop": "Stop",
        "tray_mute": "Mute",
        "tray_unmute": "Unmute",
        "tray_station": "Station",
        "tray_channel": "Channel",
        "tray_format": "Format/Codec",
        "tray_quit": "Quit",
        "tray_open_app": "Open KikuMoe ↗",
        "tray_no_track": "No track playing",
        # Section headers for Tray menu
        "tray_section_playback": "Playback",
        "tray_section_window": "Window",
        "tray_section_preferences": "Preferences",
        # Keys for settings window
        "settings_button": "Settings",
        "settings_title": "Settings",
        "settings_autoplay": "Autoplay on startup",
        "settings_autoplay_tip": "Automatically start playback when the app opens.",
        "settings_discord_rpc": "Enable Discord Rich Presence",
        "settings_discord_id": "Discord Application ID",
        "discord_open_kikumoe": "Open KikuMoe",
        "settings_language": "Language",
        "settings_appearance_section": "APPEARANCE & THEME",
        "settings_theme": "Interface theme",
        "theme_cyber_moe": "Cyber Moe",
        "theme_midnight_amoled": "Midnight AMOLED",
        "theme_sakura_bloom": "Sakura Bloom",
        "theme_neon_matrix": "Neon Matrix",
        "theme_ocean_cyan": "Ocean Cyan",
        "settings_custom_accent_enable": "Custom accent color",
        "settings_custom_accent_color": "Accent color",
        "settings_custom_accent_pick": "Pick…",
        "settings_custom_accent_dialog_title": "Choose accent color",
        "settings_custom_accent_reset": "Reset",
        "settings_custom_accent_reset_tip": "Reset to preset's default accent",
        "color_picker_eyedropper": "Pick Screen",
        "color_picker_eyedropper_tip": "Pick a color from anywhere on your screen",
        "color_picker_copy_tip": "Copy HEX code",
        "color_picker_restore_initial_tip": "Restore initial color ({hex})",
        "color_picker_presets": "QUICK PALETTE",
        "color_picker_saved": "SAVED COLORS",
        "color_picker_save_btn": "+ Save",
        "color_picker_save_tip": "Save current color to custom swatches",
        "color_picker_empty_slot_tip": "Empty slot — click to save current color",
        "color_picker_saved_slot_tip": "{hex} — left-click to apply, right-click to remove",
        "color_picker_red": "Red (0–255)",
        "color_picker_green": "Green (0–255)",
        "color_picker_blue": "Blue (0–255)",
        "color_picker_hue": "Hue (0–359°)",
        "color_picker_sat": "Saturation (0–100%)",
        "color_picker_val": "Brightness (0–100%)",
        "settings_station": "Radio station",
        "settings_station_tip": "Select the radio station to stream",
        "settings_channel": "Default channel",
        "settings_format": "Default format",
        "settings_volume": "Default volume",
        "settings_mute": "Default mute",
        "settings_vlc_path": "VLC path",
        "settings_browse": "Browse…",
        "settings_tray_enable": "Enable tray icon",
        "settings_tray_notifications": "Song notifications in tray",
        "settings_tray_hide_on_minimize": "Hide to tray when minimized",
        "settings_network_caching": "Network caching (ms)",
        "settings_ok": "OK",
        "settings_cancel": "Cancel",
        "settings_apply": "Apply",
        "settings_saved": "Settings saved",
        "settings_unchanged": "No changes to apply",
        # Audio backend selection
        "settings_audio_backend": "Audio backend",
        "settings_audio_backend_auto": "Auto (FFmpeg → MPV → VLC)",
        "settings_audio_backend_ffmpeg": "FFmpeg",
        "settings_audio_backend_mpv": "MPV",
        "settings_audio_backend_vlc": "VLC",
        # Audio device selection
        "settings_audio_output": "Audio output",
        "settings_audio_default": "System (default device)",
        "settings_audio_refresh": "Refresh",
        # Sleep Timer
        "sleep_timer": "Sleep timer",
        "sleep_minutes": "Minutes:",
        "sleep_start": "Start",
        "sleep_cancel": "Cancel",
        "sleep_remaining": "Sleep in {time}",
        # Option: stop when Sleep Timer elapses
        "settings_sleep_stop_on_end": "When Sleep Timer elapses: stop playback",
        "settings_show_sleep_timer": "Show Sleep Timer panel",
        "settings_show_sleep_timer_tip": "Show or hide the Sleep Timer card on the main window",
        # Dev console
        "settings_dev_console": "Enable developer console",
        "settings_dev_console_show_dev": "Show messages tagged [DEV]",
        "dev_console_button": "Console",
        "dev_console_title": "Developer Console",
        "dev_console_clear": "Clear",
        "dev_console_copy": "Copy all",
        "dev_console_pause": "Pause",
        "dev_console_resume": "Resume",
        "dev_console_save": "Save...",
        "dev_console_autoscroll": "Autoscroll",
        "dev_console_wrap": "Wrap",
        "dev_console_level": "Level filter",
        "dev_console_level_short": "LEVEL",
        "dev_console_status_live": "LIVE",
        "dev_console_status_paused": "PAUSED",
        "dev_console_ready": "Console ready. Logs will appear here.",
        "dev_console_placeholder": "Logs will appear here...",
        "tray_audio_restarted": "Audio restarted: session timer continues",
        "tray_persistent_error": "Persistent error: retry aborted.",
        # Volume zero safeguard
        "volume_zero_title": "Volume is zero",
        "volume_zero_text": "Volume is set to 0. Do you want to restore it to 60%?",
        "restore": "Restore",
        "mini_mode": "Open mini player (F9)",
        "mini_restore": "Restore window (F9)",
        "mini_pin": "Always on top",
        "mini_volume": "Volume",
        "tt_play": "Play",
        "tt_pause": "Pause/Resume",
        "tt_stop": "Stop playback",
        "tt_mute": "Mute",
        "tt_unmute": "Unmute",
        "close_dialog_title": "Close the app?",
        "close_dialog_text": "Do you want to close the app or minimize it to the tray?",
        "close_remember": "Remember choice",
        # Song History & Quick Search
        "history_button": "Song History",
        "history_title": "Session History",
        "history_empty": "No songs played in this session yet",
        "history_clear": "Clear",
        "history_count": "{n} songs",
        "search_spotify": "Search on Spotify",
        "search_youtube": "Search on YouTube",
        "search_apple_music": "Search on Apple Music",
        "search_menu_tooltip": "Search track / Actions...",
        "copy_title": "Copy song title",
        "copy_artist": "Copy artist",
        "copy_formatted": "Copy 'Artist - Title'",
        "copied_feedback": "Copied to clipboard!",
        "close_option_quit": "Quit App",
        "close_option_tray": "Minimize to Tray",
        # Settings Tab Labels
        "settings_tab_general": "General",
        "settings_tab_audio": "Audio",
        "settings_tab_advanced": "Advanced",
        "settings_tab_info": "About",
        # About & Info
        "about_title": "About KikuMoe",
        "about_tagline": "Modern desktop player for web radio, music & local playback",
        "about_authors_section": "AUTHORS & DEVELOPMENT",
        "about_authors_names": "Chirokun & alsogamer",
        "about_license": "MIT License",
        "about_links_section": "REPOSITORIES & LINKS",
        "about_link_forgejo": "Forgejo",
        "about_link_github": "GitHub",
        "about_link_telegram": "Telegram",
        "about_link_telegram_tip": "Updates channel on Telegram (t.me/Chiro_kun)",
        "about_powered_by_section": "POWERED BY / RADIO",
        "about_link_listenmoe": "LISTEN.moe",
        "about_link_listenmoe_tip": "LISTEN.moe (listen.moe)",
        "about_link_gensokyo": "Gensokyo",
        "about_link_gensokyo_tip": "Gensokyo Radio (gensokyoradio.net)",
        "about_link_anison": "Anison",
        "about_link_anison_tip": "Anison.FM (en.anison.fm)",
        "about_link_neuro21": "Neuro 21",
        "about_link_neuro21_tip": "Neuro 21 Radio (radio.twinskaraoke.com)",
        "about_link_truckersfm": "TruckersFM",
        "about_link_truckersfm_tip": "TruckersFM (truckers.fm)",
        "about_sys_section": "SYSTEM DIAGNOSTICS",
        "about_sys_backend": "Audio Engine:",
        "about_sys_python": "Python:",
        "about_sys_pyqt": "PyQt:",
        "about_sys_os": "Operating System:",
        "about_copy_sys_info": "Copy System Info",
        "about_copied": "Copied to clipboard! ✓",
        "tray_about": "About KikuMoe...",
        # OTA Updates
        "updates_title": "Update Available",
        "updates_new_version_available": "New version available: {version}",
        "updates_current_version": "Installed version: {version}",
        "updates_check_now": "Check for updates",
        "updates_checking": "Checking for updates…",
        "updates_up_to_date": "KikuMoe is up to date!",
        "updates_section": "APPLICATION UPDATES",
        "updates_channel_label": "Update channel:",
        "updates_channel_stable": "Stable",
        "updates_channel_beta": "Beta / Preview",
        "updates_startup_check": "Check for updates on startup",
        "updates_startup_check_tip": (
            "Automatically check for new versions on GitHub when starting the app."
        ),
        "updates_download": "Download update",
        "updates_downloading": "Downloading ({pct}%)…",
        "updates_download_complete": "Download completed successfully!",
        "updates_open_folder": "Open download folder",
        "updates_view_github": "View on GitHub",
        "updates_remind_later": "Remind me later",
        "updates_ignore_version": "Don't notify me again for this version",
        "updates_error": "Failed to check for updates: {error}",
        "updates_badge_stable": "STABLE",
        "updates_badge_beta": "BETA",
        # Local Music
        "station_local": "Local Music",
        "local_prompt_title": "Local Music",
        "local_prompt_subtitle": (
            "Your local queue is empty.\nSelect a folder or audio files to start listening."
        ),
        "local_select_folder": "Select Folder…",
        "local_select_files": "Select Files…",
        "local_open_queue": "Open Queue Manager",
        "queue_empty_hint": "Queue empty · Select folder or drop files",
        "local_queue_title": "Local Queue",
        "local_queue_empty": "Drag audio files or folders here to start listening",
        "local_add_files": "Add Files…",
        "local_add_folder": "Add Folder…",
        "local_clear_queue": "Clear queue",
        "local_remove_track": "Remove track",
        "local_play_now": "Play now",
        "local_open_directory": "Open file folder",
        "local_shuffle": "Shuffle",
        "local_repeat_all": "Repeat: All",
        "local_repeat_one": "Repeat: One",
        "local_repeat_off": "Repeat: Off",
        "local_tracks_summary": "{count} tracks · {duration}",
        "local_prev_track": "Previous track",
        "local_next_track": "Next track",
        "local_search_placeholder": "Search track or artist…",
        "local_audio_files_filter": (
            "Audio Files (*.mp3 *.flac *.ogg *.opus *.m4a *.aac *.wav);;All Files (*.*)"
        ),
        "local_tracks_zero": "0 tracks",
        # Window & playback controls
        "window_minimize": "Minimize",
        "window_maximize": "Maximize",
        "window_restore": "Restore",
        "window_close": "Close",
        "tt_force_stop": "Force Reset Audio",
        "tt_force_stop_menu": "Force Stop / Reset Audio",
        "tt_stop_shortcut": "Stop (S)",
        "tt_prev_track": "Previous Track (F5)",
        "tt_play_pause": "Play / Pause (Space)",
        "tt_next_track": "Next Track (F6)",
        "tt_queue": "Queue / Playlist (Q)",
        "tt_sleep_timer": "Sleep Timer",
        "tt_sleep_toggle_drawer": "Hide Sleep Timer",
        "tt_autoplay": "Autoplay",
        "tt_mute_toggle": "Mute / Unmute (M)",
        "sleep_custom_minutes_tip": "Custom minutes",
        "station_switch_tooltip": "Switch radio station",
        "history_unknown_track": "Unknown Track",
        "about_badge": "INFO & CREDITS",
        "backend_ok": "Audio backend OK",
        "dev_console_log_files_filter": ("Log Files (*.log);;Text Files (*.txt);;All Files (*)"),
        # Updates (dialog details)
        "updates_release_notes": "Release notes:",
        "updates_no_release_notes": "No detailed release notes available.",
        "updates_package_info": "Package: {name} ({size_mb} MB)",
        "updates_available_github": "Available on GitHub Releases",
        "updates_launch_installer": "Launch Installer",
        "updates_download_error": "Download error: {error}",
        # Settings (sections & remaining controls)
        "settings_radio_prefs_section": "RADIO PREFERENCES",
        "settings_ambient_mode": "Ambient Mode (dynamic backdrop)",
        "settings_ambient_mode_tip": (
            "Show a dynamic blurred background tinted by the album cover art"
        ),
        "settings_visualizer": "Radial audio visualizer",
        "settings_visualizer_tip": "Show an audio-reactive halo around the album cover art",
        "settings_playback_section": "PLAYBACK BEHAVIOR",
        "settings_discord_id_placeholder": "KikuMoe (default)",
        "settings_audio_engine_section": "AUDIO ENGINE & OUTPUT",
        "settings_force_reset_audio_btn": "Reset audio",
        "settings_force_reset_audio_done": "Audio reset",
        "settings_force_reset_audio_tip": "Force stop and clean up the active audio backend",
        "settings_network_libvlc_section": "NETWORK BUFFER & LIBVLC",
        "settings_vlc_path_placeholder": "Auto / System PATH",
        "settings_tray_section": "SYSTEM TRAY",
        "settings_dev_console_section": "DEVELOPER CONSOLE",
        "settings_back_to_player": "Player",
        # Dynamic volume (audio ducking)
        "settings_dynamic_volume_section": "DYNAMIC VOLUME",
        "settings_dynamic_volume_enable": "Duck volume for specific apps",
        "settings_dynamic_volume_tip": (
            "Temporarily ducks KikuMoe's playback volume while listed games or apps "
            "are running or focused"
        ),
        "settings_dynamic_volume_mode": "When to duck",
        "settings_dynamic_volume_mode_any": "Listed app running",
        "settings_dynamic_volume_mode_fg": "Listed app focused",
        "settings_dynamic_volume_level": "Ducked level",
        "settings_dynamic_volume_level_tip": (
            "Percentage of your current volume kept while ducking is active (e.g. 25%)"
        ),
        "settings_dynamic_volume_apps": "Apps / processes",
        "settings_dynamic_volume_apps_placeholder": "e.g. VALORANT-Win64-Shipping, cs2, discord",
        "settings_dynamic_volume_apps_tip": (
            "Comma-separated process names (with or without .exe; supports *)"
        ),
        "settings_dynamic_volume_pick_app": "Pick running app…",
        "settings_dynamic_volume_no_apps": "No apps detected",
        "dynamic_volume_ducked_tooltip": (
            "Volume ducked to {effective}% for {app} (base volume: {base}%)"
        ),
    },
}


class I18n:
    def __init__(self, lang: str) -> None:
        self.lang = "it" if lang not in ("it", "en") else lang

    def set_lang(self, lang: str) -> None:
        self.lang = "it" if lang not in ("it", "en") else lang

    def t(self, key: str, **kwargs) -> str:
        try:
            txt = I18N[self.lang][key]
            return txt.format(**kwargs) if kwargs else txt
        except Exception:
            return I18N["it"].get(key, key)


def resolve_i18n(i18n: I18n | None = None, parent: Any = None) -> I18n:
    """Resolve an I18n instance from explicit argument, parent widget, or settings/default."""
    if i18n is not None:
        return i18n
    if parent is not None:
        parent_i18n = getattr(parent, "i18n", None) or getattr(parent, "_i18n", None)
        if isinstance(parent_i18n, I18n):
            return parent_i18n
    return I18n("it")


_active_qt_translator: Any = None


def _candidate_qt_translation_dirs() -> list[str]:
    dirs: list[str] = []
    try:
        from PyQt6.QtCore import QLibraryInfo

        qt_dir = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        if qt_dir:
            dirs.append(qt_dir)
    except Exception:
        pass
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        base = Path(str(meipass))
        for rel in (Path("PyQt6") / "Qt6" / "translations", Path("translations")):
            p = str(base / rel)
            if p not in dirs:
                dirs.append(p)
    return [d for d in dirs if d and os.path.isdir(d)]


def install_qt_translator(app: Any, lang: str) -> bool:
    """Load and install Qt's built-in qtbase_<lang>.qm translator on ``app``."""
    global _active_qt_translator
    if app is None:
        return False
    try:
        from PyQt6.QtCore import QTranslator
    except Exception:
        return False

    if _active_qt_translator is not None:
        try:
            app.removeTranslator(_active_qt_translator)
        except Exception:
            pass
        _active_qt_translator = None

    target_lang = "it" if lang not in ("it", "en") else lang
    translator = QTranslator(app)
    for tdir in _candidate_qt_translation_dirs():
        if translator.load(f"qtbase_{target_lang}", tdir):
            if app.installTranslator(translator):
                _active_qt_translator = translator
                return True
    return False
