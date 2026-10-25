import inspect

from audio.player_ffmpeg import PlayerFFmpeg
from audio.player_mpv import PlayerMPV
from audio.player_vlc import PlayerVLC


def test_player_backends_interface_consistency():
    """Verify that all three audio backends implement the expected public methods."""
    required_methods = [
        "is_ready",
        "play_url",
        "stop",
        "pause_toggle",
        "set_volume",
        "get_volume",
        "set_mute",
        "get_mute",
        "force_cleanup",
        "get_init_error",
    ]

    backends = [PlayerFFmpeg, PlayerVLC, PlayerMPV]

    for backend in backends:
        for method_name in required_methods:
            assert hasattr(backend, method_name), (
                f"{backend.__name__} is missing required method '{method_name}'"
            )
            method = getattr(backend, method_name)
            assert inspect.isfunction(method), f"{backend.__name__}.{method_name} is not callable"


def test_player_backends_volume_scaling():
    """Verify set_volume and get_volume consistency and perceptual mapping across all backends."""
    # Mathematical mapping functions
    assert PlayerMPV._to_backend_volume(0) == 0.0
    assert PlayerMPV._to_backend_volume(100) == 100.0
    assert 44.0 < PlayerMPV._to_backend_volume(20) < 45.0
    assert PlayerMPV._to_backend_volume(-5) == 0.0
    assert PlayerMPV._to_backend_volume(120) == 100.0

    assert PlayerVLC._to_backend_volume(0) == 0
    assert PlayerVLC._to_backend_volume(100) == 100
    assert PlayerVLC._to_backend_volume(20) == 45
    assert PlayerVLC._to_backend_volume(-5) == 0
    assert PlayerVLC._to_backend_volume(120) == 100

    # PlayerFFmpeg volume behavior
    ffmpeg = PlayerFFmpeg()
    ffmpeg.set_volume(20)
    assert ffmpeg.get_volume() == 20
    assert 0.08 < ffmpeg._volume < 0.10
    ffmpeg.set_volume(100)
    assert ffmpeg.get_volume() == 100
    assert ffmpeg._volume == 1.0
    ffmpeg.set_volume(0)
    assert ffmpeg.get_volume() == 0
    assert ffmpeg._volume == 0.0
    ffmpeg.set_volume(-10)
    assert ffmpeg.get_volume() == 0
    ffmpeg.set_volume(150)
    assert ffmpeg.get_volume() == 100


def test_player_mpv_find_library_resolution(monkeypatch):
    """Verify libmpv path detection with explicit environment overrides and fallback behavior."""
    import tempfile
    from pathlib import Path

    from audio.player_mpv import _find_libmpv_path

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        # Case 1: MPV_PATH override pointing to an existing file
        fake_lib = tmp_path / "libmpv.so.2"
        fake_lib.write_text("dummy", encoding="utf-8")
        monkeypatch.setenv("MPV_PATH", str(fake_lib))
        assert _find_libmpv_path() == str(fake_lib.resolve())

        # Case 2: MPV_DIR override containing candidate library on Linux
        monkeypatch.delenv("MPV_PATH", raising=False)
        monkeypatch.setenv("MPV_DIR", str(tmp_path))
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setattr("audio.player_mpv._IS_WIN32", False)
        assert _find_libmpv_path() == str(fake_lib.resolve())


def test_silence_stderr_exception_propagation():
    """Verify silence_stderr propagates exceptions raised in its block without masking them."""
    import pytest

    from core.logger import silence_stderr

    with pytest.raises(ZeroDivisionError):
        with silence_stderr():
            _ = 1 / 0


def test_player_vlc_plugin_path_detection(monkeypatch):
    """Verify VLC_PLUGIN_PATH detection does not crash and respects existing environment."""
    from audio.player_vlc import PlayerVLC

    monkeypatch.setenv("VLC_PLUGIN_PATH", "/custom/vlc/plugins")
    player = PlayerVLC()
    # Should not crash during initialization
    assert hasattr(player, "is_ready")


def test_player_ffmpeg_bin_discovery(monkeypatch):
    """Verify _find_ffmpeg_bin respects FFMPEG_PATH and fallback behavior."""
    import tempfile
    from pathlib import Path

    from audio.player_ffmpeg import _find_ffmpeg_bin

    with tempfile.TemporaryDirectory() as tmp_dir:
        fake_ffmpeg = Path(tmp_dir) / "fake_ffmpeg.exe"
        fake_ffmpeg.write_text("dummy", encoding="utf-8")

        # FFMPEG_PATH takes precedence
        monkeypatch.setenv("FFMPEG_PATH", str(fake_ffmpeg))
        assert _find_ffmpeg_bin() == str(fake_ffmpeg)

        # Non-existent FFMPEG_PATH falls back
        monkeypatch.setenv("FFMPEG_PATH", str(fake_ffmpeg) + "_nonexistent")
        res = _find_ffmpeg_bin()
        assert res is not None


def test_player_ffmpeg_sample_rate_negotiation(monkeypatch):
    """Verify _open_pyaudio_stream negotiates fallback sample rates when preferred rate fails."""
    from audio.player_ffmpeg import PlayerFFmpeg

    player = PlayerFFmpeg()

    class FakePyAudio:
        def __init__(self):
            self.opened_rates = []

        def get_device_info_by_index(self, idx):
            return {"defaultSampleRate": 48000.0}

        def get_default_output_device_info(self):
            return {"defaultSampleRate": 44100.0}

        def open(self, **kwargs):
            rate = kwargs.get("rate")
            self.opened_rates.append(rate)
            # Simulate 48000 failing on device, but 44100 succeeding
            if kwargs.get("output_device_index") == 99 and rate == 48000:
                raise OSError(-9997, "Invalid sample rate")
            return "fake_stream"

    fake_pa = FakePyAudio()
    player._pyaudio_instance = fake_pa

    stream, rate = player._open_pyaudio_stream(99)
    assert stream == "fake_stream"
    assert rate == 44100
    assert 48000 in fake_pa.opened_rates


def test_player_ffmpeg_is_ready_requires_ffmpeg(monkeypatch):
    """Verify PlayerFFmpeg.is_ready() returns False when ffmpeg is not available."""
    from audio.player_ffmpeg import PlayerFFmpeg

    player = PlayerFFmpeg()
    monkeypatch.setattr(player, "_check_ffmpeg", lambda: False)
    assert not player.is_ready()


def test_logger_file_and_ring_buffer():
    """Verify logger writes to log file and captures lines in recent logs buffer."""
    import os

    from core.logger import _SafeTextStream, get_log_file_path, get_logger, get_recent_logs

    log_path = get_log_file_path()
    assert log_path.endswith("kikumoe.log")

    lg = get_logger("TestLogger")
    test_msg = "UniqueTestMessage_42_AudioCheck"
    lg.info(test_msg)

    # Check ring buffer
    recent = get_recent_logs()
    assert any(test_msg in line for line in recent)

    # Check file
    assert os.path.isfile(log_path)
    with open(log_path, encoding="utf-8") as f:
        file_content = f.read()
    assert test_msg in file_content

    # Safe text stream with None
    stream = _SafeTextStream(None)
    assert stream.write("hello") == 5
    assert not stream.isatty()


def test_player_ffmpeg_meipass_discovery(monkeypatch):
    """Verify _find_ffmpeg_bin resolves ffmpeg from sys._MEIPASS when frozen."""
    import sys
    import tempfile
    from pathlib import Path

    from audio.player_ffmpeg import _find_ffmpeg_bin

    with tempfile.TemporaryDirectory() as tmp_dir:
        fake_ffmpeg = Path(tmp_dir) / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
        fake_ffmpeg.write_text("dummy", encoding="utf-8")

        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_dir), raising=False)
        monkeypatch.delenv("FFMPEG_PATH", raising=False)

        found = _find_ffmpeg_bin()
        assert found == str(fake_ffmpeg.resolve())


def test_linux_audio_diagnostics_probe(monkeypatch):
    """Verify probe_linux_audio_environment and log_audio_diagnostics execute safely."""
    import logging
    import tempfile
    from pathlib import Path

    from audio.diagnostics import log_audio_diagnostics, probe_linux_audio_environment

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        fake_pw = tmp_path / "pipewire-0"
        fake_pw.write_text("", encoding="utf-8")

        monkeypatch.setenv("PIPEWIRE_RUNTIME_DIR", str(tmp_path))
        monkeypatch.setenv("PULSE_SERVER", "unix:/tmp/pulse-socket")
        monkeypatch.setenv("SSL_CERT_FILE", "/fake/cert.pem")

        env = probe_linux_audio_environment()
        assert env["pipewire"] is True
        assert env["pulseaudio"] is True
        assert env["ssl_cert_file"] == "/fake/cert.pem"

        # Ensure log_audio_diagnostics runs without exception
        logger = logging.getLogger("TestAudioDiag")
        monkeypatch.setattr("audio.diagnostics._IS_WIN32", False)
        log_audio_diagnostics(logger)


def test_kikumoe_spec_audio_excludes():
    """Verify that kikumoe.spec includes necessary Linux host audio library excludes."""
    with open("kikumoe.spec", encoding="utf-8") as f:
        spec_content = f.read()

    expected_excludes = [
        "libvlc",
        "libvlccore",
        "libasound",
        "libpulse",
        "libjack",
        "libpipewire",
        "libspa",
        "libasound_module",
        "libstdc++",
        "libgcc_s",
    ]
    for lib in expected_excludes:
        assert f'"{lib}"' in spec_content, f"kikumoe.spec missing expected exclude: {lib}"


def test_smooth_progress_bar_live_mode():
    """Verify SmoothProgressBar supports live mode toggling and state inspection."""
    import os

    from PyQt6.QtWidgets import QApplication

    from ui.main_window import SmoothProgressBar

    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    _ = QApplication.instance() or QApplication(["pytest"])

    bar = SmoothProgressBar()
    assert not bar.is_live_mode()

    bar.set_live_mode(True)
    assert bar.is_live_mode()
    assert bar._live_mode is True

    bar.set_live_mode(False)
    assert not bar.is_live_mode()
    assert bar._live_mode is False


def test_audio_diagnostics_mpv_error_formatting(monkeypatch):
    """Verify log_audio_diagnostics formats MPV error details cleanly when unavailable."""
    import logging

    from audio.diagnostics import log_audio_diagnostics

    logger = logging.getLogger("TestMpvDiag")
    monkeypatch.setattr("audio.diagnostics._IS_WIN32", False)
    monkeypatch.setattr("audio.player_mpv.mpv", None)
    monkeypatch.setattr(
        "audio.player_mpv._mpv_import_error",
        OSError("Cannot open shared object file: No such file"),
    )
    monkeypatch.setattr("audio.player_mpv._found_libmpv", "/usr/lib/libmpv.so.2.5.0")

    # Should run and log without raising any exception
    log_audio_diagnostics(logger)
