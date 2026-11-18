"""Cross-backend audio equalizer tests (FFmpeg, MPV, VLC) — CI/headless safe."""

from __future__ import annotations

import logging
import math
import struct
import threading
from types import SimpleNamespace

import audio.player_vlc as vlc_mod
from audio.equalizer import EQ_PRESETS, BiquadEqualizerProcessor, build_mpv_af_string
from audio.player_ffmpeg import PlayerFFmpeg
from audio.player_mpv import PlayerMPV


def _make_sine_chunk(freq_hz: float = 1000.0, amp: float = 5000.0, frames: int = 1024) -> bytes:
    samples: list[int] = []
    w = 2.0 * math.pi * freq_hz / 48000.0
    for n in range(frames):
        v = int(round(amp * math.sin(w * n)))
        samples.append(v)
        samples.append(v)
    return struct.pack(f"<{len(samples)}h", *samples)


def _rms(data: bytes) -> float:
    n = len(data) // 2
    vals = struct.unpack(f"<{n}h", data)
    return math.sqrt(sum(s * s for s in vals) / max(1, len(vals)))


class _FakeAudioStream:
    def __init__(self) -> None:
        self.written: list[bytes] = []

    def is_active(self) -> bool:
        return True

    def write(self, data: bytes, exception_on_underflow: bool = False) -> None:
        self.written.append(data)


def test_ffmpeg_write_chunk_applies_eq_before_tap_and_volume() -> None:
    """PlayerFFmpeg runs EQ post-decode, feeding EQ'd PCM to visualizer tap and volume scaling."""
    player = PlayerFFmpeg.__new__(PlayerFFmpeg)
    player._stream_lock = threading.RLock()
    player._state_lock = threading.RLock()
    player._audio_stream = _FakeAudioStream()
    player._paused = False
    player._muted = False
    player._seek_pending = False
    player._seek_seq = 0
    player._bytes_streamed = 0
    player._stream_sample_rate = 48000
    player._volume = 0.5  # 50% gain after EQ
    player._eq_processor = BiquadEqualizerProcessor()
    player.log = logging.getLogger("test_ffmpeg_eq")

    tapped: list[bytes] = []
    player._audio_tap = tapped.append

    raw_pcm = _make_sine_chunk(1000.0, amp=5000.0, frames=1024)

    # 1. EQ disabled -> tap receives unmodified raw_pcm, stream receives volume-scaled PCM
    player.set_equalizer(False, 6.0, [0.0] * 10)
    player._write_audio_chunk(raw_pcm)
    assert tapped[-1] == raw_pcm
    assert 0.45 < (_rms(player._audio_stream.written[-1]) / _rms(raw_pcm)) < 0.55

    # 2. EQ enabled with +6 dB preamp -> tap sees ~2x boosted signal, stream sees ~1x (2x * 0.5)
    player.set_equalizer(True, 6.0, [0.0] * 10)
    player._write_audio_chunk(raw_pcm)
    assert 1.85 < (_rms(tapped[-1]) / _rms(raw_pcm)) < 2.15
    assert 0.90 < (_rms(player._audio_stream.written[-1]) / _rms(raw_pcm)) < 1.10


def test_ffmpeg_seek_resets_eq_delay_state() -> None:
    """Seeking a local file resets the biquad delay lines cleanly."""
    player = PlayerFFmpeg.__new__(PlayerFFmpeg)
    player._state_lock = threading.RLock()
    player._ready = True
    player._is_local_file = True
    player._current_stream = "dummy.flac"
    player._playing = True
    player._stop_event = threading.Event()
    player._current_seek_offset = 0.0
    player._bytes_streamed = 100
    player._seek_seq = 0
    player._seek_pending = False
    player._ffmpeg_process = None
    player._eq_processor = BiquadEqualizerProcessor()

    player._eq_processor.configure(True, 0.0, list(EQ_PRESETS["rock"][1]), sample_rate=48000)
    _ = player._eq_processor.process_pcm_s16le(_make_sine_chunk(), sample_rate=48000)
    assert any(any(abs(v) > 1e-6 for v in st) for st in player._eq_processor._band_states.values())

    assert player.seek(12.5) is True
    assert player._eq_processor._band_states == {}


def test_mpv_af_string_builder_edge_cases() -> None:
    assert build_mpv_af_string(False, 4.0, [6.0] * 10) == ""
    assert build_mpv_af_string(True, 0.0, [0.0] * 10) == ""
    assert build_mpv_af_string(True, 0.02, [0.01] * 10) == ""
    assert build_mpv_af_string(True, -3.5, [0.0] * 10) == "lavfi=[volume=-3.5dB]"
    assert (
        build_mpv_af_string(True, 0.0, [0.0, 0.0, 0.0, 0.0, 0.0, 4.5, 0.0, 0.0, 0.0, -2.0])
        == "lavfi=[equalizer=f=1000:t=o:w=1.0:g=4.5,equalizer=f=16000:t=o:w=1.0:g=-2.0]"
    )
    # Clamps out-of-range values
    assert (
        build_mpv_af_string(True, 99.0, [-99.0] + [0.0] * 9)
        == "lavfi=[volume=12.0dB,equalizer=f=31:t=o:w=1.0:g=-12.0]"
    )


def test_mpv_set_equalizer_live_and_unready() -> None:
    mpv_inst = PlayerMPV.__new__(PlayerMPV)
    mpv_inst._lock = threading.RLock()
    mpv_inst._ready = False
    mpv_inst._player = None
    mpv_inst.log = logging.getLogger("test_mpv_eq")
    mpv_inst._eq_enabled = False
    mpv_inst._eq_preamp = 0.0
    mpv_inst._eq_bands = [0.0] * 10

    # Calling set_equalizer while unready stores state safely without crashing
    mpv_inst.set_equalizer(True, -2.0, [5.0] + [0.0] * 9)
    assert mpv_inst._eq_enabled is True
    assert mpv_inst._eq_preamp == -2.0

    # Becoming ready and calling _apply_equalizer_to_mpv pushes stored state
    mpv_inst._ready = True
    mpv_inst._player = SimpleNamespace(af="")
    mpv_inst._apply_equalizer_to_mpv()
    assert mpv_inst._player.af == "lavfi=[volume=-2.0dB,equalizer=f=31:t=o:w=1.0:g=5.0]"

    # Disabling clears af live
    mpv_inst.set_equalizer(False, -2.0, [5.0] + [0.0] * 9)
    assert mpv_inst._player.af == ""


def test_vlc_set_equalizer_and_missing_libvlc(monkeypatch) -> None:
    class _FakeAudioEq:
        def __init__(self) -> None:
            self.preamp = 0.0
            self.amps: dict[int, float] = {}

        def set_preamp(self, val: float) -> None:
            self.preamp = val

        def set_amp_at_index(self, amp: float, idx: int) -> None:
            self.amps[idx] = amp

    applied: list[object] = []

    class _FakeVlcPlayer:
        def set_equalizer(self, eq: object) -> None:
            applied.append(eq)

    monkeypatch.setattr(vlc_mod, "vlc", SimpleNamespace(AudioEqualizer=_FakeAudioEq))

    vlc_inst = vlc_mod.PlayerVLC.__new__(vlc_mod.PlayerVLC)
    vlc_inst._lock = threading.RLock()
    vlc_inst._ready = True
    vlc_inst.player = _FakeVlcPlayer()
    vlc_inst.instance = object()
    vlc_inst.log = logging.getLogger("test_vlc_eq")
    vlc_inst._eq_enabled = False
    vlc_inst._eq_preamp = 0.0
    vlc_inst._eq_bands = [0.0] * 10

    rock_pre, rock_bands = EQ_PRESETS["rock"]
    vlc_inst.set_equalizer(True, rock_pre, list(rock_bands))
    assert isinstance(applied[-1], _FakeAudioEq)
    assert applied[-1].preamp == rock_pre
    for idx, expected in enumerate(rock_bands):
        assert applied[-1].amps[idx] == expected

    vlc_inst.set_equalizer(False, rock_pre, list(rock_bands))
    assert applied[-1] is None

    # Missing vlc module (headless CI without libvlc installed) does not raise
    monkeypatch.setattr(vlc_mod, "vlc", None)
    vlc_inst.set_equalizer(True, 1.0, [1.0] * 10)
