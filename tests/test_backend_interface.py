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
    """Verify set_volume and get_volume consistency across all backends."""
    backends = [PlayerFFmpeg, PlayerVLC, PlayerMPV]
    for backend in backends:
        player = backend()
        player.set_volume(20)
        assert player.get_volume() == 20
        player.set_volume(85)
        assert player.get_volume() == 85
        player.set_volume(-10)
        assert player.get_volume() == 0
        player.set_volume(150)
        assert player.get_volume() == 100
        player.force_cleanup()
        if hasattr(player, "_player") and getattr(player, "_player") is not None:
            try:
                player._player.terminate()
            except Exception:
                pass
