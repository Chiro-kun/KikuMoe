"""KikuMoe Station and Stream Configurations.

Defines stream endpoints, quality formats, and metadata endpoints
for supported web radio stations.
"""

from __future__ import annotations

from typing import Any

# Legacy stream dictionary for LISTEN.moe backward compatibility
STREAMS: dict[str, dict[str, str]] = {
    "J-POP": {
        "Vorbis": "https://listen.moe/stream",
        "Opus": "https://listen.moe/opus",
        "MP3": "https://listen.moe/fallback",
    },
    "K-POP": {
        "Vorbis": "https://listen.moe/kpop/stream",
        "Opus": "https://listen.moe/kpop/opus",
        "MP3": "https://listen.moe/kpop/fallback",
    },
}

# Complete station catalog for multi-station support
STATIONS: dict[str, dict[str, Any]] = {
    "listenmoe": {
        "id": "listenmoe",
        "name": "LISTEN.moe",
        "icon": "listen.png",
        "has_channels": True,
        "channels": ["J-POP", "K-POP"],
        "formats": ["Vorbis", "Opus", "MP3"],
        "default_channel": "J-POP",
        "default_format": "Vorbis",
        "streams": STREAMS,
        "homepage": "https://listen.moe",
    },
    "gensokyo": {
        "id": "gensokyo",
        "name": "Gensokyo Radio",
        "icon": "radio_gensokyo.png",
        "has_channels": False,
        "channels": [],
        "formats": ["MP3 256k", "MP3 128k", "Opus 64k"],
        "default_channel": "",
        "default_format": "MP3 256k",
        "streams": {
            "MP3 256k": "https://stream.gensokyoradio.net/3",
            "MP3 128k": "https://stream.gensokyoradio.net/1",
            "Opus 64k": "https://stream.gensokyoradio.net/2",
        },
        "metadata_url": "https://gensokyoradio.net/api/station/playing/",
        "art_base_url": "https://gensokyoradio.net/images/albums/500/",
        "homepage": "https://gensokyoradio.net/",
    },
    "anison": {
        "id": "anison",
        "name": "ANISON.FM",
        "icon": "radio_anison.png",
        "has_channels": False,
        "channels": [],
        "formats": ["MP3 320k"],
        "default_channel": "",
        "default_format": "MP3 320k",
        "streams": {
            "MP3 320k": "https://pool.anison.fm/AniSonFM(320)",
        },
        "fallback_streams": [
            "http://pool.anison.fm:9000/AniSonFM(320)",
        ],
        "metadata_url": "https://anison.fm/status.php?widget=true&layer=1",
        "homepage": "https://en.anison.fm/",
    },
}


def get_station_config(station_id: str) -> dict[str, Any]:
    """Returns the configuration dict for the given station, defaulting to LISTEN.moe."""
    return STATIONS.get(station_id.lower().strip(), STATIONS["listenmoe"])


def get_station_stream_url(
    station_id: str,
    channel: str | None = None,
    fmt: str | None = None,
) -> str:
    """Resolves the audio stream URL for a station, channel, and audio format.

    Gracefully falls back to station defaults if the requested format or channel
    is missing or invalid.
    """
    station = get_station_config(station_id)
    streams = station.get("streams", {})

    if station.get("has_channels"):
        chan_key = (channel or station.get("default_channel", "J-POP")).strip()
        chan_streams = streams.get(chan_key) or streams.get("J-POP", {})
        fmt_key = (fmt or station.get("default_format", "Vorbis")).strip()
        url = chan_streams.get(fmt_key)
        if url:
            return str(url)
        # Fallback to Vorbis, MP3, or first available
        fallback = (
            chan_streams.get("Vorbis")
            or chan_streams.get("MP3")
            or (next(iter(chan_streams.values()), None) if chan_streams else None)
        )
        if fallback:
            return str(fallback)
        return "https://listen.moe/fallback"

    # Station without sub-channels
    fmt_key = (fmt or station.get("default_format", "")).strip()
    url = streams.get(fmt_key)
    if url:
        return str(url)
    if streams:
        return str(next(iter(streams.values())))

    return "https://listen.moe/fallback"
