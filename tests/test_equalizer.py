"""Unit tests for the 10-band ISO Equalizer DSP engine, presets, and serialization."""

from __future__ import annotations

import math
import struct
import threading

import pytest

from audio.equalizer import (
    EQ_BAND_LABELS,
    EQ_FREQUENCIES,
    EQ_MAX_DB,
    EQ_MIN_DB,
    EQ_NUM_BANDS,
    EQ_PRESET_CUSTOM,
    EQ_PRESET_ORDER,
    EQ_PRESETS,
    BiquadEqualizerProcessor,
    clamp_eq_db,
    compute_peaking_biquad,
    normalize_eq_bands,
    parse_eq_bands,
    serialize_eq_bands,
)


def _make_stereo_sine_pcm(
    freq_hz: float,
    amp_left: float = 8000.0,
    amp_right: float | None = None,
    frames: int = 4096,
    sr: int = 48000,
) -> bytes:
    amp_r = amp_left if amp_right is None else amp_right
    samples: list[int] = []
    two_pi_f = 2.0 * math.pi * freq_hz / sr
    for n in range(frames):
        s = math.sin(two_pi_f * n)
        vl = max(-32768, min(32767, int(round(amp_left * s))))
        vr = max(-32768, min(32767, int(round(amp_r * s))))
        samples.append(vl)
        samples.append(vr)
    return struct.pack(f"<{len(samples)}h", *samples)


def _rms_channel_pcm(data: bytes, channel: int = 0, skip_frames: int = 512) -> float:
    n_samples = len(data) // 2
    samples = struct.unpack(f"<{n_samples}h", data)
    ch_samples = samples[channel::2][skip_frames:]
    if not ch_samples:
        return 0.0
    return math.sqrt(sum(s * s for s in ch_samples) / len(ch_samples))


def test_presets_metadata_and_bounds() -> None:
    assert len(EQ_FREQUENCIES) == EQ_NUM_BANDS == 10
    assert len(EQ_BAND_LABELS) == EQ_NUM_BANDS == 10
    assert EQ_PRESET_CUSTOM in EQ_PRESET_ORDER
    assert "flat" in EQ_PRESETS
    assert EQ_PRESETS["flat"] == (0.0, (0.0,) * 10)

    for pid, (preamp, bands) in EQ_PRESETS.items():
        assert pid in EQ_PRESET_ORDER
        assert EQ_MIN_DB <= preamp <= EQ_MAX_DB
        assert len(bands) == EQ_NUM_BANDS
        for gain in bands:
            assert EQ_MIN_DB <= gain <= EQ_MAX_DB


def test_clamping_and_serialization_edge_cases() -> None:
    assert clamp_eq_db(25.0) == EQ_MAX_DB
    assert clamp_eq_db(-99.0) == EQ_MIN_DB
    assert clamp_eq_db(float("nan")) == 0.0
    assert clamp_eq_db(float("inf")) == 0.0
    assert clamp_eq_db(float("-inf")) == 0.0
    assert clamp_eq_db("not-a-number") == 0.0  # type: ignore[arg-type]

    raw = serialize_eq_bands([15.0, -20.0, 3.46, 0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    assert parse_eq_bands(raw) == [12.0, -12.0, 3.5, 0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0]

    # CSV fallback, truncated lists, malformed strings, None
    assert parse_eq_bands("1, 2, -3.5") == [1.0, 2.0, -3.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    assert parse_eq_bands("[invalid json") == [0.0] * 10
    assert parse_eq_bands("") == [0.0] * 10
    assert parse_eq_bands(None) == [0.0] * 10
    assert normalize_eq_bands([1.0, 2.0]) == [1.0, 2.0] + [0.0] * 8
    assert normalize_eq_bands([1.0] * 20) == [1.0] * 10


def test_biquad_identity_bypass_and_preamp() -> None:
    proc = BiquadEqualizerProcessor()
    pcm = _make_stereo_sine_pcm(1000.0, amp_left=6000.0, frames=2048)

    # Disabled -> exact identity object returned (zero-copy bypass)
    assert not proc.is_active()
    assert proc.process_pcm_s16le(pcm) is pcm

    # Enabled with flat gains -> exact identity bypass
    proc.configure(True, 0.0, [0.0] * 10, sample_rate=48000)
    assert not proc.is_active()
    assert proc.process_pcm_s16le(pcm) is pcm

    # Preamp +6 dB (~2x amplitude)
    proc.configure(True, 6.0, [0.0] * 10, sample_rate=48000)
    assert proc.is_active()
    boosted = proc.process_pcm_s16le(pcm, sample_rate=48000)
    ratio_up = _rms_channel_pcm(boosted) / _rms_channel_pcm(pcm)
    assert 1.9 < ratio_up < 2.1

    # Preamp -6 dB (~0.5x amplitude)
    proc.configure(True, -6.0, [0.0] * 10, sample_rate=48000)
    attenuated = proc.process_pcm_s16le(pcm, sample_rate=48000)
    ratio_down = _rms_channel_pcm(attenuated) / _rms_channel_pcm(pcm)
    assert 0.48 < ratio_down < 0.53


@pytest.mark.parametrize(
    ("band_idx", "target_hz", "untouched_hz"),
    [
        (1, 62.0, 4000.0),
        (5, 1000.0, 62.0),
        (8, 8000.0, 250.0),
    ],
)
def test_biquad_frequency_selective_boost_and_cut(
    band_idx: int, target_hz: float, untouched_hz: float
) -> None:
    proc = BiquadEqualizerProcessor()
    sine_target = _make_stereo_sine_pcm(target_hz, amp_left=6000.0, frames=6144)
    sine_other = _make_stereo_sine_pcm(untouched_hz, amp_left=6000.0, frames=6144)

    # +6 dB on target band
    bands = [0.0] * 10
    bands[band_idx] = 6.0
    proc.configure(True, 0.0, bands, sample_rate=48000)
    out_target = proc.process_pcm_s16le(sine_target, sample_rate=48000)
    ratio_boost = _rms_channel_pcm(out_target, skip_frames=1024) / _rms_channel_pcm(
        sine_target, skip_frames=1024
    )
    assert 1.80 < ratio_boost < 2.20

    proc.reset_state()
    out_other = proc.process_pcm_s16le(sine_other, sample_rate=48000)
    ratio_other = _rms_channel_pcm(out_other, skip_frames=1024) / _rms_channel_pcm(
        sine_other, skip_frames=1024
    )
    assert 0.90 < ratio_other < 1.10

    # -6 dB cut on target band
    bands[band_idx] = -6.0
    proc.configure(True, 0.0, bands, sample_rate=48000)
    proc.reset_state()
    out_cut = proc.process_pcm_s16le(sine_target, sample_rate=48000)
    ratio_cut = _rms_channel_pcm(out_cut, skip_frames=1024) / _rms_channel_pcm(
        sine_target, skip_frames=1024
    )
    assert 0.44 < ratio_cut < 0.58


def test_biquad_stereo_channel_isolation() -> None:
    """Processing signal on Left channel must never bleed into silent Right channel."""
    proc = BiquadEqualizerProcessor()
    pcm = _make_stereo_sine_pcm(1000.0, amp_left=10000.0, amp_right=0.0, frames=2048)
    proc.configure(True, -1.0, list(EQ_PRESETS["rock"][1]), sample_rate=48000)
    out = proc.process_pcm_s16le(pcm, sample_rate=48000)
    assert _rms_channel_pcm(out, channel=0) > 1000.0
    assert _rms_channel_pcm(out, channel=1) == 0.0


def test_biquad_chunk_boundary_continuity() -> None:
    """Splitting audio into smaller chunks must match single-pass processing."""
    pcm = _make_stereo_sine_pcm(500.0, amp_left=7000.0, frames=2048)
    bands = list(EQ_PRESETS["anime_jpop"][1])

    p_whole = BiquadEqualizerProcessor()
    p_whole.configure(True, -2.0, bands, sample_rate=48000)
    whole_out = p_whole.process_pcm_s16le(pcm, sample_rate=48000)

    p_chunked = BiquadEqualizerProcessor()
    p_chunked.configure(True, -2.0, bands, sample_rate=48000)
    chunk_bytes = 512  # 128 stereo frames per chunk
    pieces = [
        p_chunked.process_pcm_s16le(pcm[i : i + chunk_bytes], sample_rate=48000)
        for i in range(0, len(pcm), chunk_bytes)
    ]
    assert b"".join(pieces) == whole_out


def test_biquad_nyquist_safety_and_short_buffers() -> None:
    """High-frequency bands remain stable even at low sample rates (e.g. 22050 Hz)."""
    for sr in (22050, 44100, 48000, 96000):
        coeffs = compute_peaking_biquad(16000.0, sr, 9.0)
        assert all(math.isfinite(c) for c in coeffs)

    proc = BiquadEqualizerProcessor()
    proc.configure(True, 12.0, [12.0] * 10, sample_rate=22050)
    assert proc.process_pcm_s16le(b"", sample_rate=22050) == b""
    assert proc.process_pcm_s16le(b"\x01\x02", sample_rate=22050) == b"\x01\x02"

    loud = _make_stereo_sine_pcm(1000.0, amp_left=30000.0, frames=1024, sr=22050)
    out = proc.process_pcm_s16le(loud, sample_rate=22050)
    samples = struct.unpack(f"<{len(out) // 2}h", out)
    assert max(samples) <= 32767
    assert min(samples) >= -32768


def test_biquad_thread_safety_under_live_updates() -> None:
    """Concurrent configure() and process_pcm_s16le() calls never raise or corrupt length."""
    proc = BiquadEqualizerProcessor()
    pcm = _make_stereo_sine_pcm(1000.0, amp_left=6000.0, frames=512)
    errors: list[BaseException] = []

    def _writer() -> None:
        try:
            for i in range(60):
                pid = ("flat", "rock", "bass_boost", "vocal")[i % 4]
                pre, bands = EQ_PRESETS[pid]
                proc.configure(i % 5 != 0, pre, bands, sample_rate=48000)
        except BaseException as exc:
            errors.append(exc)

    def _processor() -> None:
        try:
            for _ in range(60):
                out = proc.process_pcm_s16le(pcm, sample_rate=48000)
                assert len(out) == len(pcm)
        except BaseException as exc:
            errors.append(exc)

    t1 = threading.Thread(target=_writer)
    t2 = threading.Thread(target=_processor)
    t1.start()
    t2.start()
    t1.join(timeout=5.0)
    t2.join(timeout=5.0)
    assert not errors


def test_all_presets_have_non_clipping_peak_headroom() -> None:
    """Every built-in preset must keep summed Q=1.414 response <= 0.1 dB across 20Hz-20kHz."""
    import cmath

    sr = 48000
    freqs = [20.0 * (1000.0 ** (i / 300.0)) for i in range(301)]
    for pid, (preamp, bands) in EQ_PRESETS.items():
        stages = [
            compute_peaking_biquad(freq, sr, gain)
            for freq, gain in zip(EQ_FREQUENCIES, bands)
            if abs(gain) >= 0.05
        ]
        peak_db = max(
            preamp
            + sum(
                20.0
                * math.log10(
                    max(
                        1e-12,
                        abs(
                            (
                                b0
                                + b1 * cmath.exp(-1j * 2.0 * math.pi * f / sr)
                                + b2 * cmath.exp(-2j * 2.0 * math.pi * f / sr)
                            )
                            / (
                                1.0
                                + a1 * cmath.exp(-1j * 2.0 * math.pi * f / sr)
                                + a2 * cmath.exp(-2j * 2.0 * math.pi * f / sr)
                            )
                        ),
                    )
                )
                for b0, b1, b2, a1, a2 in stages
            )
            for f in freqs
        )
        assert peak_db <= 0.1, f"Preset {pid!r} exceeds 0 dBFS headroom: {peak_db:+.2f} dB"


def test_headphones_preset_and_soft_limiter_prevent_hard_clipping() -> None:
    """Headphones preset avoids clipping on hot signals; extreme boosts soft-limit smoothly."""
    proc = BiquadEqualizerProcessor()
    pre, bands = EQ_PRESETS["headphones"]
    proc.configure(True, pre, bands, sample_rate=48000)

    for freq_hz in (62.0, 8000.0, 12000.0):
        hot = _make_stereo_sine_pcm(freq_hz, amp_left=30000.0, frames=2048, sr=48000)
        out = proc.process_pcm_s16le(hot, sample_rate=48000)
        samples = struct.unpack(f"<{len(out) // 2}h", out)
        # Skip initial filter transient; steady-state output must never hard-clip at ±32767
        steady = samples[256:]
        assert all(abs(s) < 32767 for s in steady)

    # Extreme custom boost (+12 dB preamp) soft-limits smoothly without hitting ±32767
    proc.configure(True, 12.0, [0.0] * 10, sample_rate=48000)
    loud = _make_stereo_sine_pcm(1000.0, amp_left=28000.0, frames=512, sr=48000)
    limited = proc.process_pcm_s16le(loud, sample_rate=48000)
    lim_samples = struct.unpack(f"<{len(limited) // 2}h", limited)
    assert all(abs(s) < 32767 for s in lim_samples)
    assert max(lim_samples) > 31500
