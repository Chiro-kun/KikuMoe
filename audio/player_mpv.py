from __future__ import annotations

import locale
import os
import sys
from pathlib import Path
from typing import Any, Callable

from core.constants import (
    APP_NAME,
    APP_SETTINGS,
    APP_VERSION,
    KEY_AUDIO_DEVICE_INDEX,
    ORG_NAME,
    _get_project_root,
)
from core.logger import get_logger

_IS_WIN32 = sys.platform == "win32"


def _find_libmpv_path() -> str | None:
    """Cerca la DLL di libmpv nelle posizioni comuni su Windows in modo robusto."""
    if not _IS_WIN32:
        return None

    # Se MPV_PATH punta direttamente a un file esistente, usalo subito
    env_mpv_path = os.environ.get("MPV_PATH")
    if env_mpv_path and os.path.isfile(env_mpv_path):
        return str(Path(env_mpv_path).resolve())

    # Nomi comuni per libmpv su Windows
    names = ["libmpv-2.dll", "mpv-2.dll", "libmpv-1.dll", "mpv-1.dll", "mpv.dll"]

    candidate_dirs: list[Path] = []

    # 1. Directory da variabile d'ambiente MPV_DIR se specificata
    env_mpv_dir = os.environ.get("MPV_DIR")
    if env_mpv_dir:
        candidate_dirs.append(Path(env_mpv_dir))

    # 2. Se congelato (PyInstaller)
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidate_dirs.append(Path(meipass))
        candidate_dirs.append(Path(sys.executable).resolve().parent)
    else:
        # In sviluppo: radice del repository determinata dal file corrente
        script_dir = Path(__file__).resolve().parent  # <repo>/audio
        repo_root = script_dir.parent                 # <repo>
        candidate_dirs.append(repo_root)
        candidate_dirs.append(script_dir)
        candidate_dirs.append(repo_root / "packaging" / "windows")

        try:
            proj_root = Path(_get_project_root()).resolve()
            candidate_dirs.append(proj_root)
            candidate_dirs.append(proj_root / "packaging" / "windows")
        except Exception:
            pass

    # 3. Rimuovi duplicati preservando l'ordine (NO fallback su CWD per prevenire DLL hijacking)
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

    # 5. Cerca le DLL nelle directory individuate
    for d in unique_dirs:
        for name in names:
            dll_path = d / name
            try:
                if dll_path.is_file():
                    return str(dll_path.resolve())
            except Exception:
                pass

    return None


# Configura il path DLL PRIMA di importare mpv
_found_libmpv = _find_libmpv_path()
if _found_libmpv:
    _dll_dir = str(Path(_found_libmpv).parent)
    if _IS_WIN32:
        # Forza python-mpv a usare questa specifica DLL
        # (utile per nomi non standard come libmpv-2.dll)
        os.environ["MPV_PATH"] = _found_libmpv
        # Aggiungi al PATH per sicurezza
        os.environ["PATH"] = _dll_dir + os.pathsep + os.environ.get("PATH", "")
        # Per Python 3.8+ su Windows, aggiungi alla directory DLL sicura
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(_dll_dir)
            except Exception:
                pass


_mpv_import_error: Exception | None = None
try:
    import mpv
except Exception as e:
    mpv = None  # type: ignore
    _mpv_import_error = e

# MPV end-file reason integers (MPV_END_FILE_REASON_*)
_MPV_END_STOP = 2
_MPV_END_QUIT = 3
_MPV_END_ERROR = 4


class PlayerMPV:
    def __init__(self, on_event: Callable[[str, int | None], None] | None = None) -> None:
        self._on_event = on_event
        self._muted: bool = False
        self._volume: int = 100
        self._ready: bool = False
        self._init_error: str | None = None
        self._player: Any | None = None
        # Set when stop()/force_cleanup() is called so the end-file callback
        # doesn't mis-classify the resulting event as a natural 'ended'.
        self._stopping: bool = False
        self.log = get_logger("PlayerMPV")
        try:
            self._user_agent = f"{APP_NAME}/{APP_VERSION}"
        except Exception:
            self._user_agent = "KikuMoe/1.10.0"
        self._init_mpv()

    def _get_stored_device_name(self) -> str | None:
        """Return the human-readable name of the user-configured PortAudio output device,
        or None when the setting is absent or unresolvable."""
        try:
            from PyQt6.QtCore import QSettings

            settings = QSettings(ORG_NAME, APP_SETTINGS)
            val = settings.value(KEY_AUDIO_DEVICE_INDEX, "")
            if val in (None, ""):
                return None
            import pyaudio

            pa = pyaudio.PyAudio()
            try:
                info = pa.get_device_info_by_index(int(val))
                return str(info.get("name", "")) if isinstance(info, dict) else None
            finally:
                pa.terminate()
        except Exception:
            return None

    def _apply_linux_audio_device(self) -> None:
        """On Linux, match the stored PortAudio device name against MPV's
        audio-device-list and set audio_device when a match is found."""
        if _IS_WIN32 or not self.is_ready():
            return
        device_name = self._get_stored_device_name()
        if not device_name:
            return
        try:
            assert self._player is not None
            device_list = getattr(self._player, "audio_device_list", None)
            if not device_list:
                return
            needle = device_name.lower()
            for dev in device_list:
                try:
                    desc = str(dev.get("description", "")).lower()
                    name = str(dev.get("name", "")).lower()
                except Exception:
                    try:
                        desc = str(getattr(dev, "description", "")).lower()
                        name = str(getattr(dev, "name", "")).lower()
                    except Exception:
                        continue
                if needle in desc or needle in name or desc in needle:
                    try:
                        self._player.audio_device = dev.get("name") or getattr(dev, "name", None)
                        self.log.debug("[MPV] audio_device set to: %s", self._player.audio_device)
                    except Exception as e:
                        self.log.debug("[MPV] Could not set audio_device: %s", e)
                    return
        except Exception as e:
            self.log.debug("[MPV] _apply_linux_audio_device error: %s", e)

    def _init_mpv(self) -> None:
        self._ready = False
        if mpv is None:
            self._init_error = str(_mpv_import_error or "unknown import error")
            self.log.error(
                "[BACKEND] PlayerMPV: python-mpv import unavailable: %s",
                self._init_error,
            )
            return
        try:
            # libmpv requires LC_NUMERIC="C"; set it before creating the instance
            # to avoid the "Non-C locale detected" warning and segfault.
            locale.setlocale(locale.LC_NUMERIC, "C")
        except Exception:
            pass
        # On Linux, prefer PipeWire → PulseAudio → ALSA in that order.
        # MPV processes the comma-separated list and uses the first driver that works.
        linux_ao: str | None = None
        if not _IS_WIN32:
            try:
                uid = os.getuid()  # type: ignore[attr-defined]
                pw_sock = os.environ.get("PIPEWIRE_RUNTIME_DIR", f"/run/user/{uid}")
                if os.path.exists(os.path.join(pw_sock, "pipewire-0")):
                    linux_ao = "pipewire,pulse,alsa"
                else:
                    linux_ao = "pulse,alsa"
            except Exception:
                linux_ao = "pulse,alsa"
        try:
            lib_path = _found_libmpv
            if lib_path:
                self.log.info("[BACKEND] PlayerMPV: using libmpv at %s", lib_path)

            kwargs: dict = dict(
                vid="no",
                terminal=False,
                quiet=True,
                user_agent=self._user_agent,
            )
            if linux_ao:
                kwargs["ao"] = linux_ao
            self._player = mpv.MPV(**kwargs)
            self._player.volume = float(self._volume)
            self._player.mute = self._muted

            @self._player.event_callback("start-file")
            def _on_start(event):
                self._stopping = False
                self._emit("opening", None)

            @self._player.event_callback("file-loaded")
            def _on_loaded(event):
                self._emit("playing", None)

            @self._player.event_callback("end-file")
            def _on_end(event):
                # If stop()/force_cleanup() set the flag, absorb this event —
                # 'stopped' was already emitted by the calling method.
                if self._stopping:
                    self._stopping = False
                    return

                # Determine reason: event.reason is an int in libmpv
                # (MPV_END_FILE_REASON_STOP=2, QUIT=3, ERROR=4, EOF=0/1).
                # Guard against string/enum forms in future python-mpv versions.
                reason = getattr(event, "reason", None)
                try:
                    reason_int = int(reason)
                except Exception:
                    reason_int = -1
                reason_str = str(reason).lower()

                if (
                    reason_int in (_MPV_END_STOP, _MPV_END_QUIT)
                    or "stop" in reason_str
                    or "quit" in reason_str
                ):
                    self._emit("stopped", None)
                elif reason_int == _MPV_END_ERROR or "error" in reason_str:
                    self._emit("error", None)
                else:
                    self._emit("ended", None)

            @self._player.property_observer("cache-buffering-state")
            def _on_cache(name, value):
                if value is not None:
                    try:
                        self._emit("buffering", int(value))
                    except Exception:
                        pass

            self._ready = True
            try:
                self.log.info(
                    "[BACKEND] PlayerMPV: backend initialized (version: %s)", self.get_version()
                )
            except Exception:
                pass
        except Exception as e:
            self._init_error = str(e)
            self.log.error("[BACKEND] PlayerMPV: init failed: %s", e)
            # If we specified an ao and it caused the failure, retry without it
            if linux_ao and "ao" in kwargs:
                try:
                    self.log.debug("[DEBUG] PlayerMPV: retrying without ao preference")
                    kwargs.pop("ao")
                    self._player = mpv.MPV(**kwargs)
                    self._player.volume = float(self._volume)
                    self._player.mute = self._muted
                    self._ready = True
                except Exception as e2:
                    self._init_error = str(e2)
                    self.log.debug("[DEBUG] PlayerMPV: retry also failed: %s", e2)
                    self._player = None
                    self._ready = False
            else:
                self._player = None
                self._ready = False

    def is_ready(self) -> bool:
        return bool(self._ready and self._player is not None)

    def get_init_error(self) -> str | None:
        return self._init_error

    def reinitialize(
        self, libvlc_path: str | None = None, network_caching_ms: int | None = None
    ) -> bool:
        return self.is_ready()

    def _emit(self, code: str, value: int | None = None) -> None:
        if self._on_event:
            try:
                self._on_event(code, value)
            except Exception:
                pass

    def play_url(self, url: str) -> bool:
        if not self.is_ready():
            self._emit("error", None)
            return False
        try:
            assert self._player is not None
            self._stopping = False
            self._apply_linux_audio_device()
            self._player.pause = False
            self._player.play(url)
            return True
        except Exception as e:
            self.log.error("[BACKEND] PlayerMPV: play_url failed: %s", e)
            self._emit("error", None)
            return False

    def stop(self) -> None:
        if not self.is_ready():
            return
        assert self._player is not None
        # Only set the flag when there's actually something playing/paused;
        # if MPV is already idle no end-file event will fire and the flag
        # would linger, suppressing the next natural 'ended'.
        try:
            idle = bool(getattr(self._player, "idle_active", True))
            self._stopping = not idle
        except Exception:
            self._stopping = False
        try:
            self._player.stop()
        except Exception:
            self._stopping = False
        self._emit("stopped", None)

    def pause_toggle(self) -> None:
        if not self.is_ready():
            return
        try:
            assert self._player is not None
            self._player.pause = not bool(self._player.pause)
            if self._player.pause:
                self._emit("paused", None)
            else:
                self._emit("playing", None)
        except Exception:
            self._emit("error", None)

    def set_volume(self, vol: int) -> None:
        self._volume = max(0, min(100, int(vol)))
        if not self.is_ready():
            return
        try:
            assert self._player is not None
            self._player.volume = float(self._volume)
        except Exception:
            pass

    def set_mute(self, mute: bool) -> None:
        self._muted = bool(mute)
        if not self.is_ready():
            return
        try:
            assert self._player is not None
            self._player.mute = self._muted
        except Exception:
            pass

    def get_volume(self) -> int:
        return self._volume

    def get_mute(self) -> bool:
        return self._muted

    def is_playing(self) -> bool:
        if not self.is_ready():
            return False
        try:
            assert self._player is not None
            idle = bool(getattr(self._player, "idle_active", True))
            paused = bool(getattr(self._player, "pause", True))
            return not idle and not paused
        except Exception:
            return False

    def is_paused(self) -> bool:
        if not self.is_ready():
            return False
        try:
            assert self._player is not None
            idle = bool(getattr(self._player, "idle_active", True))
            paused = bool(getattr(self._player, "pause", False))
            return not idle and paused
        except Exception:
            return False

    def get_version(self) -> str | None:
        if mpv is None or not self.is_ready():
            return None
        try:
            assert self._player is not None
            ver = self._player.mpv_version
            return str(ver) if ver else None
        except Exception:
            return None

    def get_configured_path(self) -> str | None:
        return None

    def force_cleanup(self) -> None:
        if not self.is_ready():
            return
        assert self._player is not None
        try:
            idle = bool(getattr(self._player, "idle_active", True))
            self._stopping = not idle
        except Exception:
            self._stopping = False
        try:
            self._player.stop()
        except Exception:
            self._stopping = False
