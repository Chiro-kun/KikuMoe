"""Platform-neutral snapshot for system media controls."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MediaState:
    status: str = "Stopped"
    title: str = ""
    artist: str = ""
    station: str = ""
    cover_url: str = ""
    track_id: str = "/org/mpris/MediaPlayer2/TrackList/NoTrack"
    duration_us: int = 0
    position_us: int = 0
    volume: float = 1.0
