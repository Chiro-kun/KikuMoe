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
