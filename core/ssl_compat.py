"""SSL compatibility and CA discovery for cross-platform Linux and Windows environments."""

import logging
import os
import ssl
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("kikumoe.ssl")

# Well-known CA bundle paths across various Linux distributions and Unix-like OSes:
# - Debian / Ubuntu / Arch / Gentoo: /etc/ssl/certs/ca-certificates.crt
# - Fedora / RHEL 6/7 / CentOS: /etc/pki/tls/certs/ca-bundle.crt
# - Fedora / RHEL 8/9 / Rocky / Alma: /etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem
# - openSUSE / SUSE: /etc/ssl/ca-bundle.pem
# - Alpine / FreeBSD / OpenBSD / macOS: /etc/ssl/cert.pem
# - OpenELEC: /etc/pki/tls/cacert.pem
_SYSTEM_CA_BUNDLE_CANDIDATES: Tuple[str, ...] = (
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/pki/tls/certs/ca-bundle.crt",
    "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",
    "/etc/ssl/ca-bundle.pem",
    "/etc/ssl/cert.pem",
    "/etc/pki/tls/cacert.pem",
    "/usr/share/ssl/certs/ca-bundle.crt",
)

# Well-known CA certificate directories (hashed certificate symlinks)
_SYSTEM_CA_DIR_CANDIDATES: Tuple[str, ...] = (
    "/etc/ssl/certs",
    "/etc/pki/tls/certs",
    "/etc/pki/ca-trust/extracted/pem",
    "/system/etc/security/cacerts",
)

_cached_ca_bundle: Optional[str] = None
_cached_ca_dir: Optional[str] = None
_env_setup_done: bool = False


def get_ca_bundle_path(force_refresh: bool = False) -> Optional[str]:
    """Finds a valid root CA certificates bundle file.

    Probes in the following order:
    1. SSL_CERT_FILE environment variable (if pointing to an existing file)
    2. Bundled certifi CA bundle (Mozilla root store)
    3. Host system CA bundle paths for all major Linux distributions
    """
    global _cached_ca_bundle
    if _cached_ca_bundle is not None and not force_refresh:
        if os.path.isfile(_cached_ca_bundle):
            return _cached_ca_bundle

    # 1. Custom user/system environment override
    env_cert = os.environ.get("SSL_CERT_FILE")
    if env_cert and os.path.isfile(env_cert):
        _cached_ca_bundle = env_cert
        return _cached_ca_bundle

    # 2. Bundled certifi package
    try:
        import certifi

        certifi_path = certifi.where()
        if certifi_path and os.path.isfile(certifi_path):
            _cached_ca_bundle = certifi_path
            return _cached_ca_bundle
    except Exception:
        pass

    # 3. Known host system CA bundle locations
    for path in _SYSTEM_CA_BUNDLE_CANDIDATES:
        try:
            if os.path.isfile(path):
                _cached_ca_bundle = path
                return _cached_ca_bundle
        except Exception:
            continue

    return None


def get_ca_dir_path(force_refresh: bool = False) -> Optional[str]:
    """Finds a valid directory containing trusted CA certificates."""
    global _cached_ca_dir
    if _cached_ca_dir is not None and not force_refresh:
        if os.path.isdir(_cached_ca_dir):
            return _cached_ca_dir

    env_dir = os.environ.get("SSL_CERT_DIR")
    if env_dir and os.path.isdir(env_dir):
        _cached_ca_dir = env_dir
        return _cached_ca_dir

    for cdir in _SYSTEM_CA_DIR_CANDIDATES:
        try:
            if os.path.isdir(cdir):
                _cached_ca_dir = cdir
                return _cached_ca_dir
        except Exception:
            continue

    return None


def get_ssl_context(purpose: Any = ssl.Purpose.SERVER_AUTH) -> ssl.SSLContext:
    """Creates a hardened SSLContext that uses the resolved CA certificates bundle.

    Ensures hostname verification and CERT_REQUIRED are enabled, with minimum TLS 1.2
    where supported.
    """
    ca_bundle = get_ca_bundle_path()
    ca_dir = get_ca_dir_path()

    ctx: Optional[ssl.SSLContext] = None
    try:
        if ca_bundle:
            ctx = ssl.create_default_context(purpose=purpose, cafile=ca_bundle, capath=ca_dir)
        else:
            ctx = ssl.create_default_context(purpose=purpose, capath=ca_dir)
    except Exception:
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            if ca_bundle or ca_dir:
                ctx.load_verify_locations(cafile=ca_bundle, capath=ca_dir)
        except Exception:
            ctx = ssl.create_default_context(purpose=purpose)

    # Also load system default certificates (Windows store, macOS keychain, host OpenSSL)
    try:
        ctx.load_default_certs(purpose)
    except Exception:
        pass

    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED

    if hasattr(ssl, "TLSVersion"):
        try:
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        except Exception:
            pass

    return ctx


def get_websocket_sslopt() -> Dict[str, Any]:
    """Returns sslopt dictionary configured with verified SSL context for websocket-client."""
    sslopt: Dict[str, Any] = {
        "context": get_ssl_context(),
        "check_hostname": True,
        "cert_reqs": ssl.CERT_REQUIRED,
    }
    ca_bundle = get_ca_bundle_path()
    if ca_bundle:
        sslopt["ca_certs"] = ca_bundle
    ca_dir = get_ca_dir_path()
    if ca_dir:
        sslopt["ca_cert_dir"] = ca_dir
    return sslopt


def setup_ssl_environment() -> None:
    """Configures process-level SSL environment variables and default HTTPS context.

    Should be called as early as possible during application startup.
    """
    global _env_setup_done
    if _env_setup_done:
        return
    _env_setup_done = True

    try:
        ca_bundle = get_ca_bundle_path()
        if ca_bundle:
            cur_file = os.environ.get("SSL_CERT_FILE")
            if not cur_file or not os.path.isfile(cur_file):
                os.environ["SSL_CERT_FILE"] = ca_bundle
                logger.debug("Configured SSL_CERT_FILE=%s", ca_bundle)

        ca_dir = get_ca_dir_path()
        if ca_dir:
            cur_dir = os.environ.get("SSL_CERT_DIR")
            if not cur_dir or not os.path.isdir(cur_dir):
                os.environ["SSL_CERT_DIR"] = ca_dir
                logger.debug("Configured SSL_CERT_DIR=%s", ca_dir)

        # Ensure Python standard library urllib/http uses our verified context factory
        def _https_context_factory(*args: Any, **kwargs: Any) -> ssl.SSLContext:
            return get_ssl_context()

        ssl._create_default_https_context = _https_context_factory  # type: ignore[attr-defined]
    except Exception as exc:
        logger.warning("setup_ssl_environment failed non-critically: %s", exc)
