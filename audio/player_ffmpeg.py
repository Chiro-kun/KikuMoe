from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from PyQt6.QtCore import QSettings

from audio.equalizer import BiquadEqualizerProcessor
from core.constants import APP_NAME, APP_SETTINGS, APP_VERSION, KEY_AUDIO_DEVICE_INDEX, ORG_NAME
from core.logger import PORTAUDIO_LOCK, get_logger, silence_stderr

_IS_WIN32 = sys.platform == "win32"

_pyaudio_import_error: BaseException | None = None
try:
    import pyaudio
except Exception as e:
    pyaudio = None  # type: ignore
    _pyaudio_import_error = e


def _find_ffmpeg_bin() -> str:
    """Restituisce il percorso dell'eseguibile ffmpeg, cercando prima in FFMPEG_PATH,
    poi nella cartella dell'eseguibile (utile per distribuzioni portatili su Windows)
    e infine nel PATH di sistema."""
    env_bin = os.environ.get("FFMPEG_PATH")
    if env_bin and os.path.isfile(env_bin):
        if not (_IS_WIN32 and env_bin.lower().endswith((".bat", ".cmd"))):
            return env_bin

    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / ("ffmpeg.exe" if _IS_WIN32 else "ffmpeg"))
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / ("ffmpeg.exe" if _IS_WIN32 else "ffmpeg"))
    else:
        try:
            repo_root = Path(__file__).resolve().parent.parent
            candidates.append(repo_root / ("ffmpeg.exe" if _IS_WIN32 else "ffmpeg"))
            if _IS_WIN32:
                candidates.append(repo_root / "packaging" / "windows" / "ffmpeg.exe")
        except Exception:
            pass

    for c in candidates:
        try:
            if c.is_file() and not (_IS_WIN32 and c.name.lower().endswith((".bat", ".cmd"))):
                return str(c.resolve())
        except Exception:
            pass

    if _IS_WIN32:
        which_bin = shutil.which("ffmpeg.exe")
        if which_bin and not which_bin.lower().endswith((".bat", ".cmd")):
            return which_bin
        return "ffmpeg.exe"

    which_bin = shutil.which("ffmpeg")
    if which_bin:
        return which_bin

    return "ffmpeg"


class PlayerFFmpeg:
    def __init__(self, on_event: Callable[[str, int | None], None] | None = None) -> None:
        self._on_event = on_event
        self._muted: bool = False
        self._user_volume: int = 100
        self._volume: float = 1.0
        self._ready: bool = False
        self._playing: bool = False
        self._current_stream: str | None = None
        # stop event replaces boolean flag to safely notify worker thread
        self._stop_requested = False
        self._stop_event = threading.Event()
        self._worker_stop_event: threading.Event | None = None
        # lock protecting _ffmpeg_process and _audio_stream
        self._state_lock = threading.RLock()
        self._lifecycle_lock = threading.RLock()
        self._stream_lock = threading.RLock()
        self._session_seq: int = 0
        self._stream_thread: threading.Thread | None = None
        self._audio_stream: Any | None = None
        self._pyaudio_instance: Any | None = None  # type: ignore
        self._ffmpeg_process: subprocess.Popen | None = None
        # Track pause state explicitly
        self._paused: bool = False
        self._init_error: str | None = None
        self._audio_tap: Callable[[bytes], None] | None = None
        self._current_seek_offset: float = 0.0
        self._bytes_streamed: int = 0
        self._stream_sample_rate: int = 48000
        self._is_local_file: bool = False
        self._ffmpeg_verified: bool = False
        self._seek_seq: int = 0
        self._seek_pending: bool = False
        self._eq_processor = BiquadEqualizerProcessor()
        self.log = get_logger("PlayerFFmpeg")
        self._ffmpeg_bin = _find_ffmpeg_bin()
        # Build dynamic User-Agent from constants (e.g., "KikuMoe/1.11.0")
        try:
            self._user_agent = f"{APP_NAME}/{APP_VERSION}"
        except Exception:
            self._user_agent = "KikuMoe/1.11.0"
        self._init_audio()

    # PortAudio host API type constants (from portaudio.h)
    _PA_ALSA = 8
    _PA_PULSE_AUDIO = 18  # also covers PipeWire-pulse

    def _init_audio(self) -> None:
        self._ready = False
        self._init_error = None
        if pyaudio is None:
            err_details = f": {_pyaudio_import_error}" if _pyaudio_import_error else ""
            self._init_error = f"pyaudio module not installed or unavailable{err_details}"
            self.log.warning("[BACKEND] PlayerFFmpeg: %s", self._init_error)
            return
        if not self._check_ffmpeg():
            self._init_error = (
                f"ffmpeg executable not found in PATH or app directory ('{self._ffmpeg_bin}')"
            )
            self.log.warning("[BACKEND] PlayerFFmpeg: %s", self._init_error)
            return
        try:
            with PORTAUDIO_LOCK, silence_stderr():
                self._pyaudio_instance = pyaudio.PyAudio()
            self._ready = True
            if not _IS_WIN32:
                self._linux_preferred_device = self._detect_linux_output_device()
            else:
                self._linux_preferred_device = None
        except Exception as e:
            self._init_error = f"PyAudio initialization error: {e}"
            self.log.error("[BACKEND] PlayerFFmpeg: %s", self._init_error)
            self._ready = False

    def _detect_linux_output_device(self) -> int | None:
        """On Linux, pick the best default output device from the highest-priority
        host API available: PulseAudio/PipeWire (type 18) > ALSA (type 8).
        Returns a PortAudio device index, or None to fall back to PortAudio's own default.
        """
        if pyaudio is None or self._pyaudio_instance is None:
            return None
        pa = self._pyaudio_instance
        with PORTAUDIO_LOCK:
            for api_type in (self._PA_PULSE_AUDIO, self._PA_ALSA):
                try:
                    api_info = pa.get_host_api_info_by_type(api_type)
                except Exception:
                    continue
                device_count = api_info.get("deviceCount", 0) if isinstance(api_info, dict) else 0
                if not device_count:
                    continue
                # Use the default output device reported by this host API
                default_out = (
                    api_info.get("defaultOutputDevice", -1) if isinstance(api_info, dict) else -1
                )
                if default_out is not None and default_out >= 0:
                    try:
                        dev_info = pa.get_device_info_by_index(default_out)
                        if (
                            isinstance(dev_info, dict)
                            and int(dev_info.get("maxOutputChannels", 0)) > 0
                        ):
                            label = "PipeWire/Pulse" if api_type == self._PA_PULSE_AUDIO else "ALSA"
                            self.log.debug(
                                "[FFmpeg] Linux audio: using %s device index=%d (%s)",
                                label,
                                default_out,
                                dev_info.get("name", ""),
                            )
                            return default_out
                    except Exception:
                        pass
                # No explicit default; take the first output-capable device on this API
                api_idx = api_info.get("index", -1) if isinstance(api_info, dict) else -1
                for i in range(pa.get_device_count()):
                    try:
                        d = pa.get_device_info_by_index(i)
                        if (
                            isinstance(d, dict)
                            and d.get("hostApi") == api_idx
                            and int(d.get("maxOutputChannels", 0)) > 0
                        ):
                            label = "PipeWire/Pulse" if api_type == self._PA_PULSE_AUDIO else "ALSA"
                            self.log.debug(
                                "[FFmpeg] Linux audio: using first %s device index=%d (%s)",
                                label,
                                i,
                                d.get("name", ""),
                            )
                            return i
                    except Exception:
                        pass
        self.log.debug("[FFmpeg] Linux audio: no preferred host API found, using PortAudio default")
        return None

    def is_ready(self) -> bool:
        return bool(self._ready and pyaudio is not None)

    def reinitialize(
        self, libvlc_path: str | None = None, network_caching_ms: int | None = None
    ) -> bool:
        self._ffmpeg_verified = False
        self._init_audio()
        return self.is_ready()

    def get_init_error(self) -> str | None:
        return self._init_error

    def _emit(self, code: str, value: int | None = None) -> None:
        if self._on_event:
            try:
                self._on_event(code, value)
            except Exception:
                pass

    def _emit_if_session(self, session_id: int | None, code: str, value: int | None = None) -> None:
        if session_id is not None and session_id != self._session_seq:
            return
        self._emit(code, value)

    def _close_audio_stream(
        self, target_stream: Any | None = None, clear_attr: bool = True
    ) -> None:
        """Stop and close a PyAudio stream cleanly under PORTAUDIO_LOCK and _stream_lock."""
        with PORTAUDIO_LOCK, self._stream_lock:
            stream = target_stream if target_stream is not None else self._audio_stream
            if clear_attr and (target_stream is None or self._audio_stream is stream):
                self._audio_stream = None
            if stream is None or getattr(stream, "_kikumoe_closed", False):
                return
            # Guard against calling Pa_CloseStream twice on the same C PaStream* pointer.
            try:
                setattr(stream, "_kikumoe_closed", True)
            except Exception:
                pass
            try:
                if getattr(stream, "is_active", lambda: False)():
                    try:
                        stream.stop_stream()
                    except Exception:
                        pass
                try:
                    stream.close()
                except Exception:
                    pass
            except Exception:
                pass

    def _terminate_ffmpeg_proc(self, proc: Any, kill_immediately: bool = False) -> None:
        """Terminate or kill an ffmpeg subprocess and close its stdout pipe to unblock readers."""
        if proc is None:
            return
        try:
            if getattr(proc, "poll", lambda: 0)() is None:
                if kill_immediately:
                    proc.kill()
                else:
                    proc.terminate()
                try:
                    proc.wait(timeout=0.35)
                except subprocess.TimeoutExpired:
                    try:
                        proc.kill()
                        proc.wait(timeout=0.35)
                    except Exception:
                        pass
                if proc.poll() is None:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            if getattr(proc, "stdout", None) is not None and hasattr(proc.stdout, "close"):
                proc.stdout.close()
        except Exception:
            pass

    def _check_ffmpeg(self) -> bool:
        """Check if ffmpeg is available."""
        if getattr(self, "_ffmpeg_verified", False):
            return True
        try:
            bin_to_check = getattr(self, "_ffmpeg_bin", None) or _find_ffmpeg_bin()
            if _IS_WIN32:
                if bin_to_check.lower().endswith((".bat", ".cmd")):
                    return False
                if not os.path.isabs(bin_to_check) and not shutil.which(bin_to_check):
                    return False
            kwargs: dict = {}
            if _IS_WIN32:
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            result = subprocess.run(
                [bin_to_check, "-version"],
                capture_output=True,
                check=False,
                timeout=5,
                **kwargs,
            )
            ok = result.returncode == 0
            if ok:
                self._ffmpeg_verified = True
            return ok
        except Exception:
            return False

    def _get_output_device_index(self) -> int | None:
        """Returns the PyAudio output device index to use.

        Priority:
          1. Explicit user selection from QSettings.
          2. On Linux: auto-detected PipeWire/Pulse/ALSA device (_linux_preferred_device).
          3. None → PortAudio's own global default.
        """
        try:
            settings = QSettings(ORG_NAME, APP_SETTINGS)
            val = settings.value(KEY_AUDIO_DEVICE_INDEX, "")
            if val not in (None, ""):
                return int(val)
        except Exception:
            pass
        # On Linux, use the pre-detected preferred device if available
        if not _IS_WIN32:
            return getattr(self, "_linux_preferred_device", None)
        return None

    def _sanitize_stream_url(self, raw: str) -> str:
        """Estrae e sanifica un URL di streaming o preserva un percorso file locale esistente."""
        try:
            # Se raw è un file locale esistente, preserva il percorso assoluto
            if raw and os.path.isfile(raw):
                return str(Path(raw).resolve())

            s = raw or ""
            # Rimuovi globalmente caratteri di apici/backtick e spazi superflui
            s = re.sub(r"[`'\"“”‘’]+", "", s)
            s = s.strip()
            # Estrai il primo token http(s) usando solo caratteri consentiti (no backtick)
            m = re.search(r"https?://[A-Za-z0-9\-._~:/?#\\\[\]@!$&()*+,;=%]+", s)
            url = m.group(0) if m else s
            # Trim spazi
            url = url.strip()
            lower = url.lower()
            # Normalizza suffissi accidentali che terminano con un punto
            if lower.endswith("/mp3.") or lower.endswith(".mp3."):
                url = url[:-1]
            # Rimuovi comune punteggiatura finale/spazi
            url = url.rstrip(".,;!?)]}'\"` \t\r\n")
            return url
        except Exception:
            # Fallback: strip basilare di spazi/apici/backtick
            return (raw or "").strip().strip("`'\"“”‘’")

    def _stop_worker_locked(self, *, emit_stopped: bool, join_timeout: float) -> None:
        """Stop the active ffmpeg worker thread and invalidate any in-flight session.

        Caller must hold _lifecycle_lock.
        """
        with self._state_lock:
            had_worker_running = bool(self._stream_thread and self._stream_thread.is_alive())
            self._session_seq += 1
            self._stop_requested = True
            self._seek_pending = False
            self._stop_event.set()
            if self._worker_stop_event is not None:
                self._worker_stop_event.set()
            self._playing = False
            self._paused = False
            proc: Any = self._ffmpeg_process
            self._ffmpeg_process = None
            thread_ref = self._stream_thread

        self._terminate_ffmpeg_proc(proc)

        if thread_ref and thread_ref.is_alive() and thread_ref is not threading.current_thread():
            try:
                self.log.debug("[DEBUG] Waiting for stream thread to terminate...")
                thread_ref.join(timeout=join_timeout)
            except Exception:
                pass
            if thread_ref.is_alive():
                self.log.debug(
                    "[DEBUG] Stream thread did not terminate within %.2fs.", join_timeout
                )

        with self._state_lock:
            if self._stream_thread is thread_ref and (
                thread_ref is None or not thread_ref.is_alive()
            ):
                self._stream_thread = None
            self._current_stream = None

        if emit_stopped and not had_worker_running:
            self._emit("stopped", None)

    def play_url(self, url: str) -> bool:
        if not self.is_ready():
            # Backend (ffmpeg) non pronto: emette errore generico
            self._emit("error", None)
            return False

        try:
            self.log.debug("[DEBUG] play_url: requested for %s", url)
            raw_in = url
            safe_url = self._sanitize_stream_url(raw_in)
            if safe_url != raw_in:
                try:
                    self.log.debug(
                        "[DEBUG] play_url: sanitized url: %r from raw: %r", safe_url, raw_in
                    )
                except Exception:
                    pass

            with self._lifecycle_lock:
                with self._state_lock:
                    if (
                        self._current_stream == safe_url
                        and self._playing
                        and not self._stop_requested
                    ):
                        self.log.debug("[DEBUG] Already playing this stream, skipping.")
                        return True
                    need_stop = bool(
                        self._playing or (self._stream_thread and self._stream_thread.is_alive())
                    )
                    self._paused = False

                if need_stop:
                    self._stop_worker_locked(emit_stopped=False, join_timeout=0.75)
                else:
                    self.log.debug("[DEBUG] play_url: no active stream, skip stop.")

                worker_stop = threading.Event()
                with self._state_lock:
                    self._session_seq += 1
                    session_id = self._session_seq
                    self._current_stream = safe_url
                    self._is_local_file = os.path.isfile(safe_url)
                    self._current_seek_offset = 0.0
                    self._bytes_streamed = 0
                    self._seek_seq += 1
                    self._seek_pending = False
                    self._stop_requested = False
                    self._stop_event.clear()
                    self._worker_stop_event = worker_stop
                    self._playing = True
                    self._eq_processor.reset_state()

                self.log.debug("[DEBUG] play_url: starting stream thread (session=%d)", session_id)
                try:
                    t = threading.Thread(
                        target=self._stream_worker,
                        args=(safe_url, session_id, worker_stop),
                        daemon=True,
                    )
                    with self._state_lock:
                        self._stream_thread = t
                    t.start()
                except Exception:
                    with self._state_lock:
                        if self._session_seq == session_id:
                            self._playing = False
                            self._current_stream = None
                            self._stream_thread = None
                    self._emit("error", None)
                    return False

            return True
        except Exception:
            with self._state_lock:
                self._playing = False
                self._current_stream = None
            self._emit("error", None)
            return False

    def stop(self) -> None:
        self.log.debug("[DEBUG] stop: called")
        if not self.is_ready():
            return
        with self._lifecycle_lock:
            if not self._playing and not (self._stream_thread and self._stream_thread.is_alive()):
                self.log.debug("[DEBUG] stop: already stopped, skipping redundant stop.")
                return
            try:
                self._stop_worker_locked(emit_stopped=True, join_timeout=1.5)
            except Exception as e:
                try:
                    self.log.debug("[DEBUG] stop: exception during stop: %s", e)
                except Exception:
                    pass

    def pause_toggle(self) -> None:
        if not self.is_ready():
            return

        # Keep the live output stream running: stopping PortAudio while its worker
        # is writing can trigger host errors, especially on rapid toggles.
        with self._state_lock:
            if not self._playing or self._stop_event.is_set():
                return
            self._paused = not self._paused
            paused = self._paused
        self.log.debug("[DEBUG] pause_toggle: %s", "paused" if paused else "resumed")
        self._emit("paused" if paused else "playing", None)

    def set_volume(self, vol: int) -> None:
        self._user_volume = max(0, min(100, int(vol)))
        if self._user_volume <= 0:
            self._volume = 0.0
        elif self._user_volume >= 100:
            self._volume = 1.0
        else:
            self._volume = float((self._user_volume / 100.0) ** 1.5)

    def set_mute(self, mute: bool) -> None:
        self._muted = bool(mute)

    def set_audio_tap(self, callback: Callable[[bytes], None] | None) -> None:
        """Registra callback per intercettare i chunk PCM raw per il visualizzatore."""
        self._audio_tap = callback

    def set_equalizer(
        self, enabled: bool, preamp_db: float, bands_db: list[float] | tuple[float, ...]
    ) -> None:
        """Update real-time 10-band biquad EQ parameters without restarting playback."""
        self._eq_processor.configure(
            enabled=enabled,
            preamp_db=preamp_db,
            bands_db=bands_db,
            sample_rate=self._stream_sample_rate,
        )

    def get_volume(self) -> int:
        return self._user_volume

    def get_mute(self) -> bool:
        return self._muted

    def is_playing(self) -> bool:
        return bool(self._playing and not self._stop_requested)

    def is_paused(self) -> bool:
        return bool(
            self._paused
            and self._playing
            and not self._stop_requested
            and not self._stop_event.is_set()
        )

    def seek(self, seconds: float) -> bool:
        """Seek to target timestamp in seconds for local audio playback."""
        if not self.is_ready() or not self._is_local_file:
            return False
        target = max(0.0, float(seconds))
        with self._state_lock:
            cur_stream = self._current_stream
            if not cur_stream or not self._playing or self._stop_event.is_set():
                return False
            self._current_seek_offset = target
            self._bytes_streamed = 0
            self._seek_seq += 1
            self._seek_pending = True
            self._eq_processor.reset_state()
            proc = self._ffmpeg_process
        # Kill only the active decoder subprocess so _stream_worker restarts at
        # the new offset immediately without blocking the UI thread or reopening audio.
        if proc is not None:
            try:
                if proc.poll() is None:
                    proc.kill()
            except Exception:
                pass
        return True

    def get_time(self) -> float | None:
        """Return current playback position in seconds."""
        if not self._playing:
            return 0.0
        with self._state_lock:
            offset = self._current_seek_offset
            streamed = self._bytes_streamed
        bytes_per_sec = self._stream_sample_rate * 2 * 2
        if bytes_per_sec > 0:
            return offset + (streamed / bytes_per_sec)
        return offset

    def get_duration(self) -> float | None:
        """Return track duration if known."""
        return None

    def get_version(self) -> str | None:
        """Return ffmpeg version string if available."""
        try:
            bin_to_run = getattr(self, "_ffmpeg_bin", None) or _find_ffmpeg_bin()
            if _IS_WIN32:
                if bin_to_run.lower().endswith((".bat", ".cmd")):
                    return None
                if not os.path.isabs(bin_to_run) and not shutil.which(bin_to_run):
                    return None
            kwargs: dict = {}
            if _IS_WIN32:
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            result = subprocess.run(
                [bin_to_run, "-version"],
                capture_output=True,
                text=True,
                timeout=5,
                **kwargs,
            )
            if result.returncode == 0:
                return str(result.stdout.split("\n")[0])
        except Exception:
            pass
        return None

    def get_configured_path(self) -> str | None:
        """Return None - ffmpeg doesn't use external paths."""
        return None

    def force_cleanup(self) -> None:
        """Force cleanup of current stream."""
        try:
            with self._lifecycle_lock:
                with self._state_lock:
                    self._session_seq += 1
                    self._stop_requested = True
                    self._stop_event.set()
                    if self._worker_stop_event is not None:
                        self._worker_stop_event.set()
                    self._playing = False
                    self._paused = False
                    proc: Any = self._ffmpeg_process
                    self._ffmpeg_process = None
                    thread_ref = self._stream_thread

                self._terminate_ffmpeg_proc(proc, kill_immediately=True)

                if (
                    thread_ref
                    and thread_ref.is_alive()
                    and thread_ref is not threading.current_thread()
                ):
                    try:
                        self.log.debug(
                            "[DEBUG] Waiting for stream thread to terminate after force_cleanup..."
                        )
                        thread_ref.join(timeout=2.0)
                    except Exception:
                        pass
                    if thread_ref.is_alive():
                        self.log.debug(
                            "[DEBUG] Stream thread did not terminate after force_cleanup."
                        )

                # Close active audio stream cleanly under _stream_lock
                self._close_audio_stream()

                with self._state_lock:
                    if self._stream_thread is thread_ref and (
                        thread_ref is None or not thread_ref.is_alive()
                    ):
                        self._stream_thread = None
                    self._current_stream = None
        except Exception:
            pass

    def _open_pyaudio_stream(self, device_idx: int | None) -> tuple[Any, int]:
        """Tenta di aprire uno stream PyAudio negoziando una frequenza di campionamento
        supportata (48000, 44100 o il default del dispositivo).
        Restituisce una tupla (audio_stream, sample_rate).
        """
        pa = self._pyaudio_instance
        if pa is None:
            raise RuntimeError("PyAudio instance not initialized")

        pa_format = getattr(pyaudio, "paInt16", None)
        # 2048 frames (circa 43-46ms) per eliminare crackle, micro-interruzioni e buffer underrun
        frames_per_buffer = 2048

        def _get_candidate_rates(dev_index: int | None) -> list[int]:
            rates: list[int] = []
            with PORTAUDIO_LOCK:
                if dev_index is not None:
                    try:
                        info = pa.get_device_info_by_index(dev_index)
                        if isinstance(info, dict):
                            def_rate = int(round(float(info.get("defaultSampleRate", 0))))
                            if def_rate > 0:
                                rates.append(def_rate)
                    except Exception:
                        pass
                else:
                    try:
                        info = pa.get_default_output_device_info()
                        if isinstance(info, dict):
                            def_rate = int(round(float(info.get("defaultSampleRate", 0))))
                            if def_rate > 0:
                                rates.append(def_rate)
                    except Exception:
                        pass
            for r in (48000, 44100):
                if r not in rates:
                    rates.append(r)
            return rates

        last_exc: Exception | None = None

        # 1. Tentativo con device_idx (se configurato)
        if device_idx is not None:
            candidate_rates = _get_candidate_rates(device_idx)
            self.log.debug(
                "[DEBUG] _open_pyaudio_stream: trying device_idx=%s with rates: %s",
                device_idx,
                candidate_rates,
            )
            for rate in candidate_rates:
                try:
                    with PORTAUDIO_LOCK:
                        stream = pa.open(
                            format=pa_format,
                            channels=2,
                            rate=rate,
                            output=True,
                            output_device_index=device_idx,
                            frames_per_buffer=frames_per_buffer,
                        )
                    self.log.debug(
                        "[DEBUG] _open_pyaudio_stream: opened device_idx=%s with rate=%d",
                        device_idx,
                        rate,
                    )
                    return stream, rate
                except Exception as e:
                    last_exc = e
                    self.log.debug(
                        "[DEBUG] _open_pyaudio_stream: device_idx=%s failed with rate=%d: %s",
                        device_idx,
                        rate,
                        e,
                    )

            self.log.warning(
                "[BACKEND] PlayerFFmpeg: all rates failed for device %s, fallback to default",
                device_idx,
            )

        # 2. Tentativo con dispositivo predefinito di sistema (output_device_index=None)
        candidate_rates = _get_candidate_rates(None)
        self.log.debug(
            "[DEBUG] _open_pyaudio_stream: trying system default device with rates: %s",
            candidate_rates,
        )
        for rate in candidate_rates:
            try:
                with PORTAUDIO_LOCK:
                    stream = pa.open(
                        format=pa_format,
                        channels=2,
                        rate=rate,
                        output=True,
                        frames_per_buffer=frames_per_buffer,
                    )
                self.log.debug(
                    "[DEBUG] _open_pyaudio_stream: opened system default device with rate=%d", rate
                )
                return stream, rate
            except Exception as e:
                last_exc = e
                self.log.debug(
                    "[DEBUG] _open_pyaudio_stream: default device failed with rate=%d: %s",
                    rate,
                    e,
                )

        if last_exc:
            raise last_exc
        raise RuntimeError("Failed to open PyAudio stream with any candidate sample rate")

    def _write_pause_silence(self, target_stream: Any | None, chunk_size: int) -> None:
        """Keep the PortAudio output active with silence while paused on a local file."""
        t0 = time.monotonic()
        wrote = False
        if target_stream is not None:
            with self._stream_lock:
                stream = self._audio_stream
                if stream is not None and stream is target_stream:
                    try:
                        if getattr(stream, "is_active", lambda: False)():
                            stream.write(b"\x00" * chunk_size, exception_on_underflow=False)
                            wrote = True
                    except Exception:
                        pass
        if not wrote or (time.monotonic() - t0) < 0.01:
            time.sleep(0.04)

    def _write_audio_chunk(self, data: bytes, target_stream: Any | None = None) -> None:
        """Applica il controllo dinamico del volume e scrive il chunk PCM
        nello stream PyAudio con gestione di underflow e pause."""
        with self._stream_lock:
            stream = target_stream if target_stream is not None else self._audio_stream
            if stream is None:
                return
            if target_stream is not None and stream is not self._audio_stream:
                return

            try:
                stream_active = getattr(stream, "is_active", lambda: False)()
            except Exception:
                stream_active = False

            if not stream_active:
                time.sleep(0.02)
                return

            n_bytes = len(data)
            if n_bytes == 0:
                return

            with self._state_lock:
                paused = self._paused
                write_seek_seq = self._seek_seq
                if self._seek_pending:
                    return
            if self._muted or paused:
                try:
                    stream.write(b"\x00" * n_bytes, exception_on_underflow=False)
                except Exception:
                    pass
                return

            vol = self._volume
            tap_cb = self._audio_tap
            tap_data: bytes | None = data if tap_cb is not None else None

            if self._eq_processor.is_active():
                try:
                    chunk_to_write, tap_data = self._eq_processor.process_pcm_s16le_with_volume(
                        data,
                        sample_rate=self._stream_sample_rate,
                        volume=vol,
                        need_pre_fader=(tap_cb is not None),
                    )
                except Exception:
                    chunk_to_write = data
            elif vol >= 0.999:
                # Ottimizzazione: a volume massimo (o quasi), invia direttamente il chunk raw
                chunk_to_write = data
            elif vol <= 0.001:
                chunk_to_write = b"\x00" * n_bytes
            else:
                try:
                    n_samples = n_bytes // 2
                    samples = struct.unpack(f"<{n_samples}h", data)
                    vol_samples = [
                        -32768 if v < -32768 else (32767 if v > 32767 else v)
                        for v in (int(s * vol) for s in samples)
                    ]
                    chunk_to_write = struct.pack(f"<{n_samples}h", *vol_samples)
                except Exception:
                    chunk_to_write = data

            if tap_cb is not None and tap_data is not None:
                try:
                    # Pre-fader audio tap: visualizer receives post-EQ, unattenuated 100% dynamic
                    # range PCM stream regardless of user volume slider setting.
                    tap_cb(tap_data)
                except Exception:
                    pass

            try:
                stream.write(chunk_to_write, exception_on_underflow=False)
                with self._state_lock:
                    if not self._seek_pending and self._seek_seq == write_seek_seq:
                        self._bytes_streamed += len(chunk_to_write)
            except Exception as e:
                self.log.debug("[DEBUG] _write_audio_chunk: error writing chunk: %s", e)

    def _is_seek_interrupted(self, seek_seq_at_start: int) -> bool:
        """Return True if a newer seek has superseded the active decoder pass."""
        with self._state_lock:
            return bool(self._seek_pending or self._seek_seq != seek_seq_at_start)

    def _flush_prebuffer(
        self,
        prebuffer: list[bytes],
        seek_seq_at_start: int,
        has_emitted_playing: bool,
        stop_event: threading.Event | None = None,
        session_id: int | None = None,
        target_stream: Any | None = None,
    ) -> tuple[bool, bool]:
        """Emit initial playing state if needed and drain buffered PCM chunks."""
        local_stop = stop_event or self._stop_event
        if not has_emitted_playing:
            has_emitted_playing = True
            self._emit_if_session(session_id, "paused" if self.is_paused() else "playing", None)
        interrupted = False
        for pre_chunk in prebuffer:
            if local_stop.is_set() or (session_id is not None and session_id != self._session_seq):
                break
            if self._is_seek_interrupted(seek_seq_at_start):
                interrupted = True
                break
            if target_stream is not None:
                self._write_audio_chunk(pre_chunk, target_stream=target_stream)
            else:
                self._write_audio_chunk(pre_chunk)
        prebuffer.clear()
        return interrupted, has_emitted_playing

    def _stream_worker(
        self,
        url: str,
        session_id: int | None = None,
        stop_event: threading.Event | None = None,
    ) -> None:
        local_stop = stop_event or self._stop_event
        local_stream: Any | None = None
        local_proc: Any | None = None

        def _session_aborted() -> bool:
            return local_stop.is_set() or (
                session_id is not None and session_id != self._session_seq
            )

        self.log.debug("[DEBUG] _stream_worker: started for url: %s (session=%s)", url, session_id)
        terminal_event: str | None = None
        try:
            if _session_aborted():
                return
            self._emit_if_session(session_id, "opening", None)

            # Check ffmpeg availability
            self.log.debug("[DEBUG] _stream_worker: checking ffmpeg availability")
            if not self._check_ffmpeg():
                self.log.error("[BACKEND] PlayerFFmpeg: ffmpeg is not available")
                self._emit_if_session(session_id, "error", None)
                return

            if _session_aborted():
                return

            # Open audio stream with robust sample rate negotiation
            self.log.debug("[DEBUG] _stream_worker: opening PyAudio stream")
            if self._pyaudio_instance is not None:
                try:
                    device_idx = self._get_output_device_index()
                    local_stream, stream_rate = self._open_pyaudio_stream(device_idx)
                    if _session_aborted():
                        self._close_audio_stream(local_stream, clear_attr=False)
                        local_stream = None
                        return
                    try:
                        with PORTAUDIO_LOCK, self._stream_lock:
                            if _session_aborted():
                                self._close_audio_stream(local_stream, clear_attr=False)
                                local_stream = None
                                return
                            self._audio_stream = local_stream
                            self._stream_sample_rate = stream_rate
                            if local_stream is not None and hasattr(local_stream, "start_stream"):
                                local_stream.start_stream()
                                self.log.debug(
                                    "[DEBUG] _stream_worker: PyAudio stream started at rate=%d",
                                    stream_rate,
                                )
                    except Exception as se:
                        self.log.debug(
                            "[DEBUG] _stream_worker: could not start PyAudio stream: %s", se
                        )
                except Exception as e:
                    self.log.error("[BACKEND] PlayerFFmpeg: failed to open PyAudio stream: %s", e)
                    self._emit_if_session(session_id, "error", None)
                    return
            else:
                self.log.error("[BACKEND] PlayerFFmpeg: PyAudio instance is not ready")
                self._emit_if_session(session_id, "error", None)
                return

            # Sanitize URL (robusta e coerente con play_url)
            raw_url = url
            safe_url = self._sanitize_stream_url(raw_url)
            self.log.debug(
                "[DEBUG] _stream_worker: sanitized url: %r from raw: %r", safe_url, raw_url
            )

            is_local = os.path.isfile(safe_url)
            if is_local:
                candidates = [safe_url]
            else:
                candidates = [safe_url]
                try:
                    u = safe_url.lower()
                    if "/kpop/" in u:
                        candidates.append("https://listen.moe/kpop/stream")
                        candidates.append("https://listen.moe/kpop/stream.m3u")
                    else:
                        candidates.append("https://listen.moe/stream")
                        candidates.append("https://listen.moe/stream.m3u")
                except Exception:
                    pass

                # Rimuovi eventuali endpoint non-HTTPS per prevenire stream in chiaro
                candidates = [c for c in candidates if c.lower().startswith("https://")] or [
                    safe_url
                ]

            # Tenta in sequenza ogni URL candidato finché non si ricevono dati;
            # per i file locali gestisce anche eventuali restart da seek senza riaprire PyAudio.
            has_emitted_playing = False
            started_streaming = False
            forced_error = False
            while not _session_aborted():
                started_streaming = False
                forced_error = False
                seek_restarted = False
                last_seek_seq = 0
                for attempt_idx, cur_url in enumerate(candidates):
                    if _session_aborted():
                        break
                    with self._state_lock:
                        seek_offset = self._current_seek_offset
                        seek_seq_at_start = self._seek_seq
                        last_seek_seq = seek_seq_at_start
                        self._seek_pending = False
                    try:
                        self.log.debug(
                            "[DEBUG] _stream_worker: attempt %d with url: %s",
                            attempt_idx + 1,
                            cur_url,
                        )
                    except Exception:
                        pass

                    # FFmpeg command to decode stream and output raw audio at full 100% scale
                    is_mp3 = False
                    try:
                        uu = cur_url.lower()
                        is_mp3 = ("/mp3" in uu) or uu.endswith(".mp3")
                    except Exception:
                        is_mp3 = False

                    ffmpeg_bin = getattr(self, "_ffmpeg_bin", None) or _find_ffmpeg_bin()
                    ffmpeg_cmd = [
                        ffmpeg_bin,
                        "-hide_banner",
                        "-nostdin",
                    ]
                    if not is_local:
                        ffmpeg_cmd.extend(
                            [
                                "-probesize",
                                "32768",
                                "-analyzeduration",
                                "0",
                                "-rw_timeout",
                                "15000000",
                                "-user_agent",
                                self._user_agent,
                                "-reconnect",
                                "1",
                                "-reconnect_streamed",
                                "1",
                                "-reconnect_at_eof",
                                "1",
                                "-reconnect_delay_max",
                                "2",
                                "-reconnect_on_network_error",
                                "1",
                            ]
                        )
                    elif seek_offset > 0:
                        ffmpeg_cmd.extend(["-ss", f"{seek_offset:.3f}"])

                    # Apply MP3-specific HTTP headers for network streams only
                    if is_mp3 and not is_local:
                        try:
                            ffmpeg_cmd.extend(
                                [
                                    "-headers",
                                    "Accept: audio/mpeg\r\nIcy-MetaData: 0\r\n",
                                ]
                            )
                            self.log.debug("[DEBUG] _stream_worker: applying MP3-specific headers")
                        except Exception:
                            pass

                    # Input URL
                    ffmpeg_cmd.extend(["-i", cur_url])

                    # Output format: raw PCM s16le to stdout matching negotiated stream_rate
                    ffmpeg_cmd.extend(
                        [
                            "-vn",
                            "-f",
                            "s16le",
                            "-ar",
                            str(stream_rate),
                            "-ac",
                            "2",
                            "-acodec",
                            "pcm_s16le",
                            "-loglevel",
                            "error",
                            "-",
                        ]
                    )

                    # Launch ffmpeg process with OS pipe buffering (64KB)
                    with self._state_lock:
                        if _session_aborted():
                            break
                        self._ffmpeg_process = None
                    try:
                        kwargs: dict = {}
                        if _IS_WIN32:
                            kwargs["creationflags"] = getattr(
                                subprocess, "CREATE_NO_WINDOW", 0x08000000
                            )
                        self.log.debug("[DEBUG] _stream_worker: launching ffmpeg: %r", ffmpeg_cmd)
                        local_proc = subprocess.Popen(
                            ffmpeg_cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            stdin=subprocess.DEVNULL,
                            bufsize=65536,
                            **kwargs,
                        )
                        with self._state_lock:
                            if _session_aborted():
                                self._terminate_ffmpeg_proc(local_proc, kill_immediately=True)
                                local_proc = None
                                break
                            self._ffmpeg_process = local_proc
                        self.log.debug(
                            "[DEBUG] _stream_worker: ffmpeg process started, pid: %s",
                            local_proc.pid,
                        )
                    except Exception as e:
                        self.log.error(
                            "[BACKEND] PlayerFFmpeg: failed to launch ffmpeg process: %s", e
                        )
                        with self._state_lock:
                            if self._ffmpeg_process is local_proc:
                                self._ffmpeg_process = None
                        local_proc = None
                        continue

                    # Loop di lettura dei dati
                    # Chunk size = 8192 bytes (2048 frames stereo 16-bit, circa 43ms a 48kHz)
                    chunk_size = 8192
                    empty_reads = 0
                    stall_timeout = 10.0
                    last_data_ts = time.time()
                    prebuffer: list[bytes] = []
                    # Local seeks use a minimal 2-chunk prebuffer (~85ms) with active PortAudio
                    prebuffer_target_bytes = (
                        (chunk_size * 2)
                        if (is_local and seek_offset > 0)
                        else (stream_rate * 4 // 4)
                    )

                    # Watchdog di stallo: forza riavvio di ffmpeg se i dati si fermano
                    watchdog_stop = threading.Event()
                    forced_error_ref = {"v": False}

                    def _stall_watchdog_local(
                        _watchdog_stop=watchdog_stop,
                        _forced_error_ref=forced_error_ref,
                        _watched_proc=local_proc,
                    ):
                        nonlocal last_data_ts
                        _last_wd_log = [0]
                        while not _watchdog_stop.is_set():
                            if _session_aborted():
                                break
                            with self._state_lock:
                                p = self._ffmpeg_process
                            try:
                                ended = (
                                    (p is None)
                                    or (p is not _watched_proc)
                                    or (p.poll() is not None)
                                )
                            except Exception:
                                ended = True
                            if ended:
                                break
                            try:
                                if is_local and self._paused:
                                    last_data_ts = time.time()
                                    if _watchdog_stop.wait(0.5):
                                        break
                                    continue
                                delta = time.time() - last_data_ts
                            except Exception:
                                delta = stall_timeout + 1

                            now_int = int(time.time())
                            if now_int != _last_wd_log[0] and now_int % 5 == 0:
                                _last_wd_log[0] = now_int
                                try:
                                    self.log.debug(
                                        "[DEBUG] _stall_watchdog: delta=%.1f s, pid=%s, started=%s",
                                        delta,
                                        p.pid if p else "None",
                                        started_streaming,
                                    )
                                except Exception:
                                    pass

                            if delta > stall_timeout:
                                try:
                                    self.log.debug(
                                        "[DEBUG] _stall_watchdog: stall detected (%.2fs > %.2fs), "
                                        "terminating ffmpeg",
                                        delta,
                                        stall_timeout,
                                    )
                                except Exception:
                                    pass
                                _forced_error_ref["v"] = True
                                self._terminate_ffmpeg_proc(_watched_proc)
                                break
                            if _watchdog_stop.wait(0.5):
                                break

                    watchdog_thread = threading.Thread(target=_stall_watchdog_local, daemon=True)
                    try:
                        watchdog_thread.start()
                    except Exception:
                        pass

                    stderr_chunks: list[bytes] = []

                    def _drain_stderr(
                        _proc=local_proc,
                        _chunks=stderr_chunks,
                    ) -> None:
                        try:
                            if _proc is None or _proc.stderr is None:
                                return
                            total = 0
                            while True:
                                buf = _proc.stderr.read(4096)
                                if not buf:
                                    break
                                if total < 65536:
                                    take = buf[: 65536 - total]
                                    _chunks.append(take)
                                    total += len(take)
                        except Exception:
                            pass

                    stderr_thread = threading.Thread(
                        target=_drain_stderr, name="FFmpegStderrDrain", daemon=True
                    )
                    try:
                        stderr_thread.start()
                    except Exception:
                        pass

                    while True:
                        if self._is_seek_interrupted(seek_seq_at_start):
                            seek_restarted = True
                            prebuffer.clear()
                            break
                        if is_local and started_streaming and self._paused:
                            while (
                                self._paused
                                and not _session_aborted()
                                and not self._is_seek_interrupted(seek_seq_at_start)
                            ):
                                last_data_ts = time.time()
                                self._write_pause_silence(local_stream, chunk_size)
                            last_data_ts = time.time()
                            if self._is_seek_interrupted(seek_seq_at_start):
                                seek_restarted = True
                                prebuffer.clear()
                                break
                            if _session_aborted():
                                break
                        with self._state_lock:
                            if _session_aborted():
                                self.log.debug(
                                    "[DEBUG] _stream_worker: stop event set, breaking loop"
                                )
                                break
                            proc: Any = local_proc  # type: ignore[no-redef]
                        if proc is None:
                            self.log.debug("[DEBUG] _stream_worker: ffmpeg process missing")
                            forced_error = True
                            break
                        if proc.poll() is not None:
                            if self._is_seek_interrupted(seek_seq_at_start):
                                seek_restarted = True
                                prebuffer.clear()
                                break
                            code = proc.poll()
                            err = b""
                            try:
                                if stderr_thread.is_alive():
                                    stderr_thread.join(timeout=0.1)
                                if stderr_chunks:
                                    err = b"".join(stderr_chunks)
                                elif proc.stderr:
                                    err = proc.stderr.read() or b""  # type: ignore[assignment]
                            except Exception as e:
                                self.log.debug("[DEBUG] error reading ffmpeg stderr: %s", e)
                            err_text = err.decode(errors="ignore").strip()
                            if code not in (0, None) or err_text:
                                self.log.error(
                                    "[BACKEND] PlayerFFmpeg: FFmpeg process exited "
                                    "with code %s: %s",
                                    code,
                                    err_text or "no stderr output",
                                )
                            else:
                                self.log.debug(
                                    "[DEBUG] _stream_worker: ffmpeg process ended "
                                    "normally (code: %s)",
                                    code,
                                )
                            try:
                                if "forced_error_ref" in locals() and forced_error_ref.get("v"):
                                    forced_error = True
                            except Exception:
                                pass
                            if not forced_error:
                                try:
                                    if code not in (0, None):
                                        forced_error = True
                                    elif err and err.strip():
                                        forced_error = True
                                except Exception:
                                    pass
                            if (
                                not forced_error
                                and not started_streaming
                                and is_local
                                and (prebuffer or seek_offset > 0)
                            ):
                                started_streaming = True
                                seek_restarted, has_emitted_playing = self._flush_prebuffer(
                                    prebuffer,
                                    seek_seq_at_start,
                                    has_emitted_playing,
                                    stop_event=local_stop,
                                    session_id=session_id,
                                    target_stream=local_stream,
                                )
                            break

                        if proc.stdout is None:
                            self.log.debug("[DEBUG] _stream_worker: ffmpeg stdout is None")
                            forced_error = True
                            break

                        try:
                            chunk = proc.stdout.read(chunk_size)
                        except Exception as e:
                            self.log.debug(
                                "[DEBUG] _stream_worker: exception reading ffmpeg stdout: %s", e
                            )
                            if self._is_seek_interrupted(seek_seq_at_start):
                                seek_restarted = True
                                prebuffer.clear()
                                break
                            if not _session_aborted():
                                forced_error = True
                            break

                        if not chunk:
                            if self._is_seek_interrupted(seek_seq_at_start):
                                seek_restarted = True
                                prebuffer.clear()
                                break
                            empty_reads += 1
                            if proc.poll() is None and not _session_aborted():
                                if empty_reads % 20 == 0:
                                    self.log.debug(
                                        "[DEBUG] _stream_worker: empty chunk (x%d), waiting...",
                                        empty_reads,
                                    )
                                time.sleep(0.05)
                                continue
                            else:
                                self.log.debug(
                                    "[DEBUG] _stream_worker: ffmpeg stdout EOF after process ended"
                                )
                                if (
                                    not started_streaming
                                    and is_local
                                    and proc.poll() == 0
                                    and (prebuffer or seek_offset > 0)
                                ):
                                    started_streaming = True
                                    seek_restarted, has_emitted_playing = self._flush_prebuffer(
                                        prebuffer,
                                        seek_seq_at_start,
                                        has_emitted_playing,
                                        stop_event=local_stop,
                                        session_id=session_id,
                                        target_stream=local_stream,
                                    )
                                break

                        # Ricevuto chunk di dati validi
                        empty_reads = 0
                        last_data_ts = time.time()

                        n_bytes = (len(chunk) // 2) * 2
                        if n_bytes == 0:
                            time.sleep(0.01)
                            continue
                        data: bytes = chunk[:n_bytes]  # type: ignore[assignment]

                        # Jitter buffer iniziale: accumula dati prima di iniziare la riproduzione
                        if not started_streaming:
                            prebuffer.append(data)
                            if sum(len(c) for c in prebuffer) >= prebuffer_target_bytes:
                                started_streaming = True
                                self.log.debug(
                                    "[DEBUG] _stream_worker: pre-buffer filled (%d B), playing",
                                    sum(len(c) for c in prebuffer),
                                )
                                seek_restarted, has_emitted_playing = self._flush_prebuffer(
                                    prebuffer,
                                    seek_seq_at_start,
                                    has_emitted_playing,
                                    stop_event=local_stop,
                                    session_id=session_id,
                                    target_stream=local_stream,
                                )
                                if seek_restarted:
                                    break
                            continue

                        # Riproduzione standard continua con gestione volume e buffer safety
                        self._write_audio_chunk(data, target_stream=local_stream)

                    # prova a spegnere il watchdog
                    try:
                        watchdog_stop.set()
                        if "watchdog_thread" in locals() and watchdog_thread.is_alive():
                            watchdog_thread.join(timeout=1.0)
                    except Exception:
                        pass
                    # Propaga eventuale errore forzato dal watchdog per questo tentativo
                    try:
                        if (
                            not seek_restarted
                            and "forced_error_ref" in locals()
                            and forced_error_ref.get("v")
                        ):
                            forced_error = True
                    except Exception:
                        pass

                    # Fine tentativo: chiudi il processo se non ancora terminato
                    if (
                        local_proc
                        and local_proc.poll() is None
                        and (not started_streaming or seek_restarted or _session_aborted())
                    ):
                        self._terminate_ffmpeg_proc(local_proc, kill_immediately=True)
                    if seek_restarted or self._is_seek_interrupted(seek_seq_at_start):
                        seek_restarted = True
                        break
                    # Se abbiamo iniziato lo streaming, interrompi la catena di fallback
                    if started_streaming or _session_aborted():
                        break

                if (
                    seek_restarted or self._is_seek_interrupted(last_seek_seq)
                ) and not _session_aborted():
                    continue
                break

            # Post-loop: gestione esiti
            self.log.debug("[DEBUG] _stream_worker: cleaning up ffmpeg process")
            if local_proc and local_proc.poll() is None:
                self._terminate_ffmpeg_proc(local_proc)

            is_current_session = session_id is None or session_id == self._session_seq
            if is_current_session:
                if not (local_stop.is_set() or self._stop_requested):
                    if forced_error:
                        self.log.error(
                            "[BACKEND] PlayerFFmpeg: stream failed or stalled; emitting error"
                        )
                        terminal_event = "error"
                    elif not started_streaming:
                        self.log.error(
                            "[BACKEND] PlayerFFmpeg: connection failed before receiving audio data"
                            " (all attempts); emitting error"
                        )
                        terminal_event = "error"
                    else:
                        self.log.debug("[DEBUG] _stream_worker: stream ended naturally")
                        terminal_event = "ended"
                else:
                    self.log.debug("[DEBUG] _stream_worker: stream stopped by request")
                    terminal_event = "stopped"

        except Exception as e:
            self.log.error(
                "[BACKEND] PlayerFFmpeg: unhandled exception in stream worker thread: %s", e
            )
            if not (local_stop.is_set() or self._stop_requested):
                terminal_event = "error"
        finally:
            self.log.debug("[DEBUG] _stream_worker: final cleanup (session=%s)", session_id)
            if local_proc is not None and local_proc.poll() is None:
                self._terminate_ffmpeg_proc(local_proc, kill_immediately=True)
            if local_stream is not None:
                self._close_audio_stream(local_stream, clear_attr=True)
            with self._state_lock:
                is_current_session = session_id is None or session_id == self._session_seq
                if is_current_session:
                    self._playing = False
                    self._paused = False
                    self._current_stream = None
                    if self._ffmpeg_process is local_proc:
                        self._ffmpeg_process = None
                try:
                    if self._stream_thread is threading.current_thread():
                        self._stream_thread = None
                except Exception:
                    pass
            # Emit terminal state only after process, PortAudio stream, and flags
            # are completely cleaned up so handlers (e.g. local autoswitch / repeat-one)
            # can safely call play_url() without racing the exiting worker.
            if terminal_event is not None:
                self._emit_if_session(session_id, terminal_event, None)
            self.log.debug("[DEBUG] _stream_worker: exited")
