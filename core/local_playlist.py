"""Local music playlist model and queue manager for KikuMoe.

Handles queue operations, shuffling, repeat modes, track advancement,
and persistence across app sessions.
"""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path
from typing import Sequence

from PyQt6.QtCore import QObject, QSettings, pyqtSignal

from core.constants import (
    APP_SETTINGS,
    KEY_LOCAL_LAST_DIR,
    KEY_LOCAL_REPEAT_MODE,
    KEY_LOCAL_SAVED_TRACKS,
    KEY_LOCAL_SHUFFLE,
    ORG_NAME,
    REPEAT_ALL,
    REPEAT_OFF,
    REPEAT_ONE,
    SUPPORTED_AUDIO_EXTENSIONS,
)
from core.local_metadata import LocalTrackInfo, extract_track_metadata

logger = logging.getLogger("kikumoe.local_playlist")


class LocalPlaylistManager(QObject):
    """Coordinates local audio tracks, playlist navigation, shuffle, and repeat."""

    track_changed = pyqtSignal(object)  # LocalTrackInfo | None
    queue_updated = pyqtSignal()
    playback_ended = pyqtSignal()
    mode_changed = pyqtSignal(bool, int)  # shuffle, repeat_mode

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._tracks: list[LocalTrackInfo] = []
        self._current_index: int = -1
        self._history: list[int] = []
        self._shuffle_order: list[int] = []
        self._shuffle_pos: int = -1

        self._settings = QSettings(ORG_NAME, APP_SETTINGS)
        self._shuffle: bool = self._settings.value(KEY_LOCAL_SHUFFLE, False, type=bool)
        self._repeat_mode: int = int(self._settings.value(KEY_LOCAL_REPEAT_MODE, REPEAT_ALL))

    @property
    def tracks(self) -> list[LocalTrackInfo]:
        return list(self._tracks)

    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def shuffle(self) -> bool:
        return self._shuffle

    @property
    def repeat_mode(self) -> int:
        return self._repeat_mode

    def count(self) -> int:
        return len(self._tracks)

    def is_empty(self) -> bool:
        return len(self._tracks) == 0

    def get_track(self, index: int) -> LocalTrackInfo | None:
        if 0 <= index < len(self._tracks):
            return self._tracks[index]
        return None

    def get_current_track(self) -> LocalTrackInfo | None:
        return self.get_track(self._current_index)

    def total_duration_seconds(self) -> float:
        return sum(t.duration_seconds for t in self._tracks)

    def add_files(self, paths: Sequence[str]) -> int:
        """Extract metadata and append supported audio files to the queue."""
        added = 0
        for p in paths:
            path_obj = Path(p)
            if not path_obj.is_file():
                continue
            if path_obj.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
                continue
            try:
                info = extract_track_metadata(str(path_obj.resolve()))
                self._tracks.append(info)
                added += 1
            except Exception as e:
                logger.warning("Could not extract metadata for '%s': %s", p, e)

        if added > 0:
            self._rebuild_shuffle_order()
            self.save_queue()
            self.queue_updated.emit()
            if self._current_index == -1 and len(self._tracks) > 0:
                self.play_index(0)
        return added

    def add_folder(self, folder_path: str, recursive: bool = True) -> int:
        """Scan a directory for supported audio files and add them."""
        folder = Path(folder_path)
        if not folder.is_dir():
            return 0

        self._settings.setValue(KEY_LOCAL_LAST_DIR, str(folder.resolve()))

        files_to_add: list[str] = []
        iterator = folder.rglob("*") if recursive else folder.glob("*")
        for item in sorted(iterator):
            if item.is_file() and item.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS:
                files_to_add.append(str(item.resolve()))

        return self.add_files(files_to_add)

    def remove_track(self, index: int) -> bool:
        """Remove a track at the given index."""
        if not (0 <= index < len(self._tracks)):
            return False

        is_current = index == self._current_index
        del self._tracks[index]
        self._history = [h for h in self._history if h != index]

        if is_current:
            if len(self._tracks) == 0:
                self._current_index = -1
                self.track_changed.emit(None)
            else:
                new_idx = min(index, len(self._tracks) - 1)
                self._current_index = new_idx
                self.track_changed.emit(self._tracks[new_idx])
        elif self._current_index > index:
            self._current_index -= 1

        self._rebuild_shuffle_order()
        self.save_queue()
        self.queue_updated.emit()
        return True

    def move_track(self, from_idx: int, to_idx: int) -> bool:
        """Reorder tracks in the playlist."""
        if not (0 <= from_idx < len(self._tracks) and 0 <= to_idx < len(self._tracks)):
            return False
        if from_idx == to_idx:
            return True

        track = self._tracks.pop(from_idx)
        self._tracks.insert(to_idx, track)

        if self._current_index == from_idx:
            self._current_index = to_idx
        elif from_idx < self._current_index <= to_idx:
            self._current_index -= 1
        elif to_idx <= self._current_index < from_idx:
            self._current_index += 1

        self._rebuild_shuffle_order()
        self.save_queue()
        self.queue_updated.emit()
        return True

    def clear(self) -> None:
        """Empty the queue entirely."""
        self._tracks.clear()
        self._current_index = -1
        self._history.clear()
        self._shuffle_order.clear()
        self._shuffle_pos = -1
        self.save_queue()
        self.track_changed.emit(None)
        self.queue_updated.emit()

    def play_index(self, index: int) -> LocalTrackInfo | None:
        """Switch to and play the track at the specified index."""
        if not (0 <= index < len(self._tracks)):
            return None

        self._current_index = index
        self._history.append(index)
        if len(self._history) > 100:
            self._history.pop(0)

        track = self._tracks[index]
        self.track_changed.emit(track)
        return track

    def set_current_index(self, index: int) -> bool:
        """Switch to and play track at index. Returns True if index is valid."""
        return self.play_index(index) is not None

    def next_track(self) -> LocalTrackInfo | None:
        """Determine and switch to the next track according to repeat and shuffle modes."""
        if not self._tracks:
            return None

        if self._repeat_mode == REPEAT_ONE and self._current_index != -1:
            # Repeat current song
            track = self._tracks[self._current_index]
            self.track_changed.emit(track)
            return track

        if self._shuffle and len(self._tracks) > 1:
            self._shuffle_pos += 1
            if self._shuffle_pos >= len(self._shuffle_order):
                if self._repeat_mode == REPEAT_OFF:
                    self.playback_ended.emit()
                    return None
                # Reshuffle for next round
                self._rebuild_shuffle_order()
                self._shuffle_pos = 0
            target_idx = self._shuffle_order[self._shuffle_pos]
            return self.play_index(target_idx)

        # Sequential mode
        next_idx = self._current_index + 1
        if next_idx >= len(self._tracks):
            if self._repeat_mode == REPEAT_ALL:
                next_idx = 0
            else:
                self.playback_ended.emit()
                return None

        return self.play_index(next_idx)

    def previous_track(self, current_pos: float = 0.0) -> LocalTrackInfo | None:
        """Skip to previous track, or restart current track if already playing > 3.0s."""
        if not self._tracks:
            return None

        if current_pos > 3.0 and self._current_index != -1:
            # Replay current track from beginning
            track = self._tracks[self._current_index]
            self.track_changed.emit(track)
            return track

        if len(self._history) >= 2:
            self._history.pop()  # remove current
            prev_idx = self._history.pop()
            if 0 <= prev_idx < len(self._tracks):
                return self.play_index(prev_idx)

        # Fallback to index - 1
        prev_idx = self._current_index - 1
        if prev_idx < 0:
            prev_idx = len(self._tracks) - 1 if self._repeat_mode == REPEAT_ALL else 0

        return self.play_index(prev_idx)

    def toggle_shuffle(self) -> bool:
        """Toggle shuffle state on/off."""
        return self.set_shuffle(not self._shuffle)

    def set_shuffle(self, enabled: bool) -> bool:
        """Set shuffle state and recompute order."""
        self._shuffle = bool(enabled)
        self._settings.setValue(KEY_LOCAL_SHUFFLE, self._shuffle)
        self._rebuild_shuffle_order()
        self.mode_changed.emit(self._shuffle, self._repeat_mode)
        return self._shuffle

    def cycle_repeat_mode(self) -> int:
        """Cycle repeat mode: All -> One -> Off -> All."""
        modes = [REPEAT_ALL, REPEAT_ONE, REPEAT_OFF]
        try:
            curr_pos = modes.index(self._repeat_mode)
            new_mode = modes[(curr_pos + 1) % len(modes)]
        except ValueError:
            new_mode = REPEAT_ALL
        return self.set_repeat_mode(new_mode)

    def set_repeat_mode(self, mode: int) -> int:
        """Set explicit repeat mode."""
        self._repeat_mode = mode if mode in (REPEAT_OFF, REPEAT_ALL, REPEAT_ONE) else REPEAT_ALL
        self._settings.setValue(KEY_LOCAL_REPEAT_MODE, self._repeat_mode)
        self.mode_changed.emit(self._shuffle, self._repeat_mode)
        return self._repeat_mode

    def _rebuild_shuffle_order(self) -> None:
        """Rebuild randomized index list."""
        if not self._tracks:
            self._shuffle_order = []
            self._shuffle_pos = -1
            return

        order = list(range(len(self._tracks)))
        # Keep current track first if possible
        if self._current_index in order:
            order.remove(self._current_index)
            random.shuffle(order)
            order.insert(0, self._current_index)
            self._shuffle_pos = 0
        else:
            random.shuffle(order)
            self._shuffle_pos = -1
        self._shuffle_order = order

    def save_queue(self) -> None:
        """Persist track paths to settings so queue restores on restart."""
        try:
            paths = [t.file_path for t in self._tracks]
            self._settings.setValue(KEY_LOCAL_SAVED_TRACKS, json.dumps(paths))
        except Exception:
            pass

    def load_saved_queue(self) -> int:
        """Restore previous session tracks from settings."""
        try:
            saved_raw = self._settings.value(KEY_LOCAL_SAVED_TRACKS, "[]")
            paths = json.loads(str(saved_raw))
            if isinstance(paths, list) and paths:
                return self.add_files(paths)
        except Exception:
            pass
        return 0
