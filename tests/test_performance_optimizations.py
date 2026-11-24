"""Regression tests for Beta 5 performance & power-saving optimizations."""

from __future__ import annotations

import ast
import math
import struct
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication

from audio.equalizer import BiquadEqualizerProcessor
from audio.player_ffmpeg import PlayerFFmpeg
from core.audio_analyzer import AudioSpectrumAnalyzer
from core.i18n import I18n
from core.local_metadata import (
    clear_cover_bytes_pool,
    extract_track_metadata,
    intern_cover_bytes,
)
from core.song_history import SongHistoryManager
from ui.history_popover import SongHistoryPopover, SongHistoryRowWidget
from ui.main_window import ListenMoePlayer
from ui.widgets.ambient_cover import AmbientCoverCard, LiveEqualizerBadge

_QAPP: QApplication | None = None


def _get_qapp() -> QApplication:
    global _QAPP
    inst = QApplication.instance()
    if isinstance(inst, QApplication):
        _QAPP = inst
        return inst
    _QAPP = QApplication([])
    return _QAPP


def _make_sine_pcm(freq_hz: float, frames: int = 512, sample_rate: int = 48000) -> bytes:
    samples: list[int] = []
    for i in range(frames):
        val = int(16000 * math.sin(2.0 * math.pi * freq_hz * i / sample_rate))
        samples.append(val)
        samples.append(val)
    return struct.pack(f"<{len(samples)}h", *samples)


# ---------------------------------------------------------------------------
# 1. Single-pass EQ + volume scaling
# ---------------------------------------------------------------------------


def test_equalizer_single_pass_with_volume_matches_two_pass():
    pcm = _make_sine_pcm(1000.0, frames=256)
    bands = [4.0, 2.0, 0.0, -3.0, 0.0, 3.5, 0.0, 0.0, -2.0, 1.5]

    proc_ref = BiquadEqualizerProcessor()
    proc_ref.configure(enabled=True, preamp_db=-2.0, bands_db=bands, sample_rate=48000)
    eq_only = proc_ref.process_pcm_s16le(pcm, sample_rate=48000)

    proc_single = BiquadEqualizerProcessor()
    proc_single.configure(enabled=True, preamp_db=-2.0, bands_db=bands, sample_rate=48000)
    vol = 0.45
    scaled, pre_fader = proc_single.process_pcm_s16le_with_volume(
        pcm, sample_rate=48000, volume=vol, need_pre_fader=True
    )

    assert pre_fader == eq_only

    ref_samples = struct.unpack(f"<{len(eq_only) // 2}h", eq_only)
    out_samples = struct.unpack(f"<{len(scaled) // 2}h", scaled)
    for ref_s, out_s in zip(ref_samples, out_samples):
        expected = max(-32768, min(32767, int(ref_s * vol)))
        assert abs(out_s - expected) <= 1


def test_equalizer_single_pass_skips_pre_fader_when_not_needed():
    pcm = _make_sine_pcm(440.0, frames=128)
    proc = BiquadEqualizerProcessor()
    proc.configure(enabled=True, preamp_db=0.0, bands_db=[6.0] + [0.0] * 9, sample_rate=48000)

    out_half, pre_none = proc.process_pcm_s16le_with_volume(
        pcm, sample_rate=48000, volume=0.5, need_pre_fader=False
    )
    assert pre_none is None
    assert len(out_half) == len(pcm)

    out_mute, pre_mute = proc.process_pcm_s16le_with_volume(
        pcm, sample_rate=48000, volume=0.0, need_pre_fader=False
    )
    assert pre_mute is None
    assert out_mute == bytes(len(pcm))


def test_ffmpeg_write_audio_chunk_single_pass_tap_and_volume():
    import logging
    import threading

    written: list[bytes] = []
    tapped: list[bytes] = []

    class _FakeStream:
        def is_active(self) -> bool:
            return True

        def write(self, data: bytes, exception_on_underflow: bool = False) -> None:
            written.append(data)

    player = PlayerFFmpeg.__new__(PlayerFFmpeg)
    player._stream_lock = threading.RLock()
    player._state_lock = threading.RLock()
    player._eq_processor = BiquadEqualizerProcessor()
    player._eq_processor.configure(
        enabled=True, preamp_db=0.0, bands_db=[6.0] + [0.0] * 9, sample_rate=48000
    )
    player._stream_sample_rate = 48000
    player._muted = False
    player._paused = False
    player._seek_pending = False
    player._seek_seq = 0
    player._bytes_streamed = 0
    player._volume = 0.5
    player._audio_tap = tapped.append
    player._audio_stream = _FakeStream()
    player.log = logging.getLogger("test_ffmpeg_single_pass")

    pcm = _make_sine_pcm(60.0, frames=128)
    player._write_audio_chunk(pcm)

    assert len(written) == 1
    assert len(tapped) == 1
    # Tap receives pre-fader (post-EQ) PCM while output stream receives half-volume PCM
    tap_peak = max(abs(s) for s in struct.unpack(f"<{len(tapped[0]) // 2}h", tapped[0]))
    out_peak = max(abs(s) for s in struct.unpack(f"<{len(written[0]) // 2}h", written[0]))
    assert tap_peak > out_peak * 1.7

    # Detaching tap still writes scaled audio cleanly
    written.clear()
    tapped.clear()
    player._audio_tap = None
    player._write_audio_chunk(pcm)
    assert len(written) == 1
    assert len(tapped) == 0


# ---------------------------------------------------------------------------
# 2. AudioSpectrumAnalyzer tail-slicing & cached logarithmic bin map
# ---------------------------------------------------------------------------


def test_audio_analyzer_tail_slicing_matches_last_window():
    # Build an 8192-byte stereo s16le chunk (2048 frames, 8x FFT_SIZE)
    big_chunk = _make_sine_pcm(440.0, frames=2048)
    tail_bytes = AudioSpectrumAnalyzer.FFT_SIZE * 4
    assert len(big_chunk) == tail_bytes * 8

    a_full = AudioSpectrumAnalyzer()
    a_tail = AudioSpectrumAnalyzer()
    a_full.set_playing(True)
    a_tail.set_playing(True)

    a_full.feed_pcm(big_chunk)
    a_tail.feed_pcm(big_chunk[-tail_bytes:])

    assert a_full._buf_idx == a_tail._buf_idx
    assert a_full._buffer == a_tail._buffer

    bars1, bass1 = a_full.get_spectrum(num_bars=32)
    assert (32, 68) in a_full._bar_map_cache
    cached_ref = a_full._bar_map_cache[(32, 68)]
    bars2, bass2 = a_full.get_spectrum(num_bars=32)
    assert a_full._bar_map_cache[(32, 68)] is cached_ref
    assert len(bars1) == 32 and len(bars2) == 32
    assert 0.0 <= bass1 <= 1.0 and 0.0 <= bass2 <= 1.0


# ---------------------------------------------------------------------------
# 3. Local metadata cover-bytes interning
# ---------------------------------------------------------------------------


def test_intern_cover_bytes_deduplicates_identical_payloads():
    clear_cover_bytes_pool()
    payload_a = b"\x89PNG\r\n\x1a\n" + (b"A" * 2048)
    payload_a_copy = bytes(bytearray(payload_a))
    payload_b = b"\x89PNG\r\n\x1a\n" + (b"B" * 2048)
    assert payload_a is not payload_a_copy

    first = intern_cover_bytes(payload_a)
    second = intern_cover_bytes(payload_a_copy)
    other = intern_cover_bytes(payload_b)

    assert first is payload_a
    assert second is first
    assert other is payload_b
    assert intern_cover_bytes(None) is None
    assert intern_cover_bytes(b"") == b""


def _build_minimal_mp3_with_apic(cover_bytes: bytes, title: str) -> bytes:
    # Build ID3v2.3 header with TIT2 and APIC frames
    tit2_payload = b"\x03" + title.encode("utf-8")
    tit2 = b"TIT2" + struct.pack(">I", len(tit2_payload)) + b"\x00\x00" + tit2_payload

    apic_payload = b"\x00image/png\x00\x03\x00" + cover_bytes
    apic = b"APIC" + struct.pack(">I", len(apic_payload)) + b"\x00\x00" + apic_payload

    body = tit2 + apic
    size = len(body)
    syncsafe = bytes(
        [
            (size >> 21) & 0x7F,
            (size >> 14) & 0x7F,
            (size >> 7) & 0x7F,
            size & 0x7F,
        ]
    )
    return b"ID3\x03\x00\x00" + syncsafe + body + (b"\x00" * 64)


def test_extract_track_metadata_shares_identical_cover_bytes(tmp_path: Path):
    clear_cover_bytes_pool()
    fake_png = b"\x89PNG\r\n\x1a\n" + (b"\x42" * 4096)
    f1 = tmp_path / "track1.mp3"
    f2 = tmp_path / "track2.mp3"
    f1.write_bytes(_build_minimal_mp3_with_apic(fake_png, "Track One"))
    f2.write_bytes(_build_minimal_mp3_with_apic(fake_png, "Track Two"))

    info1 = extract_track_metadata(str(f1))
    info2 = extract_track_metadata(str(f2))

    assert info1.cover_bytes == fake_png
    assert info2.cover_bytes == fake_png
    assert info1.cover_bytes is info2.cover_bytes


# ---------------------------------------------------------------------------
# 4. Background / tray timer suspension & idle visualizer auto-stop
# ---------------------------------------------------------------------------


def test_live_equalizer_badge_suspends_and_resumes_timer():
    app = _get_qapp()
    badge = LiveEqualizerBadge()
    try:
        badge.set_playing(True)
        assert badge._timer.isActive()

        badge.set_ui_suspended(True)
        assert not badge._timer.isActive()

        # Calling set_playing(True) while suspended must keep timer stopped
        badge.set_playing(False)
        badge.set_playing(True)
        assert not badge._timer.isActive()

        badge.set_ui_suspended(False)
        assert badge._timer.isActive()
    finally:
        badge.set_playing(False)
        badge.deleteLater()
        app.processEvents()


def test_ambient_cover_suspends_and_stops_visualizer_when_idle():
    app = _get_qapp()
    card = AmbientCoverCard()
    try:
        card.set_visualizer_enabled(True)
        card.set_playing(True)
        assert card._viz_timer.isActive()

        # Suspending UI pauses the 60 FPS timer and drops incoming PCM
        card.set_ui_suspended(True)
        assert not card._viz_timer.isActive()
        prev_pcm_time = card._analyzer._last_pcm_time
        card.feed_pcm(_make_sine_pcm(200.0, frames=256))
        assert card._analyzer._last_pcm_time == prev_pcm_time

        # Resuming while playing restarts the timer
        card.set_ui_suspended(False)
        assert card._viz_timer.isActive()

        # Stopping playback lets bars decay, then auto-stops _viz_timer
        card._spectrum_bars = [0.2] * len(card._spectrum_bars)
        card._bass_energy = 0.2
        card.set_playing(False)
        for _ in range(120):
            if not card._viz_timer.isActive():
                break
            card._tick_visualizer()
        assert not card._viz_timer.isActive()
        assert card._bass_energy == 0.0
        assert all(v == 0.0 for v in card._spectrum_bars)
    finally:
        card.deleteLater()
        app.processEvents()


def test_main_window_visibility_sync_pauses_timers_and_detaches_tap():
    class _FakeTimer:
        def __init__(self, active: bool = True) -> None:
            self._active = active

        def isActive(self) -> bool:
            return self._active

        def start(self) -> None:
            self._active = True

        def stop(self) -> None:
            self._active = False

    taps: list[Any] = []
    ambient_suspended: list[bool] = []
    badge_suspended: list[bool] = []

    def _feed_pcm(data: bytes) -> None:
        return None

    state = {"visible": True, "minimized": False, "viz": True}

    fake: Any = SimpleNamespace(
        isVisible=lambda: state["visible"],
        isMinimized=lambda: state["minimized"],
        _mini_mode=False,
        song_tick_timer=_FakeTimer(True),
        _progress_timer=_FakeTimer(True),
        _mini_timer=_FakeTimer(False),
        ambient_cover=SimpleNamespace(
            is_visualizer_enabled=lambda: state["viz"],
            feed_pcm=_feed_pcm,
            set_ui_suspended=lambda s: ambient_suspended.append(s),
        ),
        live_badge=SimpleNamespace(set_ui_suspended=lambda s: badge_suspended.append(s)),
        player=SimpleNamespace(set_audio_tap=lambda cb: taps.append(cb)),
    )
    fake._is_any_ui_visible = lambda: ListenMoePlayer._is_any_ui_visible(fake)
    fake._is_main_stage_visible = lambda: ListenMoePlayer._is_main_stage_visible(fake)
    fake._sync_audio_tap = lambda player=None: ListenMoePlayer._sync_audio_tap(fake, player)

    # 1. Visible normal stage with visualizer ON -> timers active, tap attached
    ListenMoePlayer._sync_ui_timers_for_visibility(fake)
    assert fake.song_tick_timer.isActive()
    assert fake._progress_timer.isActive()
    assert taps[-1] is _feed_pcm
    assert ambient_suspended[-1] is False
    assert badge_suspended[-1] is False

    # 2. Hidden in tray -> all visual timers stopped, tap detached
    state["visible"] = False
    ListenMoePlayer._sync_ui_timers_for_visibility(fake)
    assert not fake.song_tick_timer.isActive()
    assert not fake._progress_timer.isActive()
    assert not fake._mini_timer.isActive()
    assert taps[-1] is None
    assert ambient_suspended[-1] is True
    assert badge_suspended[-1] is True

    # 3. Restored in Mini-HUD mode -> main stage suspended, mini timer active, tap detached
    state["visible"] = True
    fake._mini_mode = True
    ListenMoePlayer._sync_ui_timers_for_visibility(fake)
    assert not fake.song_tick_timer.isActive()
    assert not fake._progress_timer.isActive()
    assert fake._mini_timer.isActive()
    assert taps[-1] is None
    assert ambient_suspended[-1] is True
    assert badge_suspended[-1] is True

    # 4. Back to normal mode, but visualizer disabled -> timers active, tap remains detached
    fake._mini_mode = False
    state["viz"] = False
    ListenMoePlayer._sync_ui_timers_for_visibility(fake)
    assert fake.song_tick_timer.isActive()
    assert fake._progress_timer.isActive()
    assert taps[-1] is None
    assert ambient_suspended[-1] is False


# ---------------------------------------------------------------------------
# 5. Lazy SongHistoryPopover refresh while hidden
# ---------------------------------------------------------------------------


def test_history_popover_defers_row_rebuild_until_opened():
    app = _get_qapp()
    mgr = SongHistoryManager(max_entries=10)
    i18n = I18n("en")
    pop = SongHistoryPopover(mgr, i18n=i18n)
    try:
        # Initially hidden and dirty; no row widgets built yet
        assert pop._list_dirty is True
        assert pop.list_container.findChildren(SongHistoryRowWidget) == []

        mgr.add_entry(title="Song 1", artist="Artist 1", station_id="listenmoe")
        mgr.add_entry(title="Song 2", artist="Artist 2", station_id="listenmoe")

        # Badge & clear button stay fresh immediately, but row widgets stay deferred
        assert pop.badge_count.text() == "2"
        assert pop.btn_clear.isEnabled()
        assert pop._list_dirty is True
        assert pop.list_container.findChildren(SongHistoryRowWidget) == []

        # Opening the popover materializes the rows once
        pop.open_at(QPoint(50, 50))
        app.processEvents()
        assert pop._list_dirty is False
        assert len(pop.list_container.findChildren(SongHistoryRowWidget)) == 2
    finally:
        if pop._anim_group is not None:
            pop._anim_group.stop()
        pop.hide()
        pop.deleteLater()
        app.processEvents()


# ---------------------------------------------------------------------------
# 6. Startup speed: deferred Qt & lazy audio backend imports
# ---------------------------------------------------------------------------


def test_kikumoe_cli_version_runs_without_eager_qt_imports():
    root = Path(__file__).resolve().parent.parent
    kikumoe_src = (root / "KikuMoe.py").read_text(encoding="utf-8")
    tree = ast.parse(kikumoe_src)

    top_level_imports: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_level_imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level_imports.add(node.module)

    assert not any(m.startswith("PyQt6") for m in top_level_imports)
    assert "ui.main_window" not in top_level_imports

    proc = subprocess.run(
        [sys.executable, str(root / "KikuMoe.py"), "--version"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert proc.returncode == 0
    assert "KikuMoe" in proc.stdout


def test_main_window_does_not_eagerly_import_player_backends():
    root = Path(__file__).resolve().parent.parent
    mw_src = (root / "ui" / "main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(mw_src)

    eager_modules: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                eager_modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            eager_modules.add(node.module)

    assert "audio.player_ffmpeg" not in eager_modules
    assert "audio.player_mpv" not in eager_modules
    assert "audio.player_vlc" not in eager_modules


# ---------------------------------------------------------------------------
# 7. Discord RPC timer idle stop, History thumbnail cache, MarqueeLabel
# ---------------------------------------------------------------------------


def test_discord_settings_stops_timer_when_disabled_and_skips_qsettings_on_tick():
    class _FakeTimer:
        def __init__(self, active: bool = True) -> None:
            self._active = active

        def isActive(self) -> bool:
            return self._active

        def start(self) -> None:
            self._active = True

        def stop(self) -> None:
            self._active = False

    class _FakeRpc:
        def __init__(self) -> None:
            self.enabled = False
            self.client_id = ""
            self.activities: list[Any] = []

        def configure(self, enabled: bool, client_id: str) -> None:
            self.enabled = bool(enabled and client_id)
            self.client_id = client_id

        def set_activity(self, activity: Any) -> None:
            self.activities.append(activity)

    settings_reads = 0
    rpc_enabled = {"val": False}

    def _read_value(key: str, default: Any = "") -> Any:
        nonlocal settings_reads
        settings_reads += 1
        return default

    def _read_bool(key: str, default: bool = False) -> bool:
        nonlocal settings_reads
        settings_reads += 1
        return bool(rpc_enabled["val"])

    fake: Any = SimpleNamespace(
        discord_presence=_FakeRpc(),
        _discord_timer=_FakeTimer(active=True),
        settings=SimpleNamespace(value=_read_value),
        _get_bool=_read_bool,
        player=SimpleNamespace(is_playing=lambda: True, is_paused=lambda: False),
        _ui_paused=False,
        _current_title="Track",
        _current_artist="Artist",
        _current_radio_provider="listenmoe",
        _current_start_epoch=None,
        _current_duration_seconds=None,
        _clock_sync_offset=0.0,
        _current_cover_ref=None,
        _normalize_album_cover_url=lambda ref: None,
        i18n=SimpleNamespace(t=lambda key: key),
    )
    fake._sync_discord_presence = lambda refresh_settings=True: (
        ListenMoePlayer._sync_discord_presence(fake, refresh_settings=refresh_settings)
    )

    # Disabled -> stops 1s timer immediately
    ListenMoePlayer._sync_discord_settings(fake)
    assert not fake._discord_timer.isActive()
    assert not fake.discord_presence.enabled

    # Enabled -> starts 1s timer and reads settings once
    rpc_enabled["val"] = True
    ListenMoePlayer._sync_discord_settings(fake)
    assert fake._discord_timer.isActive()
    assert fake.discord_presence.enabled
    reads_after_enable = settings_reads

    # Periodic timer ticks must NOT re-read QSettings
    ListenMoePlayer._on_discord_timer_tick(fake)
    ListenMoePlayer._on_discord_timer_tick(fake)
    assert settings_reads == reads_after_enable
    assert len(fake.discord_presence.activities) >= 2


def test_history_thumbnail_caches_scaled_pixmap_across_repaints():
    from PyQt6.QtGui import QColor, QPixmap

    from network.image_cache import clear_cached_pixmaps, store_cached_pixmap
    from ui.history_popover import _TrackThumbnail

    app = _get_qapp()
    clear_cached_pixmaps()
    url = "https://cdn.listen.moe/covers/test_cached_thumb.png"
    pm = QPixmap(128, 128)
    pm.fill(QColor("#EC186C"))
    store_cached_pixmap(url, pm)

    thumb = _TrackThumbnail(url)
    try:
        scaled1 = thumb._get_scaled_pixmap()
        scaled2 = thumb._get_scaled_pixmap()
        assert scaled1 is not None
        assert scaled1 is scaled2
        assert scaled1.width() >= 34 and scaled1.height() >= 34
        # Offscreen repaint uses the cached pixmap cleanly
        thumb.grab()
        assert thumb._get_scaled_pixmap() is scaled1
    finally:
        thumb.deleteLater()
        app.processEvents()
        clear_cached_pixmaps()


def test_marquee_label_skips_timer_when_fitting_or_hidden_and_stops_on_hide():
    from ui.widgets.mini_hud import MarqueeLabel

    app = _get_qapp()
    lbl = MarqueeLabel("#ffffff", bold=True)
    lbl.resize(120, 18)
    try:
        # Hidden label must not start 35ms timer even for very long text
        lbl.set_text("A very long anime song title that definitely overflows 120 pixels wide")
        assert lbl._text_width > 120
        assert not lbl._timer.isActive()

        # Showing overflowing label starts timer
        lbl.show()
        app.processEvents()
        assert lbl._timer.isActive()

        # Hiding immediately stops timer and resets scroll offset
        lbl._offset = 15
        lbl.hide()
        app.processEvents()
        assert not lbl._timer.isActive()
        assert lbl._offset == 0

        # Visible short text that fits keeps timer stopped
        lbl.show()
        lbl.set_text("Hi")
        app.processEvents()
        assert not lbl._timer.isActive()
    finally:
        lbl.hide()
        lbl.deleteLater()
        app.processEvents()
