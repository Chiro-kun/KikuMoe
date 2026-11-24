"""10-band ISO Audio Equalizer (EQ) DSP engine, standard presets, and backend helpers."""

from __future__ import annotations

import json
import math
import struct
import threading
from collections.abc import Sequence

# 10-band ISO standard center frequencies (Hz)
EQ_FREQUENCIES: tuple[int, ...] = (
    31,
    62,
    125,
    250,
    500,
    1000,
    2000,
    4000,
    8000,
    16000,
)

EQ_BAND_LABELS: tuple[str, ...] = (
    "31",
    "62",
    "125",
    "250",
    "500",
    "1k",
    "2k",
    "4k",
    "8k",
    "16k",
)

EQ_NUM_BANDS = 10
EQ_MIN_DB = -12.0
EQ_MAX_DB = 12.0
EQ_PRESET_CUSTOM = "custom"

# Standard ISO 10-band reference curves (Winamp / libVLC / Rockbox inspired curves
# balanced around 0 dB with true anti-clipping preamp headroom accounting for
# adjacent Q=1.414 octave-band overlap so summed peak gain stays <= 0.0 dB):
# Format: preset_id -> (preamp_db, (31, 62, 125, 250, 500, 1k, 2k, 4k, 8k, 16k))
EQ_PRESETS: dict[str, tuple[float, tuple[float, ...]]] = {
    "flat": (0.0, (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)),
    "recommended": (-4.5, (4.0, 2.0, 1.0, 0.0, -1.0, -2.0, 0.0, 2.0, 3.0, 3.0)),
    "bass_boost": (-6.5, (5.5, 4.5, 3.5, 1.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)),
    "treble_boost": (-6.0, (0.0, 0.0, 0.0, 0.0, 0.0, 0.5, 2.0, 3.5, 5.0, 5.5)),
    "pop": (-5.5, (-1.5, 2.0, 3.5, 4.0, 2.5, 0.0, -1.5, -1.5, 1.0, 1.5)),
    "anime_jpop": (-7.0, (3.0, 2.0, -0.5, -4.5, -3.5, 0.5, 3.5, 5.0, 5.5, 5.5)),
    "rock": (-7.0, (3.5, 2.0, -3.5, -5.0, -2.5, 1.5, 4.0, 5.0, 5.0, 5.0)),
    "electronic": (-6.0, (4.0, 2.5, -0.5, -3.5, -3.0, 0.0, 3.5, 4.5, 4.5, 4.0)),
    "vocal": (-5.5, (-2.5, -3.0, -1.5, 1.0, 3.5, 4.0, 3.0, 1.0, 0.0, -1.5)),
    "headphones": (-5.5, (1.5, 4.5, 1.5, -2.5, -2.0, -0.5, 1.5, 3.5, 4.5, 5.0)),
    "classical": (0.0, (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -4.5, -4.5, -4.5, -6.0)),
    "night_soft": (-6.5, (2.0, 0.5, 0.0, -1.5, 0.0, 1.5, 3.5, 4.5, 5.0, 5.0)),
}

# Soft-clipping safety limiter constants for s16le output:
# 100% bit-exact linear below ±29491 (~90% full scale, -0.92 dBFS), then C1-smooth
# asymptotic saturation approaching ±32767 to prevent harsh digital crackling even
# under extreme custom EQ boosts.
_SOFT_CLIP_KNEE = 29491.0
_SOFT_CLIP_HEAD = 3276.0


def _soft_clip_s16(val: float) -> int:
    """Linear below ±0.9 FS; smooth C1 soft-limiter knee approaching ±32767."""
    if val > _SOFT_CLIP_KNEE:
        d = val - _SOFT_CLIP_KNEE
        return int(_SOFT_CLIP_KNEE + _SOFT_CLIP_HEAD * d / (_SOFT_CLIP_HEAD + d))
    if val < -_SOFT_CLIP_KNEE:
        d = -_SOFT_CLIP_KNEE - val
        return int(-_SOFT_CLIP_KNEE - _SOFT_CLIP_HEAD * d / (_SOFT_CLIP_HEAD + d))
    return int(val)


EQ_PRESET_ORDER: tuple[str, ...] = (
    "flat",
    "recommended",
    "bass_boost",
    "treble_boost",
    "pop",
    "anime_jpop",
    "rock",
    "electronic",
    "vocal",
    "headphones",
    "classical",
    "night_soft",
    EQ_PRESET_CUSTOM,
)


def clamp_eq_db(value: float) -> float:
    """Clamp a gain value in dB to [EQ_MIN_DB, EQ_MAX_DB] rounded to 0.1 dB."""
    try:
        v = float(value)
        if not math.isfinite(v):
            return 0.0
    except (TypeError, ValueError):
        return 0.0
    return round(max(EQ_MIN_DB, min(EQ_MAX_DB, v)), 1)


def normalize_eq_bands(bands: Sequence[float] | None) -> list[float]:
    """Return a clean 10-element list of clamped dB floats."""
    if not bands:
        return [0.0] * EQ_NUM_BANDS
    result: list[float] = []
    for i in range(EQ_NUM_BANDS):
        if i < len(bands):
            result.append(clamp_eq_db(bands[i]))
        else:
            result.append(0.0)
    return result


def parse_eq_bands(raw: object) -> list[float]:
    """Parse stored QSettings EQ band gains from JSON string, CSV string, or list."""
    if isinstance(raw, (list, tuple)):
        return normalize_eq_bands([clamp_eq_db(x) for x in raw])
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return [0.0] * EQ_NUM_BANDS
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return normalize_eq_bands(parsed)
            except Exception:
                pass
        try:
            parts = [float(p.strip()) for p in s.split(",") if p.strip()]
            if parts:
                return normalize_eq_bands(parts)
        except Exception:
            pass
    return [0.0] * EQ_NUM_BANDS


def serialize_eq_bands(bands: Sequence[float]) -> str:
    """Serialize 10 band dB floats to a compact JSON string for QSettings."""
    clean = normalize_eq_bands(bands)
    return json.dumps(clean)


def build_mpv_af_string(enabled: bool, preamp_db: float, bands_db: Sequence[float]) -> str:
    """Build an mpv `af` lavfi filter graph string for live 10-band EQ + preamp.

    Returns an empty string when disabled or when all gains are flat (0 dB),
    allowing libmpv to bypass audio filtering completely.
    """
    if not enabled:
        return ""
    pre = clamp_eq_db(preamp_db)
    clean_bands = normalize_eq_bands(bands_db)
    filters: list[str] = []
    if abs(pre) >= 0.05:
        filters.append(f"volume={pre:.1f}dB")
    for freq, gain in zip(EQ_FREQUENCIES, clean_bands):
        if abs(gain) >= 0.05:
            filters.append(f"equalizer=f={freq}:t=o:w=1.0:g={gain:.1f}")
    if not filters:
        return ""
    return f"lavfi=[{','.join(filters)}]"


def compute_peaking_biquad(
    freq_hz: float,
    sample_rate: int,
    gain_db: float,
    q: float = 1.41421356,
) -> tuple[float, float, float, float, float]:
    """Compute normalized RBJ Audio-EQ-Cookbook peaking EQ biquad coefficients.

    Returns (b0, b1, b2, a1, a2) where the difference equation is:
    y[n] = b0*x[n] + b1*x[n-1] + b2*x[n-2] - a1*y[n-1] - a2*y[n-2]
    """
    sr = max(8000, int(sample_rate))
    # Clamp center frequency safely below Nyquist (0.47 * sr)
    f0 = max(10.0, min(float(freq_hz), 0.47 * sr))
    a_amp = math.pow(10.0, float(gain_db) / 40.0)
    w0 = 2.0 * math.pi * f0 / sr
    cos_w0 = math.cos(w0)
    sin_w0 = math.sin(w0)
    alpha = sin_w0 / (2.0 * max(0.1, float(q)))

    b0 = 1.0 + alpha * a_amp
    b1 = -2.0 * cos_w0
    b2 = 1.0 - alpha * a_amp
    a0 = 1.0 + alpha / a_amp
    a1 = -2.0 * cos_w0
    a2 = 1.0 - alpha / a_amp

    inv_a0 = 1.0 / a0
    return (
        b0 * inv_a0,
        b1 * inv_a0,
        b2 * inv_a0,
        a1 * inv_a0,
        a2 * inv_a0,
    )


class BiquadEqualizerProcessor:
    """Thread-safe real-time 10-band stereo IIR biquad peaking EQ for PCM s16le chunks."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._enabled: bool = False
        self._preamp_db: float = 0.0
        self._preamp_lin: float = 1.0
        self._bands_db: list[float] = [0.0] * EQ_NUM_BANDS
        self._sample_rate: int = 48000
        # List of active biquad stages:
        # [b0, b1, b2, a1, a2, z1_l, z2_l, z1_r, z2_r]
        self._stages: list[list[float]] = []
        self._band_states: dict[int, list[float]] = {}

    def configure(
        self,
        enabled: bool,
        preamp_db: float,
        bands_db: Sequence[float],
        sample_rate: int | None = None,
    ) -> None:
        """Update EQ parameters and recompute active biquad coefficients in place."""
        with self._lock:
            new_enabled = bool(enabled)
            new_preamp = clamp_eq_db(preamp_db)
            new_bands = normalize_eq_bands(bands_db)
            new_sr = int(sample_rate) if sample_rate and sample_rate > 0 else self._sample_rate

            sr_changed = new_sr != self._sample_rate
            was_enabled = self._enabled

            self._enabled = new_enabled
            self._preamp_db = new_preamp
            self._preamp_lin = math.pow(10.0, new_preamp / 20.0) if abs(new_preamp) >= 0.05 else 1.0
            self._bands_db = new_bands
            self._sample_rate = new_sr

            if not new_enabled or (not was_enabled) or sr_changed:
                self._band_states.clear()

            self._rebuild_stages_locked()

    def reset_state(self) -> None:
        """Clear IIR filter delay lines (e.g., on track switch or seek)."""
        with self._lock:
            self._band_states.clear()
            for stage in self._stages:
                stage[5] = 0.0
                stage[6] = 0.0
                stage[7] = 0.0
                stage[8] = 0.0

    def _rebuild_stages_locked(self) -> None:
        if not self._enabled:
            self._stages = []
            return
        new_stages: list[list[float]] = []
        for idx, (freq, gain) in enumerate(zip(EQ_FREQUENCIES, self._bands_db)):
            if abs(gain) < 0.05:
                self._band_states.pop(idx, None)
                continue
            b0, b1, b2, a1, a2 = compute_peaking_biquad(freq, self._sample_rate, gain)
            state = self._band_states.get(idx)
            if state is None:
                state = [0.0, 0.0, 0.0, 0.0]
                self._band_states[idx] = state
            new_stages.append([b0, b1, b2, a1, a2, state[0], state[1], state[2], state[3]])
        self._stages = new_stages

    def is_active(self) -> bool:
        """Return True only when EQ is enabled and at least one band or preamp is non-zero."""
        with self._lock:
            if not self._enabled:
                return False
            return bool(self._stages or abs(self._preamp_db) >= 0.05)

    def get_config(self) -> tuple[bool, float, list[float]]:
        """Return current (enabled, preamp_db, bands_db)."""
        with self._lock:
            return self._enabled, self._preamp_db, list(self._bands_db)

    def process_pcm_s16le(self, data: bytes, sample_rate: int = 48000) -> bytes:
        """Apply active preamp and 10-band biquad filter cascade to stereo 16-bit PCM bytes."""
        out, _ = self.process_pcm_s16le_with_volume(
            data, sample_rate=sample_rate, volume=1.0, need_pre_fader=False
        )
        return out

    def process_pcm_s16le_with_volume(
        self,
        data: bytes,
        sample_rate: int = 48000,
        volume: float = 1.0,
        need_pre_fader: bool = False,
    ) -> tuple[bytes, bytes | None]:
        """Single-pass preamp + 10-band biquad EQ + output volume scaling.

        Returns ``(output_pcm, pre_fader_pcm)`` where ``pre_fader_pcm`` is only
        materialized when ``need_pre_fader`` is True (for an active visualizer tap).
        """
        if not data:
            return data, (data if need_pre_fader else None)
        with self._lock:
            if not self._enabled:
                return data, (data if need_pre_fader else None)
            if sample_rate > 0 and sample_rate != self._sample_rate:
                self._sample_rate = int(sample_rate)
                self._band_states.clear()
                self._rebuild_stages_locked()
            stages = self._stages
            preamp_lin = self._preamp_lin
            if not stages and abs(self._preamp_db) < 0.05:
                return data, (data if need_pre_fader else None)

            n_bytes = (len(data) // 4) * 4
            if n_bytes <= 0:
                return data, (data if need_pre_fader else None)
            n_samples = n_bytes // 2
            vol = float(volume)
            apply_vol = 0.001 < vol < 0.999
            mute_out = vol <= 0.001

            samples = struct.unpack(f"<{n_samples}h", data[:n_bytes])

            # Fast path: preamp only (no active EQ bands)
            if not stages:
                soft_clip = _soft_clip_s16
                pre_bytes: bytes | None = None
                if need_pre_fader or (not apply_vol and not mute_out):
                    pre_samples = [soft_clip(s * preamp_lin) for s in samples]
                    pre_bytes = struct.pack(f"<{n_samples}h", *pre_samples)
                if mute_out:
                    return b"\x00" * n_bytes, (pre_bytes if need_pre_fader else None)
                if not apply_vol:
                    assert pre_bytes is not None
                    return pre_bytes, (pre_bytes if need_pre_fader else None)
                combined = preamp_lin * vol
                out_pre = [soft_clip(s * combined) for s in samples]
                return struct.pack(f"<{n_samples}h", *out_pre), pre_bytes

            # De-interleave L/R into float buffers once, applying preamp if needed
            if abs(self._preamp_db) >= 0.05:
                left = [s * preamp_lin for s in samples[0::2]]
                right = [s * preamp_lin for s in samples[1::2]]
            else:
                left = [float(s) for s in samples[0::2]]
                right = [float(s) for s in samples[1::2]]

            # Outer loop over stages keeps biquad coefficients & delay states in CPython fast locals
            active_indices = [idx for idx, gain in enumerate(self._bands_db) if abs(gain) >= 0.05]
            n_frames = len(left)
            for stage in stages:
                b0, b1, b2, a1, a2, z1l, z2l, z1r, z2r = stage
                for i in range(n_frames):
                    xl = left[i]
                    yl = b0 * xl + z1l
                    z1l = b1 * xl - a1 * yl + z2l
                    z2l = b2 * xl - a2 * yl
                    left[i] = yl

                    xr = right[i]
                    yr = b0 * xr + z1r
                    z1r = b1 * xr - a1 * yr + z2r
                    z2r = b2 * xr - a2 * yr
                    right[i] = yr

                stage[5] = z1l
                stage[6] = z2l
                stage[7] = z1r
                stage[8] = z2r

            # Persist updated delay line states back into _band_states
            for band_idx, stage in zip(active_indices, stages):
                st = self._band_states.get(band_idx)
                if st is not None:
                    st[0] = stage[5]
                    st[1] = stage[6]
                    st[2] = stage[7]
                    st[3] = stage[8]

            # Build pre-fader PCM only when needed (visualizer tap or unity volume)
            soft_clip = _soft_clip_s16
            pre_fader_bytes: bytes | None = None
            if need_pre_fader or (not apply_vol and not mute_out):
                pre_out = [0] * n_samples
                pre_out[0::2] = [soft_clip(x) for x in left]
                pre_out[1::2] = [soft_clip(x) for x in right]
                pre_fader_bytes = struct.pack(f"<{n_samples}h", *pre_out)

            if mute_out:
                return b"\x00" * n_bytes, (pre_fader_bytes if need_pre_fader else None)
            if not apply_vol:
                assert pre_fader_bytes is not None
                return pre_fader_bytes, (pre_fader_bytes if need_pre_fader else None)

            # Single-pass volume scaling + soft-limiter directly from float filter output
            out = [0] * n_samples
            out[0::2] = [soft_clip(x * vol) for x in left]
            out[1::2] = [soft_clip(x * vol) for x in right]
            return struct.pack(f"<{n_samples}h", *out), pre_fader_bytes
