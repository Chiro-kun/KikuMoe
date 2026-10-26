"""Thread-safe session song history tracking for KikuMoe."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime

from PyQt6.QtCore import QObject, pyqtSignal


@dataclass(frozen=True)
class SongHistoryEntry:
    """Represents a single track played during the listening session."""

    title: str
    artist: str
    station_id: str
    station_name: str
    timestamp: float  # epoch seconds
    art_url: str | None = None
    duration: int = 0
    album: str | None = None

    @property
    def formatted_title(self) -> str:
        """Return 'Artist - Title' or simply 'Title' if artist is empty."""
        clean_artist = self.artist.strip()
        clean_title = self.title.strip()
        if clean_artist and clean_title:
            return f"{clean_artist} - {clean_title}"
        return clean_title or clean_artist or "Unknown Track"

    @property
    def display_time(self) -> str:
        """Format timestamp as HH:MM string."""
        try:
            dt = datetime.fromtimestamp(self.timestamp)
            return dt.strftime("%H:%M")
        except Exception:
            return ""


class SongHistoryManager(QObject):
    """Manages the in-memory ring buffer of tracks played in the current session."""

    entry_added = pyqtSignal(object)
    history_cleared = pyqtSignal()

    def __init__(self, max_entries: int = 100, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._max_entries = max(10, max_entries)
        self._entries: list[SongHistoryEntry] = []
        self._lock = threading.Lock()

    @property
    def max_entries(self) -> int:
        return self._max_entries

    def add_entry(
        self,
        title: str,
        artist: str = "",
        station_id: str = "listenmoe",
        station_name: str = "LISTEN.moe",
        art_url: str | None = None,
        duration: int = 0,
        album: str | None = None,
        timestamp: float | None = None,
    ) -> SongHistoryEntry | None:
        """Add a track to history with consecutive duplicate prevention."""
        clean_title = title.strip()
        clean_artist = artist.strip()

        if not clean_title and not clean_artist:
            return None

        now = timestamp if timestamp is not None else time.time()

        with self._lock:
            # Deduplicate consecutive identical tracks
            if self._entries:
                last = self._entries[0]
                if (
                    last.title.strip().lower() == clean_title.lower()
                    and last.artist.strip().lower() == clean_artist.lower()
                    and last.station_id == station_id
                ):
                    return None

            entry = SongHistoryEntry(
                title=clean_title,
                artist=clean_artist,
                station_id=station_id,
                station_name=station_name,
                timestamp=now,
                art_url=art_url,
                duration=duration,
                album=album.strip() if album else None,
            )

            self._entries.insert(0, entry)
            if len(self._entries) > self._max_entries:
                self._entries.pop()

        self.entry_added.emit(entry)
        return entry

    def get_entries(self) -> list[SongHistoryEntry]:
        """Return a copy of the recorded history entries (newest first)."""
        with self._lock:
            return list(self._entries)

    def count(self) -> int:
        """Return number of history entries."""
        with self._lock:
            return len(self._entries)

    def clear(self) -> None:
        """Clear all session history."""
        with self._lock:
            self._entries.clear()
        self.history_cleared.emit()
