from __future__ import annotations

import locale
import math
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
from core.logger import PORTAUDIO_LOCK, get_logger, silence_stderr

_IS_WIN32 = sys.platform == "win32"


def _find_libmpv_path() -> str | None:
    """Cerca la libreria dinamica libmpv (DLL su Windows, .so su Linux, .dylib su macOS)
    in modo robusto e ne restituisce il percorso assoluto."""
    # 1. Se MPV_PATH punta direttamente a un file esistente, usalo subito
    env_mpv_path = os.environ.get("MPV_PATH")
    if env_mpv_path and os.path.isfile(env_mpv_path):
        return str(Path(env_mpv_path).resolve())

    candidate_dirs: list[Path] = []

    # 2. Directory da variabile d'ambiente MPV_DIR se specificata
    env_mpv_dir = os.environ.get("MPV_DIR")
    if env_mpv_dir:
        candidate_dirs.append(Path(env_mpv_dir))

    # 3. Directory dell'applicazione (PyInstaller frozen o ambiente di sviluppo)
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
        # In sviluppo: radice del repository determinata dal file corrente
        script_dir = Path(__file__).resolve().parent  # <repo>/audio
        repo_root = script_dir.parent  # <repo>
        candidate_dirs.append(repo_root)
        candidate_dirs.append(script_dir)
        if _IS_WIN32:
            candidate_dirs.append(repo_root / "packaging" / "windows")

        try:
            proj_root = Path(_get_project_root()).resolve()
            candidate_dirs.append(proj_root)
            if _IS_WIN32:
                candidate_dirs.append(proj_root / "packaging" / "windows")
        except Exception:
            pass

    # 4. Nomi delle librerie in base alla piattaforma
    if _IS_WIN32:
        names = ["libmpv-2.dll", "mpv-2.dll", "libmpv-1.dll", "mpv-1.dll", "mpv.dll"]
    elif sys.platform == "darwin":
        names = ["libmpv.2.dylib", "libmpv.1.dylib", "libmpv.dylib"]
        candidate_dirs.extend(
            [
                Path("/opt/homebrew/lib"),
                Path("/usr/local/lib"),
                Path("/opt/local/lib"),
            ]
        )
    else:
        # Linux / BSD / Unix (in ordine di preferenza ABI)
        names = ["libmpv.so.2", "libmpv.so.1", "libmpv.so"]
        candidate_dirs.extend(
            [
                Path("/usr/lib/x86_64-linux-gnu"),
                Path("/usr/lib/aarch64-linux-gnu"),
                Path("/usr/lib/arm-linux-gnueabihf"),
                Path("/usr/lib64"),
                Path("/usr/lib"),
                Path("/usr/local/lib"),
                Path("/lib/x86_64-linux-gnu"),
                Path("/lib64"),
                Path("/lib"),
                Path("/app/lib"),  # Flatpak
                Path(os.path.expanduser("~/.local/lib")),
            ]
        )

    # 5. Rimuovi duplicati preservando l'ordine
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

    # 6. Cerca le librerie nelle directory individuate rispettando l'ordine dei nomi
    for name in names:
        for d in unique_dirs:
            candidate = d / name
            try:
                if candidate.is_file():
                    return str(candidate.resolve())
            except Exception:
                pass

    # 7. Su Linux, se non ancora trovata nelle directory note, interroga ldconfig -p
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

    # 8. Prova come ultima risorsa ctypes.util.find_library
    try:
        import ctypes.util

        lib_name = ctypes.util.find_library("mpv")
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


# Configura il path DLL/SO PRIMA di importare mpv
_found_libmpv = _find_libmpv_path()
if _found_libmpv:
    _dll_dir = str(Path(_found_libmpv).parent)
    os.environ["MPV_PATH"] = _found_libmpv
    if _IS_WIN32:
        # Aggiungi al PATH per sicurezza
        os.environ["PATH"] = _dll_dir + os.pathsep + os.environ.get("PATH", "")
        # Per Python 3.8+ su Windows, aggiungi alla directory DLL sicura
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(_dll_dir)
            except Exception:
                pass
    else:
        # Su Linux/Unix, esporta la directory in LD_LIBRARY_PATH
        curr_ld = os.environ.get("LD_LIBRARY_PATH", "")
        os.environ["LD_LIBRARY_PATH"] = _dll_dir + (os.pathsep + curr_ld if curr_ld else "")


_mpv_import_error: Exception | None = None

# Su piattaforme non-Windows, python-mpv chiama internamente ctypes.util.find_library('mpv').
# In un binario PyInstaller frozen, PyInstaller intercetta CDLL() e solleva PyInstallerImportError
# se il nome passato è relativo e non è stato impacchettato in sys._MEIPASS.
# Monkey-patchando ctypes.util.find_library per restituire il percorso assoluto della libreria
# consentiamo a CDLL() di effettuare la dlopen() direttamente dal percorso di sistema.
_orig_find_library = None
if _found_libmpv and not _IS_WIN32:
    try:
        import ctypes.util

        _orig_find_library = ctypes.util.find_library

        def _custom_find_library(name: str) -> str | None:
            if name == "mpv":
                return _found_libmpv
            return _orig_find_library(name) if _orig_find_library else None

        ctypes.util.find_library = _custom_find_library
    except Exception:
        pass

# Se libmpv non è presente nel sistema Linux/Unix, evitiamo l'import fallimentare
# di python-mpv con errore fuorviante di PyInstaller e forniamo un messaggio chiaro.
mpv: Any = None
if not _IS_WIN32 and not _found_libmpv:
    _mpv_import_error = OSError(
        "libmpv was not found on this system. Please install libmpv "
        "(e.g. 'sudo apt install libmpv-dev libmpv1' on Debian/Ubuntu, "
        "'sudo pacman -S mpv' on Arch, or 'sudo dnf install mpv-libs' on Fedora)."
    )
else:
    try:
        import mpv as _mpv_mod

        mpv = _mpv_mod
    except Exception as e:
        mpv = None
        _mpv_import_error = e
    finally:
        if _orig_find_library is not None:
            try:
                import ctypes.util

                ctypes.util.find_library = _orig_find_library
            except Exception:
                pass

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
            self._user_agent = "KikuMoe/1.11.0"
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
            cause = getattr(_mpv_import_error, "__cause__", None)
            cause_msg = f" (cause: {cause})" if cause else ""
            self._init_error = f"{_mpv_import_error}{cause_msg}"
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
                uid = getattr(os, "getuid", lambda: 1000)()
                pw_sock = os.environ.get("PIPEWIRE_RUNTIME_DIR", f"/run/user/{uid}")
                if os.path.exists(os.path.join(pw_sock, "pipewire-0")):
                    linux_ao = "pipewire,pulse,alsa"
                else:
                    linux_ao = "pulse,alsa"
            except Exception:
                linux_ao = "pulse,alsa"
        kwargs: dict = {}
        try:
            lib_path = _found_libmpv
            if lib_path:
                self.log.info("[BACKEND] PlayerMPV: using libmpv at %s", lib_path)

            def _mpv_log_handler(loglevel: str, component: str, message: str) -> None:
                lvl = (loglevel or "").lower()
                clean = f"[{component}] {message.strip()}"
                if lvl in ("fatal", "error"):
                    self.log.error("[MPV] %s", clean)
                elif lvl == "warn":
                    self.log.warning("[MPV] %s", clean)
                else:
                    self.log.debug("[MPV] %s", clean)

            kwargs = dict(
                vid="no",
                terminal=False,
                log_handler=_mpv_log_handler,
                loglevel="warn",
                user_agent=self._user_agent,
            )
            if linux_ao:
                kwargs["ao"] = linux_ao
            player = mpv.MPV(**kwargs)
            self._player = player
            player.volume = self._to_backend_volume(self._volume)
            player.mute = self._muted

            @player.event_callback("start-file")
            def _on_start(event):
                self._stopping = False
                self._emit("opening", None)

            @player.event_callback("file-loaded")
            def _on_loaded(event):
                self._emit("playing", None)

            @player.event_callback("end-file")
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
                    reason_int = int(reason) if reason is not None else -1
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
                    self.log.error(
                        "[BACKEND] PlayerMPV: playback ended with error (reason=%s)", reason
                    )
                    self._emit("error", None)
                else:
                    self._emit("ended", None)

            @player.property_observer("cache-buffering-state")
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
                    player = mpv.MPV(**kwargs)
                    self._player = player
                    player.volume = self._to_backend_volume(self._volume)
                    player.mute = self._muted
                    self._ready = True
                except Exception as e2:
                    self._init_error = str(e2)
                    self.log.error(
                        "[BACKEND] PlayerMPV: retry without ao preference also failed: %s", e2
                    )
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

    @staticmethod
    def _to_backend_volume(vol: int) -> float:
        """Map user slider percentage (0..100) to mpv internal software volume.

        MPV's internal softvol operates on a cubic scale (gain = (vol/100)^3).
        A raw linear pass-through makes volume < 20% virtually imperceptible (-42 dB).
        Mapping with 100 * (vol/100)^0.5 ensures an effective perceptual response curve
        (gain = (vol/100)^1.5), providing clear, natural, and fully audible dynamics
        across the entire 0-100% range without sudden drop-offs.
        """
        if vol <= 0:
            return 0.0
        if vol >= 100:
            return 100.0
        return float(100.0 * math.sqrt(vol / 100.0))

    def set_volume(self, vol: int) -> None:
        self._volume = max(0, min(100, int(vol)))
        if not self.is_ready():
            return
        try:
            assert self._player is not None
            self._player.volume = self._to_backend_volume(self._volume)
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

    def set_audio_tap(self, callback: Any | None) -> None:
        """Interfaccia opzionale tap audio (non implementata per MPV)."""
        self._audio_tap = callback

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
