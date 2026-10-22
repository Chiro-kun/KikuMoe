import os
import ssl
import tempfile
from pathlib import Path
from unittest.mock import patch

import certifi

import core.ssl_compat
from core.ssl_compat import (
    get_ca_bundle_path,
    get_ca_dir_path,
    get_ssl_context,
    get_websocket_sslopt,
    setup_ssl_environment,
)


def test_get_ca_bundle_path_certifi():
    """By default in test environment, certifi is installed and resolved."""
    bundle = get_ca_bundle_path(force_refresh=True)
    assert bundle is not None
    assert os.path.isfile(bundle)
    assert bundle == certifi.where()


def test_get_ca_bundle_path_env_override(monkeypatch):
    """When SSL_CERT_FILE points to an existing file, it takes precedence."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        dummy_bundle = Path(tmp_dir) / "custom_ca.pem"
        dummy_bundle.write_text("-----BEGIN CERTIFICATE-----\n-----END CERTIFICATE-----\n")

        monkeypatch.setenv("SSL_CERT_FILE", str(dummy_bundle))
        bundle = get_ca_bundle_path(force_refresh=True)
        assert bundle == str(dummy_bundle)


def test_get_ca_bundle_path_system_fallback(monkeypatch):
    """When certifi is absent, it falls back to checking system distribution paths."""
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)

    def fake_isfile(path):
        if path == "/etc/pki/tls/certs/ca-bundle.crt":
            return True
        return False

    with patch.dict("sys.modules", {"certifi": None}):
        with patch("os.path.isfile", side_effect=fake_isfile):
            bundle = get_ca_bundle_path(force_refresh=True)
            assert bundle == "/etc/pki/tls/certs/ca-bundle.crt"


def test_get_ca_dir_path_env_override(monkeypatch):
    """When SSL_CERT_DIR points to a valid directory, it is returned."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        dummy_dir = Path(tmp_dir) / "custom_certs"
        dummy_dir.mkdir()

        monkeypatch.setenv("SSL_CERT_DIR", str(dummy_dir))
        cadir = get_ca_dir_path(force_refresh=True)
        assert cadir == str(dummy_dir)


def test_get_ssl_context_settings():
    """get_ssl_context returns a properly secured SSLContext."""
    ctx = get_ssl_context()
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.check_hostname is True
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    if hasattr(ssl, "TLSVersion"):
        assert ctx.minimum_version == ssl.TLSVersion.TLSv1_2


def test_get_websocket_sslopt():
    """get_websocket_sslopt returns a dictionary with expected SSL keys."""
    opt = get_websocket_sslopt()
    assert isinstance(opt, dict)
    assert "context" in opt
    assert isinstance(opt["context"], ssl.SSLContext)
    assert opt["check_hostname"] is True
    assert opt["cert_reqs"] == ssl.CERT_REQUIRED
    assert "ca_certs" in opt
    assert os.path.isfile(opt["ca_certs"])


def test_setup_ssl_environment(monkeypatch):
    """setup_ssl_environment sets SSL_CERT_FILE and configures default https context."""
    monkeypatch.setattr(core.ssl_compat, "_env_setup_done", False)
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)

    setup_ssl_environment()

    assert "SSL_CERT_FILE" in os.environ
    assert os.path.isfile(os.environ["SSL_CERT_FILE"])
    assert hasattr(ssl, "_create_default_https_context")
    default_ctx = ssl._create_default_https_context()
    assert isinstance(default_ctx, ssl.SSLContext)
    assert default_ctx.check_hostname is True

