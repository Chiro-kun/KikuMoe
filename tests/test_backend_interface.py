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
