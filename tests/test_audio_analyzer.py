"""
Unit tests for core/audio_analyzer.py:
Tests Radix-2 iterative FFT, Hanning windowing, logarithmic frequency grouping,
attack/decay peak gravity smoothing, thread-safe PCM feeding, and fallback simulation.
"""

import math
import struct

from core.audio_analyzer import AudioSpectrumAnalyzer


def test_analyzer_init():
    analyzer = AudioSpectrumAnalyzer()
    assert analyzer.is_playing() is False
    assert len(analyzer._window) == AudioSpectrumAnalyzer.FFT_SIZE
    assert len(analyzer._twiddles) == AudioSpectrumAnalyzer.FFT_SIZE // 2
    assert len(analyzer._rev_table) == AudioSpectrumAnalyzer.FFT_SIZE


def test_analyzer_fft_pure_sine():
    analyzer = AudioSpectrumAnalyzer()
    # Create pure 1000 Hz tone
    freq = 1000.0
    sr = 44100
    n = AudioSpectrumAnalyzer.FFT_SIZE
    samples = [math.sin(2.0 * math.pi * freq * i / sr) for i in range(n)]
    windowed = [complex(samples[i] * analyzer._window[i], 0.0) for i in range(n)]
    fft_res = analyzer._fft(windowed)
    mags = [abs(fft_res[i]) for i in range(1, len(fft_res) // 2)]

    # Expected bin index: 1000 * 256 / 44100 ≈ 5.8 -> bin 5 or 6
    peak_bin = mags.index(max(mags)) + 1
    assert peak_bin in (5, 6, 7)


def test_analyzer_procedural_fallback():
    analyzer = AudioSpectrumAnalyzer()
    analyzer.set_playing(True)
    assert analyzer.is_playing() is True

    # When no PCM is fed, should use procedural harmonic fallback
    bars, bass = analyzer.get_spectrum(num_bars=48)
    assert len(bars) == 48
    assert all(0.0 <= b <= 1.0 for b in bars)
    assert 0.0 <= bass <= 1.0
    # Should not be all zeros when playing
    assert any(b > 0.05 for b in bars)

    # When stopped, values should decay towards zero
    analyzer.set_playing(False)
    for _ in range(40):
        bars, bass = analyzer.get_spectrum(num_bars=48)
    assert all(b < 0.01 for b in bars)
    assert bass < 0.01


def test_analyzer_real_pcm_feed():
    analyzer = AudioSpectrumAnalyzer()
    analyzer.set_playing(True)

    # Generate 16-bit stereo PCM chunk (sine wave 440 Hz)
    freq = 440.0
    sr = 44100
    n_frames = 512
    raw_samples = []
    for i in range(n_frames):
        s = int(24000 * math.sin(2.0 * math.pi * freq * i / sr))
        raw_samples.extend([s, s])  # stereo

    pcm_data = struct.pack(f"<{len(raw_samples)}h", *raw_samples)
    analyzer.feed_pcm(pcm_data)

    bars, bass = analyzer.get_spectrum(num_bars=24)
    assert len(bars) == 24
    assert any(b > 0.1 for b in bars)
    assert 0.0 <= bass <= 1.0


def test_analyzer_edge_cases():
    analyzer = AudioSpectrumAnalyzer()
    analyzer.set_playing(True)

    # Empty data
    analyzer.feed_pcm(b"")
    # Incomplete byte counts
    analyzer.feed_pcm(b"\x01\x02\x03")
    # All zeros (silent audio)
    analyzer.feed_pcm(b"\x00" * 1024)

    bars, bass = analyzer.get_spectrum(num_bars=32)
    assert len(bars) == 32
    assert all(0.0 <= b <= 1.0 for b in bars)

    # Reset
    analyzer.reset()
    assert analyzer._bass_smoothed == 0.0
    assert all(s == 0.0 for s in analyzer._smoothed)
