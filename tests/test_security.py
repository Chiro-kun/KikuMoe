from network.ws_client import NowPlayingWS
from ui.main_window import ListenMoePlayer


def test_cover_url_security_whitelist():
    """Verify that only HTTPS and whitelisted domains are permitted for cover art."""

    def normalize(url: str):
        return ListenMoePlayer._normalize_album_cover_url(None, url)  # type: ignore[arg-type]

    # Valid URLs
    assert (
        normalize("https://cdn.listen.moe/covers/test.jpg")
        == "https://cdn.listen.moe/covers/test.jpg"
    )
    assert (
        normalize("https://listen.moe/covers/sample.png") == "https://listen.moe/covers/sample.png"
    )
    assert normalize("sample.png") == "https://cdn.listen.moe/covers/sample.png"

    # Insecure HTTP rejected
    assert normalize("http://cdn.listen.moe/covers/test.jpg") is None

    # Arbitrary foreign domains rejected
    assert normalize("https://evil.com/malicious.jpg") is None
    assert normalize("https://attacker.org/image.png") is None

    # Loopback / SSRF targets rejected
    assert normalize("http://127.0.0.1:8080/secret") is None
    assert normalize("http://localhost/admin") is None
    assert normalize("https://169.254.169.254/latest/meta-data/") is None


def test_ws_client_shutdown_cancels_reconnect_timer():
    """Verify that NowPlayingWS.shutdown cancels any pending reconnect timer."""
    client = NowPlayingWS(
        on_now_playing=lambda *args: None,
        on_error_text=lambda err: None,
        on_closed_text=lambda msg: None,
    )
    client.ws_should_reconnect = True

    # Simulate shutdown
    client.shutdown()

    assert not client.ws_should_reconnect
    assert client._reconnect_timer is None
