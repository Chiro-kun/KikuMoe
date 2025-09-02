from typing import Dict

I18N: Dict[str, Dict[str, str]] = {
    'it': {
        'app_title': 'LISTEN.moe Player (VLC)',
        'header': 'LISTEN.moe - {channel} - {format} (VLC)',
        'channel_label': 'Canale:',
        'format_label': 'Formato:',
        'language_label': 'Lingua:',
        'play': 'Riproduci',
        'pause': 'Pausa',
        'stop': 'Stop',
        'volume': 'Volume',
        'mute': 'Muto',
        'unmute': 'Riattiva audio',
        'now_playing_prefix': 'In riproduzione:',
        'status_opening': 'Apertura…',
        'status_buffering': 'Buffering…',
        'status_buffering_pct': 'Buffering… {pct}%',
        'status_playing': 'In riproduzione!',
        'status_paused': 'In pausa.',
        'status_stopped': 'Fermo.',
        'status_ended': 'Stream terminato.',
        'status_error': 'Errore di riproduzione.',
        'ws_closed_reconnect': 'In riproduzione: WS chiuso, riconnessione...',
        'ws_error_prefix': 'In riproduzione: errore WS: ',
        'unknown': 'Sconosciuto',
    },
    'en': {
        'app_title': 'LISTEN.moe Player (VLC)',
        'header': 'LISTEN.moe - {channel} - {format} (VLC)',
        'channel_label': 'Channel:',
        'format_label': 'Format:',
        'language_label': 'Language:',
        'play': 'Play',
        'pause': 'Pause',
        'stop': 'Stop',
        'volume': 'Volume',
        'mute': 'Mute',
        'unmute': 'Unmute',
        'now_playing_prefix': 'Now Playing:',
        'status_opening': 'Opening…',
        'status_buffering': 'Buffering…',
        'status_buffering_pct': 'Buffering… {pct}%',
        'status_playing': 'Playing!',
        'status_paused': 'Paused.',
        'status_stopped': 'Stopped.',
        'status_ended': 'Stream ended.',
        'status_error': 'Playback error.',
        'ws_closed_reconnect': 'Now Playing: WS closed, reconnecting...',
        'ws_error_prefix': 'Now Playing: WS error: ',
        'unknown': 'Unknown',
    },
}

class I18n:
    def __init__(self, default_lang: str = 'it') -> None:
        self.lang = default_lang if default_lang in I18N else 'it'

    def set_lang(self, lang: str) -> None:
        self.lang = lang if lang in I18N else 'it'

    def t(self, key: str, **kwargs) -> str:
        try:
            s = I18N[self.lang][key]
            return s.format(**kwargs) if kwargs else s
        except Exception:
            return key