"""
Linux & Cross-Platform Audio Diagnostics Module for KikuMoe.
Probes host audio daemons (PipeWire, PulseAudio, ALSA) and backends (FFmpeg, PyAudio, MPV, VLC),
logging a structured summary to the application logger and DevConsole.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from typing import Any

_IS_WIN32 = sys.platform == "win32"


def probe_linux_audio_environment() -> dict[str, Any]:
    """Inspects Linux audio servers, socket paths, and certificates."""
    uid = getattr(os, "getuid", lambda: 1000)()
    pw_dir = os.environ.get("PIPEWIRE_RUNTIME_DIR", f"/run/user/{uid}")
    has_pipewire = os.path.exists(os.path.join(pw_dir, "pipewire-0"))

    pulse_native = os.path.join(f"/run/user/{uid}", "pulse", "native")
    has_pulse = os.path.exists(pulse_native) or bool(os.environ.get("PULSE_SERVER"))

    ssl_cert = os.environ.get("SSL_CERT_FILE")
    if not ssl_cert:
        for c in (
            "/etc/ssl/certs/ca-certificates.crt",
            "/etc/pki/tls/certs/ca-bundle.crt",
            "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",
            "/etc/ssl/ca-bundle.pem",
            "/etc/ssl/cert.pem",
        ):
            if os.path.isfile(c):
                ssl_cert = c
                break

    return {
        "pipewire": has_pipewire,
        "pipewire_socket": os.path.join(pw_dir, "pipewire-0") if has_pipewire else None,
        "pulseaudio": has_pulse,
        "pulse_server": os.environ.get("PULSE_SERVER") or (pulse_native if has_pulse else None),
        "ssl_cert_file": ssl_cert or "Not found",
    }


def log_audio_diagnostics(log: logging.Logger) -> None:
    """Logs a concise, human-readable summary of host audio servers and backend readiness."""
    if _IS_WIN32:
        return

    env = probe_linux_audio_environment()
    pw_str = f"Active ({env['pipewire_socket']})" if env["pipewire"] else "Not detected"
    pa_str = f"Active ({env['pulse_server']})" if env["pulseaudio"] else "Not detected"
    cert_str = env["ssl_cert_file"]

    log.info("[STARTUP] Linux Audio Environment:")
    log.info("  - PipeWire:   %s", pw_str)
    log.info("  - PulseAudio: %s", pa_str)
    log.info("  - SSL CA:     %s", cert_str)

    # Check backends
    from audio.player_ffmpeg import _find_ffmpeg_bin

    ffmpeg_path = _find_ffmpeg_bin()
    is_valid_bin = bool(
        ffmpeg_path and (shutil.which(ffmpeg_path) is not None or os.path.isfile(ffmpeg_path))
    )
    ffmpeg_status = f"Ready ({ffmpeg_path})" if is_valid_bin else f"Missing ('{ffmpeg_path}')"

    # PyAudio / PortAudio
    pa_status = "Unavailable"
    try:
        import pyaudio

        from core.logger import silence_stderr

        with silence_stderr():
            pa = pyaudio.PyAudio()
            try:
                apis = []
                for i in range(pa.get_host_api_count()):
                    info = pa.get_host_api_info_by_index(i)
                    if isinstance(info, dict):
                        apis.append(str(info.get("name", "")))
                def_dev = pa.get_default_output_device_info()
                def_name = def_dev.get("name", "Unknown") if isinstance(def_dev, dict) else "None"
                api_labels = ", ".join(apis) if apis else "None"
                pa_status = f"Ready (APIs: {api_labels}; Default: {def_name})"
            finally:
                pa.terminate()
    except Exception as e:
        pa_status = f"Failed ({e})"

    # MPV
    from audio.player_mpv import _found_libmpv, mpv

    if mpv is not None:
        mpv_status = f"Ready ({_found_libmpv or 'system library'})"
    else:
        mpv_status = f"Unavailable ({_found_libmpv or 'libmpv not found'})"

    # VLC
    from audio.player_vlc import vlc

    if vlc is not None:
        vlc_status = "Available (python-vlc loaded)"
    else:
        vlc_status = "Unavailable (python-vlc / libvlc not found)"

    log.info("[STARTUP] Audio Backends:")
    log.info("  - FFmpeg:    %s", ffmpeg_status)
    log.info("  - PortAudio: %s", pa_status)
    log.info("  - MPV:       %s", mpv_status)
    log.info("  - VLC:       %s", vlc_status)
