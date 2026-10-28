from __future__ import annotations

import math
import os
import sys
from pathlib import Path
from typing import Any, Callable

from core.constants import APP_NAME, APP_SETTINGS, APP_VERSION, KEY_AUDIO_DEVICE_INDEX, ORG_NAME
from core.logger import PORTAUDIO_LOCK, get_logger, silence_stderr

_IS_WIN32 = sys.platform == "win32"


def _find_libvlc_path() -> str | None:
    """Cerca la libreria dinamica libvlc (DLL su Windows, .so su Linux, .dylib su macOS)
    in modo robusto e ne restituisce il percorso assoluto."""
    env_vlc_path = os.environ.get("VLC_PATH") or os.environ.get("PYTHON_VLC_LIB_PATH")
    if env_vlc_path and os.path.isfile(env_vlc_path):
        return str(Path(env_vlc_path).resolve())

    candidate_dirs: list[Path] = []

    for env_var in ("VLC_DIR", "PYTHON_VLC_MODULE_PATH"):
        env_dir = os.environ.get(env_var)
        if env_dir:
            candidate_dirs.append(Path(env_dir))

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidate_dirs.append(Path(meipass))
        exe_dir = Path(sys.executable).resolve().parent
        candidate_dirs.append(exe_dir)
        if not _IS_WIN32:
            candidate_dirs.append(exe_dir.parent / "lib")
            candidate_dirs.append(exe_dir / "lib")
    else:
        script_dir = Path(__file__).resolve().parent
        repo_root = script_dir.parent
        candidate_dirs.append(repo_root)
        candidate_dirs.append(script_dir)
        if _IS_WIN32:
            candidate_dirs.append(repo_root / "packaging" / "windows")

    if _IS_WIN32:
        names = ["libvlc.dll"]
        candidate_dirs.extend(
            [
                Path(r"C:\Program Files\VideoLAN\VLC"),
                Path(r"C:\Program Files (x86)\VideoLAN\VLC"),
            ]
        )
    elif sys.platform == "darwin":
        names = ["libvlc.dylib"]
        candidate_dirs.extend(
            [
                Path("/Applications/VLC.app/Contents/MacOS/lib"),
                Path("/opt/homebrew/lib"),
                Path("/usr/local/lib"),
            ]
        )
    else:
        names = ["libvlc.so.5", "libvlc.so.12", "libvlc.so"]
        candidate_dirs.extend(
            [
                Path("/usr/lib"),
                Path("/usr/lib/x86_64-linux-gnu"),
                Path("/usr/lib64"),
                Path("/usr/local/lib"),
                Path("/app/lib"),
            ]
        )

    unique_dirs: list[Path] = []
    seen = set()
    for d in candidate_dirs:
        try:
            resolved = d.resolve()
            if resolved not in seen and resolved.is_dir():
                seen.add(resolved)
                unique_dirs.append(resolved)
        except Exception:
            pass

    for name in names:
        for d in unique_dirs:
            candidate = d / name
            try:
                if candidate.is_file():
                    return str(candidate.resolve())
            except Exception:
                pass

    if not _IS_WIN32 and sys.platform != "darwin":
        try:
            import subprocess

            for ldconfig_bin in ("/sbin/ldconfig", "ldconfig"):
                try:
                    res = subprocess.run(
                        [ldconfig_bin, "-p"],
                        capture_output=True,
                        text=True,
                        timeout=2,
                        check=False,
                    )
                    if res.returncode == 0 and res.stdout:
                        lines = res.stdout.splitlines()
                        for name in names:
                            for line in lines:
                                if name in line and "=>" in line:
                                    target = line.split("=>", 1)[1].strip()
                                    if target and os.path.isfile(target):
                                        return str(Path(target).resolve())
                        break
                except (FileNotFoundError, PermissionError):
                    continue
        except Exception:
            pass

    try:
        import ctypes.util

        lib_name = ctypes.util.find_library("vlc")
        if lib_name:
            if os.path.isabs(lib_name) and os.path.isfile(lib_name):
                return str(Path(lib_name).resolve())
            for d in unique_dirs:
                candidate = d / lib_name
                try:
                    if candidate.is_file():
                        return str(candidate.resolve())
                except Exception:
                    pass
    except Exception:
        pass

    return None


_found_libvlc = _find_libvlc_path()
if _found_libvlc:
    os.environ["PYTHON_VLC_LIB_PATH"] = _found_libvlc
    _vlc_dir = str(Path(_found_libvlc).parent)
    if _IS_WIN32:
        os.environ["PATH"] = _vlc_dir + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(_vlc_dir)
            except Exception:
                pass

_vlc_import_error: Exception | None = None
_orig_vlc_find_library = None
if _found_libvlc and not _IS_WIN32:
    try:
        import ctypes.util

        _orig_vlc_find_library = ctypes.util.find_library

        def _custom_vlc_find_library(name: str) -> str | None:
            if name == "vlc":
                return _found_libvlc
            return _orig_vlc_find_library(name) if _orig_vlc_find_library else None

        ctypes.util.find_library = _custom_vlc_find_library
    except Exception:
        pass

vlc: Any = None
if not _IS_WIN32 and not _found_libvlc:
    _vlc_import_error = OSError(
        "libvlc was not found on this system. Please install VLC "
        "(e.g. 'sudo pacman -S vlc' on Arch, 'sudo apt install vlc' on Debian/Ubuntu, "
        "or 'sudo dnf install vlc' on Fedora)."
    )
else:
    try:
        import vlc as _vlc_module

        vlc = _vlc_module
    except Exception as e:
        vlc = None
        _vlc_import_error = e
    finally:
        if _orig_vlc_find_library is not None:
            try:
                import ctypes.util

                ctypes.util.find_library = _orig_vlc_find_library
            except Exception:
                pass


class PlayerVLC:
    def __init__(
        self,
        libvlc_path: str | None = None,
        on_event: Callable[[str, int | None], None] | None = None,
        network_caching_ms: int | None = None,
    ) -> None:
        self._vlc_path = libvlc_path
        self._on_event = on_event
        self._network_caching_ms: int | None = (
            int(network_caching_ms) if network_caching_ms is not None else None
        )
        self.instance: Any | None = None
        self.player: Any | None = None
        self._muted: bool = False
        self._volume: int = 100
        self._ready: bool = False
        self._init_error: str | None = None
        # Set when stop()/play_url() is in progress so that stale VLC events
        # (EndReached, EncounteredError) fired during teardown do not trigger
        # restart logic in the main window.
        self._stopping: bool = False
        self.log = get_logger("PlayerVLC")
        # Build dynamic User-Agent similar to ffmpeg backend
        try:
            self._user_agent = f"{APP_NAME}/{APP_VERSION}"
        except Exception:
            self._user_agent = "KikuMoe/1.11.0"
        self._init_vlc()

    def _init_vlc(self) -> None:
        self._ready = False
        self._init_error = None
        if not _IS_WIN32 and not _found_libvlc:
            self._init_error = (
                "libvlc was not found on this system. Please install VLC "
                "(e.g. 'sudo pacman -S vlc' on Arch, 'sudo apt install vlc' on Debian/Ubuntu, "
                "or 'sudo dnf install vlc' on Fedora)."
            )
            self.log.error("[BACKEND] PlayerVLC: %s", self._init_error)
            return
        if vlc is None:
            err = f" ({_vlc_import_error})" if _vlc_import_error else ""
            self._init_error = f"python-vlc module not installed or unavailable{err}"
            self.log.error("[BACKEND] PlayerVLC: %s", self._init_error)
            return
        # Setup plugin path if provided by user setting, otherwise detect system plugins
        if self._vlc_path and os.path.isdir(self._vlc_path):
            try:
                if _IS_WIN32:
                    if hasattr(os, "add_dll_directory"):
                        os.add_dll_directory(self._vlc_path)  # type: ignore[attr-defined]
                    plugins_path = os.path.join(self._vlc_path, "plugins")
                    if os.path.isdir(plugins_path):
                        os.environ["VLC_PLUGIN_PATH"] = plugins_path
                else:
                    plugins_path = os.path.join(self._vlc_path, "plugins")
                    if os.path.isdir(plugins_path):
                        os.environ["VLC_PLUGIN_PATH"] = plugins_path
            except Exception as e:
                self.log.debug("[DEBUG] _init_vlc: custom plugin path setup failed: %s", e)
        elif not os.environ.get("VLC_PLUGIN_PATH"):
            # Auto-detect plugin directory if not explicitly configured
            plugin_candidates: list[Path] = []
            if _IS_WIN32:
                if getattr(sys, "frozen", False):
                    meipass = getattr(sys, "_MEIPASS", None)
                    if meipass:
                        plugin_candidates.append(Path(meipass) / "plugins")
                    plugin_candidates.append(Path(sys.executable).resolve().parent / "plugins")
                plugin_candidates.extend(
                    [
                        Path(r"C:\Program Files\VideoLAN\VLC\plugins"),
                        Path(r"C:\Program Files (x86)\VideoLAN\VLC\plugins"),
                    ]
                )
            else:
                # Linux / Unix
                if getattr(sys, "frozen", False):
                    meipass = getattr(sys, "_MEIPASS", None)
                    if meipass:
                        plugin_candidates.append(Path(meipass) / "plugins")
                        plugin_candidates.append(Path(meipass) / "vlc" / "plugins")
                    exe_parent = Path(sys.executable).resolve().parent
                    plugin_candidates.append(exe_parent / "plugins")
                    plugin_candidates.append(exe_parent.parent / "lib" / "vlc" / "plugins")
                plugin_candidates.extend(
                    [
                        Path("/usr/lib/x86_64-linux-gnu/vlc/plugins"),
                        Path("/usr/lib/aarch64-linux-gnu/vlc/plugins"),
                        Path("/usr/lib64/vlc/plugins"),
                        Path("/usr/lib/vlc/plugins"),
                        Path("/usr/local/lib/vlc/plugins"),
                        Path("/app/lib/vlc/plugins"),
                    ]
                )
            for p_dir in plugin_candidates:
                try:
                    if p_dir.is_dir():
                        os.environ["VLC_PLUGIN_PATH"] = str(p_dir.resolve())
                        self.log.debug("[DEBUG] _init_vlc: found VLC_PLUGIN_PATH=%s", p_dir)
                        break
                except Exception:
                    pass
        try:
            inst_opts = ["--quiet", "--no-video-title-show"]
            if self._network_caching_ms is not None:
                try:
                    nc = max(0, int(self._network_caching_ms))
                    inst_opts.append(f"--network-caching={nc}")
                except Exception:
                    pass
            # Add options to reduce verbose output and improve stream handling
            inst_opts.extend(
                [
                    "--intf",
                    "dummy",  # No interface
                    "--quiet",  # Reduce output
                    "--no-video-title-show",  # No video title
                    "--no-stats",  # No statistics
                    "--no-plugins-cache",  # No plugins cache
                    "--http-reconnect",  # Reconnect on HTTP errors
                    "--http-continuous",  # Continuous HTTP streaming
                    "--live-caching=1000",  # Small live caching for smooth playback
                ]
            )
            # On Linux, prefer PulseAudio if the socket or daemon is active,
            # but allow libvlc to fall back to ALSA rather than forcing pulse exclusively.
            if not _IS_WIN32:
                uid = getattr(os, "getuid", lambda: 1000)()
                pw_sock = os.environ.get("PIPEWIRE_RUNTIME_DIR", f"/run/user/{uid}")
                has_pipewire = os.path.exists(os.path.join(pw_sock, "pipewire-0"))
                pulse_native = os.path.join(f"/run/user/{uid}", "pulse", "native")
                has_pulse = os.path.exists(pulse_native) or bool(os.environ.get("PULSE_SERVER"))
                if has_pulse or has_pipewire:
                    inst_opts.append("--aout=pulse,alsa")
            # Set HTTP User-Agent globally for VLC instance
            if getattr(self, "_user_agent", None):
                inst_opts.append(f"--http-user-agent={self._user_agent}")
            self.log.debug("[DEBUG] _init_vlc: creating Instance with opts=%s", inst_opts)
            with silence_stderr():
                self.instance = vlc.Instance(inst_opts)
            if self.instance is None:
                self._init_error = (
                    "vlc.Instance() creation failed "
                    "(libvlc not found, no plugins, or incompatible architecture)"
                )
                self.log.error("[BACKEND] %s", self._init_error)
                return
            self.player = self.instance.media_player_new()
            if self.player is None:
                self._init_error = "media_player_new() creation failed"
                self.log.error("[BACKEND] PlayerVLC: %s", self._init_error)
                return
            self.log.debug("[DEBUG] _init_vlc: instance and player created OK")
            try:
                em = self.player.event_manager()
                em.event_attach(vlc.EventType.MediaPlayerOpening, self._handle_event)
                em.event_attach(vlc.EventType.MediaPlayerBuffering, self._handle_event)
                em.event_attach(vlc.EventType.MediaPlayerPlaying, self._handle_event)
                em.event_attach(vlc.EventType.MediaPlayerPaused, self._handle_event)
                em.event_attach(vlc.EventType.MediaPlayerStopped, self._handle_event)
                em.event_attach(vlc.EventType.MediaPlayerEndReached, self._handle_event)
                em.event_attach(vlc.EventType.MediaPlayerEncounteredError, self._handle_event)
                self.log.debug("[DEBUG] _init_vlc: events attached")
            except Exception as e:
                self.log.debug("[DEBUG] _init_vlc: event attach failed: %s", e)
            self.player.audio_set_volume(self._to_backend_volume(self._volume))
            self.player.audio_set_mute(self._muted)
            self._ready = True
            # Apply explicit device selection (Linux/pulse only, best-effort)
            self._apply_linux_audio_device()
            self.log.debug("[DEBUG] _init_vlc: ready")
        except Exception as e:
            self._init_error = f"VLC initialization error: {e}"
            self.log.error("[BACKEND] PlayerVLC: %s", self._init_error)
            self.instance = None
            self.player = None
            self._ready = False

    def _get_stored_device_name(self) -> str | None:
        """Return the human-readable PortAudio name of the user-configured output device,
        or None when the setting is absent or unresolvable."""
        try:
            from PyQt6.QtCore import QSettings

            settings = QSettings(ORG_NAME, APP_SETTINGS)
            val = settings.value(KEY_AUDIO_DEVICE_INDEX, "")
            if val in (None, ""):
                return None
            import pyaudio

            with PORTAUDIO_LOCK, silence_stderr():
                pa = pyaudio.PyAudio()
                try:
                    info = pa.get_device_info_by_index(int(val))
                    return str(info.get("name", "")) if isinstance(info, dict) else None
                finally:
                    pa.terminate()
        except Exception:
            return None

    def _apply_linux_audio_device(self) -> None:
        """On Linux with --aout=pulse, enumerate VLC audio output devices and select
        the one whose description best matches the stored PortAudio device name."""
        if _IS_WIN32 or not self.is_ready():
            return
        device_name = self._get_stored_device_name()
        if not device_name:
            return
        try:
            assert self.player is not None
            devices = self.player.audio_output_device_enum()
            if not devices:
                return
            needle = device_name.lower()
            dev = devices
            while dev:
                try:
                    desc = dev.description
                    dev_id = dev.device
                    if isinstance(desc, bytes):
                        desc = desc.decode(errors="ignore")
                    if isinstance(dev_id, bytes):
                        dev_id = dev_id.decode(errors="ignore")
                    desc_lc = str(desc).lower()
                    if needle in desc_lc or desc_lc in needle:
                        self.player.audio_output_device_set(None, dev_id)
                        self.log.debug("[VLC] audio output device set to: %s (%s)", dev_id, desc)
                        return
                except Exception:
                    pass
                try:
                    dev = dev.next
                except Exception:
                    break
        except Exception as e:
            self.log.debug("[VLC] _apply_linux_audio_device error: %s", e)

    def is_ready(self) -> bool:
        return bool(self._ready and self.instance is not None and self.player is not None)

    def reinitialize(self, libvlc_path: str | None, network_caching_ms: int | None = None) -> bool:
        self._vlc_path = libvlc_path
        if network_caching_ms is not None:
            try:
                self._network_caching_ms = int(network_caching_ms)
            except Exception:
                pass
        self._init_vlc()
        return self.is_ready()

    def get_init_error(self) -> str | None:
        return self._init_error

    def _emit(self, code: str, value: int | None = None) -> None:
        if self._on_event:
            try:
                self._on_event(code, value)
            except Exception:
                pass

    def play_url(self, url: str) -> bool:
        self.log.debug("[DEBUG] play_url: url=%s", url)
        if not self.is_ready():
            self.log.error(
                "[BACKEND] PlayerVLC: play_url called but backend is not ready (%s)",
                self._init_error or "not initialized",
            )
            self._emit("libvlc_init_failed", None)
            return False
        try:
            assert self.instance is not None and self.player is not None
            # Only stop if the player is actually active.  Calling stop() on a
            # freshly-initialised (never-played) player raises in some VLC
            # builds and is not needed when no stream is open.
            try:
                st = self.player.get_state()
                self.log.debug("[DEBUG] play_url: current state=%s", st)
                active = vlc is not None and st in (
                    vlc.State.Playing,
                    vlc.State.Buffering,
                    vlc.State.Opening,
                    vlc.State.Paused,
                )
            except Exception as e:
                self.log.debug("[DEBUG] play_url: get_state failed: %s", e)
                active = False
            if active:
                self.log.debug("[DEBUG] play_url: stopping previous stream")
                self._stopping = True
                try:
                    self.player.stop()
                except Exception as e:
                    self.log.debug("[DEBUG] play_url: stop() failed: %s", e)
            self.log.debug("[DEBUG] play_url: creating media")
            media = self.instance.media_new(url)
            if media is None:
                self.log.error("[BACKEND] PlayerVLC: media_new(%s) returned None", url)
                self._stopping = False
                self._emit("error", None)
                return False
            try:
                if getattr(self, "_user_agent", None):
                    media.add_option(f":http-user-agent={self._user_agent}")
            except Exception as e:
                self.log.debug("[DEBUG] play_url: add_option failed: %s", e)
            self.log.debug("[DEBUG] play_url: set_media + play")
            self.player.set_media(media)
            self._apply_linux_audio_device()
            self._stopping = False
            ret = self.player.play()
            self.log.debug("[DEBUG] play_url: play() returned %s", ret)
            if ret != 0:
                self.log.error("[BACKEND] PlayerVLC: play() returned error code %s", ret)
                self._emit("error", None)
                return False
            return True
        except Exception as e:
            self.log.error("[BACKEND] PlayerVLC: play_url exception: %s", e)
            self._stopping = False
            self._emit("error", None)
            return False

    def stop(self) -> None:
        self.log.debug("[DEBUG] stop: called")
        if not self.is_ready():
            self._emit("libvlc_init_failed", None)
            return
        try:
            assert self.player is not None
            self._stopping = True
            self.player.stop()
            self._stopping = False
            self._emit("stopped", None)
            self.log.debug("[DEBUG] stop: done")
        except Exception as e:
            self.log.debug("[DEBUG] stop: exception: %s", e)
            self._stopping = False
            self._emit("error", None)

    def pause_toggle(self) -> None:
        if not self.is_ready():
            self._emit("libvlc_init_failed", None)
            return
        try:
            assert self.player is not None
            self.player.pause()
        except Exception:
            self._emit("error", None)

    @staticmethod
    def _to_backend_volume(vol: int) -> int:
        """Map user slider percentage (0..100) to libvlc integer volume.

        VLC's audio output (e.g. WASAPI on Windows) internally applies a cubic
        tapering curve (vol = vol^3). A raw linear percentage makes volume < 20%
        almost inaudible (-42 dB). Applying the sqrt mapping ensures an effective
        power curve (gain = (vol/100)^1.5), providing a smooth, fully audible range.
        """
        if vol <= 0:
            return 0
        if vol >= 100:
            return 100
        return int(round(100.0 * math.sqrt(vol / 100.0)))

    def set_volume(self, vol: int) -> None:
        self._volume = max(0, min(100, int(vol)))
        if not self.is_ready():
            return
        try:
            assert self.player is not None
            self.player.audio_set_volume(self._to_backend_volume(self._volume))
        except Exception:
            self._emit("error", None)

    def set_mute(self, mute: bool) -> None:
        self._muted = bool(mute)
        if not self.is_ready():
            return
        try:
            assert self.player is not None
            self.player.audio_set_mute(self._muted)
        except Exception:
            self._emit("error", None)

    def get_volume(self) -> int:
        return self._volume

    def get_mute(self) -> bool:
        return self._muted

    def is_playing(self) -> bool:
        if not self.is_ready():
            return False
        try:
            if vlc is None or self.player is None:
                return False
            st = self.player.get_state()
            return st in (vlc.State.Playing, vlc.State.Buffering, vlc.State.Opening)
        except Exception:
            return False

    # VLC event handler
    def _handle_event(self, event):
        if vlc is None:
            return
        et = event.type
        self.log.debug("[DEBUG] _handle_event: type=%s stopping=%s", et, self._stopping)
        if et == vlc.EventType.MediaPlayerOpening:
            self._emit("opening", None)
        elif et == vlc.EventType.MediaPlayerBuffering:
            # Try to extract percentage
            pct = None
            try:
                pct = int(getattr(getattr(event, "u", None), "new_cache", 0))
            except Exception:
                pct = None
            self._emit("buffering", pct)
        elif et == vlc.EventType.MediaPlayerPlaying:
            self._emit("playing", None)
        elif et == vlc.EventType.MediaPlayerPaused:
            self._emit("paused", None)
        elif et == vlc.EventType.MediaPlayerStopped:
            # stop() / play_url() already emit 'stopped' manually; suppress
            # the duplicate event from VLC's callback thread.
            if self._stopping:
                return
            self._emit("stopped", None)
        elif et == vlc.EventType.MediaPlayerEndReached:
            # Absorb stale EndReached fired while we are tearing down the
            # previous stream (same guard as PlayerMPV._stopping).
            if self._stopping:
                return
            self._emit("ended", None)
        elif et == vlc.EventType.MediaPlayerEncounteredError:
            # Absorb errors fired during intentional stop/restart teardown so
            # that they do not schedule a spurious extra restart in the UI.
            if self._stopping:
                return
            self.log.error(
                "[BACKEND] PlayerVLC: MediaPlayerEncounteredError event received from libVLC"
            )
            self._emit("error", None)

    # -------- Dettagli/diagnostica VLC --------
    def get_version(self) -> str | None:
        """Return libVLC version string if available, otherwise None."""
        if vlc is None:
            return None
        try:
            ver = vlc.libvlc_get_version()  # type: ignore[attr-defined]
            if isinstance(ver, bytes):
                ver = ver.decode(errors="ignore")
            return str(ver)
        except Exception:
            return None

    def get_configured_path(self) -> str | None:
        """Return configured libvlc path (folder) or None if using system/PATH."""
        return self._vlc_path

    def force_cleanup(self) -> None:
        """Force cleanup of current media and connections using in-process release."""
        self._stopping = True
        try:
            current_volume = self._volume
            current_mute = self._muted

            if self.player is not None:
                try:
                    self.player.stop()
                except Exception:
                    pass
                try:
                    self.player.set_media(None)
                except Exception:
                    pass
                try:
                    self.player.release()
                except Exception:
                    pass
                self.player = None

            if self.instance is not None:
                try:
                    self.instance.release()
                except Exception:
                    pass
                self.instance = None

            self._ready = False

            # Reinitialize VLC so backend is ready for subsequent playback
            self._init_vlc()
            if self.is_ready():
                self.set_volume(current_volume)
                self.set_mute(current_mute)
        except Exception:
            pass
        finally:
            self._stopping = False

    def _force_complete_cleanup(self) -> None:
        """Alias for force_cleanup for backward compatibility."""
        self.force_cleanup()
