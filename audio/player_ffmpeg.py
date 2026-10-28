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
        # lock protecting _ffmpeg_process and _audio_stream
        self._state_lock = threading.RLock()
        self._stream_thread: threading.Thread | None = None
        self._audio_stream: Any | None = None
        self._pyaudio_instance: Any | None = None  # type: ignore
        self._ffmpeg_process: subprocess.Popen | None = None
        # Track pause state explicitly
        self._paused: bool = False
        self._init_error: str | None = None
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
                    if isinstance(dev_info, dict) and int(dev_info.get("maxOutputChannels", 0)) > 0:
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

    def _check_ffmpeg(self) -> bool:
        """Check if ffmpeg is available."""
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
            return result.returncode == 0
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
        """Estrae e sanifica un URL di streaming, rimuovendo in modo aggressivo
        apici/backtick e punteggiatura finale.
        Usa una classe di caratteri consentiti per l'URL (coerente con la UI)
        per evitare di catturare simboli indesiderati.
        """
        try:
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

    def play_url(self, url: str) -> bool:
        if not self.is_ready():
            # Backend (ffmpeg) non pronto: emette errore generico
            self._emit("error", None)
            return False

        try:
            self.log.debug("[DEBUG] play_url: requested for %s", url)
            # Sanitize URL in ingresso (whitelist dei caratteri + estrazione http(s))
            raw_in = url
            safe_url = self._sanitize_stream_url(raw_in)
            if safe_url != raw_in:
                try:
                    self.log.debug(
                        "[DEBUG] play_url: sanitized url: %r from raw: %r", safe_url, raw_in
                    )
                except Exception:
                    pass
            # Stop any current stream first (only if needed)
            need_stop = False
            with self._state_lock:
                need_stop = bool(
                    self._playing or (self._stream_thread and self._stream_thread.is_alive())
                )
                # Reset pause state for a fresh start
                self._paused = False
            if need_stop:
                self.stop()
                # Brief pause to ensure resources settle
                time.sleep(0.1)
            else:
                self.log.debug("[DEBUG] play_url: no active stream, skip stop.")

            # Attendi che il thread sia effettivamente terminato
            if self._stream_thread and self._stream_thread.is_alive():
                self.log.debug("[DEBUG] Waiting for previous stream thread to finish...")
                self._stream_thread.join(timeout=2.0)
                if self._stream_thread.is_alive():
                    self.log.debug("[DEBUG] Previous stream thread did not terminate in time.")

            # Check if we're already playing the same URL (controlla PRIMA di settare i flag)
            if self._current_stream == safe_url and self._playing:
                self.log.debug("[DEBUG] Already playing this stream, skipping.")
                return True

            # Reset state safely (azzera PRIMA di creare il thread)
            with self._state_lock:
                self._current_stream = safe_url
                self._stop_requested = False
                self._stop_event.clear()
                self._playing = True

            self.log.debug("[DEBUG] play_url: starting stream thread")
            # Start streaming thread with error handling
            try:
                self._stream_thread = threading.Thread(target=self._stream_worker, args=(safe_url,))
                self._stream_thread.daemon = True
                self._stream_thread.start()
            except Exception:
                self._playing = False
                self._current_stream = None
                self._emit("error", None)
                return False

            return True
        except Exception:
            self._playing = False
            self._current_stream = None
            self._emit("error", None)
            return False

    def stop(self) -> None:
        self.log.debug("[DEBUG] stop: called")
        if not self.is_ready():
            return
        if not self._playing and not (self._stream_thread and self._stream_thread.is_alive()):
            self.log.debug("[DEBUG] stop: already stopped, skipping redundant stop.")
            return
        try:
            # Signal worker to stop
            with self._state_lock:
                self._stop_requested = True
                self._stop_event.set()
                self._playing = False
                self._paused = False

            # Capture whether there was an active worker thread
            had_worker_running = bool(self._stream_thread and self._stream_thread.is_alive())

            # Terminate ffmpeg process safely
            with self._state_lock:
                proc: Any = self._ffmpeg_process  # type: ignore[no-redef]
                self._ffmpeg_process = None
            if proc:
                try:
                    if proc.poll() is None:
                        proc.terminate()
                        try:
                            proc.wait(timeout=0.5)
                        except subprocess.TimeoutExpired:
                            try:
                                proc.kill()
                                proc.wait(timeout=0.5)
                            except Exception:
                                pass
                        if proc.poll() is None:
                            try:
                                proc.kill()
                            except Exception:
                                pass
                except Exception:
                    pass

            # Wait for thread to finish with timeout
            thread_ref = self._stream_thread
            if thread_ref and thread_ref.is_alive():
                try:
                    self.log.debug("[DEBUG] Waiting for stream thread to terminate after stop...")
                    thread_ref.join(timeout=2.0)
                except Exception:
                    pass
                if thread_ref.is_alive():
                    self.log.debug("[DEBUG] Stream thread did not terminate after stop.")
            # Clear thread reference if it's no longer alive
            if self._stream_thread and not self._stream_thread.is_alive():
                self._stream_thread = None

            # Keep PyAudio instance alive for performance
            self._current_stream = None
            # Evita doppio emit: se c'era un worker attivo, sarà il worker ad emettere 'stopped'
            if not had_worker_running:
                self._emit("stopped", None)
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

    def get_volume(self) -> int:
        return self._user_volume

    def get_mute(self) -> bool:
        return self._muted

    def is_playing(self) -> bool:
        return bool(self._playing and not self._stop_requested)

    def is_paused(self) -> bool:
        return bool(self._paused)

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
            self._stop_requested = True
            self._stop_event.set()
            self._playing = False
            self._paused = False

            # Force kill ffmpeg process
            with self._state_lock:
                proc: Any = self._ffmpeg_process  # type: ignore[no-redef]
                self._ffmpeg_process = None
            if proc:
                try:
                    if proc.poll() is None:
                        proc.kill()
                        try:
                            proc.wait(timeout=1.0)
                        except Exception:
                            pass
                except Exception:
                    pass

            # Force stop audio stream
            if self._audio_stream:
                try:
                    if getattr(self._audio_stream, "is_active", lambda: False)():
                        try:
                            self._audio_stream.stop_stream()
                        except Exception:
                            pass
                    try:
                        self._audio_stream.close()
                    except Exception:
                        pass
                except Exception:
                    pass
                finally:
                    self._audio_stream = None

            # Wait for thread to finish with timeout
            if self._stream_thread and self._stream_thread.is_alive():
                try:
                    self.log.debug(
                        "[DEBUG] Waiting for stream thread to terminate after force_cleanup..."
                    )
                    self._stream_thread.join(timeout=2.0)
                except Exception:
                    pass
                if self._stream_thread.is_alive():
                    self.log.debug("[DEBUG] Stream thread did not terminate after force_cleanup.")
            # Clear thread reference if it's no longer alive
            if self._stream_thread and not self._stream_thread.is_alive():
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

    def _write_audio_chunk(self, data: bytes) -> None:
        """Applica il controllo dinamico del volume e scrive il chunk PCM
        nello stream PyAudio con gestione di underflow e pause."""
        stream = self._audio_stream
        if stream is None:
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
        if self._muted or paused:
            try:
                stream.write(b"\x00" * n_bytes, exception_on_underflow=False)
            except Exception:
                pass
            return

        vol = self._volume
        # Ottimizzazione: a volume massimo (o quasi), invia direttamente il chunk raw
        if vol >= 0.999:
            chunk_to_write = data
        elif vol <= 0.001:
            chunk_to_write = b"\x00" * n_bytes
        else:
            try:
                n_samples = n_bytes // 2
                samples = struct.unpack(f"<{n_samples}h", data)
                vol_samples = [max(-32768, min(32767, int(s * vol))) for s in samples]
                chunk_to_write = struct.pack(f"<{n_samples}h", *vol_samples)
            except Exception:
                chunk_to_write = data

        try:
            stream.write(chunk_to_write, exception_on_underflow=False)
        except Exception as e:
            self.log.debug("[DEBUG] _write_audio_chunk: error writing chunk: %s", e)

    def _stream_worker(self, url: str) -> None:
        self.log.debug("[DEBUG] _stream_worker: started for url: %s", url)
        try:
            self._emit("opening", None)

            # Check ffmpeg availability
            self.log.debug("[DEBUG] _stream_worker: checking ffmpeg availability")
            if not self._check_ffmpeg():
                self.log.error("[BACKEND] PlayerFFmpeg: ffmpeg is not available")
                self._emit("error", None)
                return

            # Open audio stream with robust sample rate negotiation
            self.log.debug("[DEBUG] _stream_worker: opening PyAudio stream")
            if self._pyaudio_instance is not None:
                try:
                    device_idx = self._get_output_device_index()
                    self._audio_stream, stream_rate = self._open_pyaudio_stream(device_idx)
                    try:
                        if self._audio_stream is not None and hasattr(
                            self._audio_stream, "start_stream"
                        ):
                            self._audio_stream.start_stream()
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
                    self._emit("error", None)
                    return
            else:
                self.log.error("[BACKEND] PlayerFFmpeg: PyAudio instance is not ready")
                self._emit("error", None)
                return

            # Sanitize URL (robusta e coerente con play_url)
            raw_url = url
            safe_url = self._sanitize_stream_url(raw_url)
            self.log.debug(
                "[DEBUG] _stream_worker: sanitized url: %r from raw: %r", safe_url, raw_url
            )

            # Costruisci lista di URL candidati con fallback automatici (solo endpoint HTTPS)
            candidates: list[str] = [safe_url]
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
            candidates = [c for c in candidates if c.lower().startswith("https://")] or [safe_url]

            # Tenta in sequenza ogni URL candidato finché non si ricevono dati
            started_streaming = False
            forced_error = False
            for attempt_idx, cur_url in enumerate(candidates):
                if self._stop_event.is_set():
                    break
                try:
                    self.log.debug(
                        "[DEBUG] _stream_worker: attempt %d with url: %s", attempt_idx + 1, cur_url
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
                    # Network/HTTP options for robust streaming
                    "-rw_timeout",
                    "15000000",
                    "-user_agent",
                    self._user_agent,
                ]
                # Add reconnect options to handle stream switches gracefully
                try:
                    ffmpeg_cmd.extend(
                        [
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
                except Exception:
                    pass

                # Apply MP3-specific headers (some servers expect audio/mpeg Accept)
                if is_mp3:
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
                        "-probesize",
                        "32768",
                        "-analyzeduration",
                        "0",
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
                    self._ffmpeg_process = None
                try:
                    kwargs: dict = {}
                    if _IS_WIN32:
                        kwargs["creationflags"] = getattr(
                            subprocess, "CREATE_NO_WINDOW", 0x08000000
                        )
                    self.log.debug("[DEBUG] _stream_worker: launching ffmpeg: %r", ffmpeg_cmd)
                    self._ffmpeg_process = subprocess.Popen(
                        ffmpeg_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        stdin=subprocess.DEVNULL,
                        bufsize=65536,
                        **kwargs,
                    )
                    self.log.debug(
                        "[DEBUG] _stream_worker: ffmpeg process started, pid: %s",
                        self._ffmpeg_process.pid,
                    )
                except Exception as e:
                    self.log.error("[BACKEND] PlayerFFmpeg: failed to launch ffmpeg process: %s", e)
                    self._ffmpeg_process = None
                    continue

                # Loop di lettura dei dati
                # Chunk size = 8192 bytes (2048 frames stereo 16-bit, circa 43ms a 48kHz)
                chunk_size = 8192
                empty_reads = 0
                stall_timeout = 10.0
                last_data_ts = time.time()
                prebuffer: list[bytes] = []
                # Bufferizza circa 0.25s di audio prima di avviare l'emissione (elimina crackle)
                prebuffer_target_bytes = stream_rate * 4 // 4

                # Watchdog di stallo: se non arrivano dati per troppo tempo, forza riavvio di ffmpeg
                watchdog_stop = threading.Event()
                forced_error_ref = {"v": False}

                def _stall_watchdog_local():
                    _last_wd_log = [0]
                    while not watchdog_stop.is_set():
                        if self._stop_event.is_set():
                            break
                        with self._state_lock:
                            p = self._ffmpeg_process
                        try:
                            ended = (p is None) or (p.poll() is not None)
                        except Exception:
                            ended = True
                        if ended:
                            break
                        try:
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
                            forced_error_ref["v"] = True
                            if p is not None:
                                try:
                                    p.terminate()
                                    p.wait(timeout=1.0)
                                except Exception:
                                    try:
                                        p.kill()
                                    except Exception:
                                        pass
                            break
                        time.sleep(0.5)

                watchdog_thread = threading.Thread(target=_stall_watchdog_local, daemon=True)
                try:
                    watchdog_thread.start()
                except Exception:
                    pass

                while True:
                    with self._state_lock:
                        if self._stop_event.is_set():
                            self.log.debug("[DEBUG] _stream_worker: stop event set, breaking loop")
                            break
                        proc: Any = self._ffmpeg_process  # type: ignore[no-redef]
                    if proc is None:
                        self.log.debug("[DEBUG] _stream_worker: ffmpeg process missing")
                        forced_error = True
                        break
                    if proc.poll() is not None:
                        code = proc.poll()
                        err = b""
                        try:
                            if proc.stderr:
                                err = proc.stderr.read() or b""  # type: ignore[assignment]
                        except Exception as e:
                            self.log.debug("[DEBUG] error reading ffmpeg stderr: %s", e)
                        err_text = err.decode(errors="ignore").strip()
                        if code not in (0, None) or err_text:
                            self.log.error(
                                "[BACKEND] PlayerFFmpeg: FFmpeg process exited with code %s: %s",
                                code,
                                err_text or "no stderr output",
                            )
                        else:
                            self.log.debug(
                                "[DEBUG] _stream_worker: ffmpeg process ended normally (code: %s)",
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
                        forced_error = True
                        break

                    if not chunk:
                        empty_reads += 1
                        if proc.poll() is None:
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
                            self._emit("paused" if self.is_paused() else "playing", None)
                            for pre_chunk in prebuffer:
                                if self._stop_event.is_set():
                                    break
                                self._write_audio_chunk(pre_chunk)
                            prebuffer.clear()
                        continue

                    # Riproduzione standard continua con gestione volume e buffer safety
                    self._write_audio_chunk(data)

                # prova a spegnere il watchdog
                try:
                    watchdog_stop.set()
                    if "watchdog_thread" in locals() and watchdog_thread.is_alive():
                        watchdog_thread.join(timeout=1.0)
                except Exception:
                    pass
                # Propaga eventuale errore forzato dal watchdog per questo tentativo
                try:
                    if "forced_error_ref" in locals() and forced_error_ref.get("v"):
                        forced_error = True
                except Exception:
                    pass

                # Fine tentativo: se non abbiamo iniziato a ricevere dati,
                # chiudi il processo e prova il prossimo
                with self._state_lock:
                    proc: Any = self._ffmpeg_process  # type: ignore[no-redef]
                if proc and proc.poll() is None and not started_streaming:
                    try:
                        proc.terminate()
                        proc.wait(timeout=1.0)
                    except Exception:
                        try:
                            proc.kill()
                        except Exception:
                            pass
                # Se abbiamo iniziato lo streaming, interrompi la catena di fallback
                if started_streaming or self._stop_event.is_set():
                    break

            # Post-loop: gestione esiti
            self.log.debug("[DEBUG] _stream_worker: cleaning up ffmpeg process")
            with self._state_lock:
                proc: Any = self._ffmpeg_process  # type: ignore[no-redef]
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=2.0)
                    self.log.debug("[DEBUG] _stream_worker: ffmpeg process terminated")
                except Exception as e:
                    self.log.debug("[DEBUG] _stream_worker: error terminating ffmpeg: %s", e)
                    try:
                        proc.kill()
                        self.log.debug("[DEBUG] _stream_worker: ffmpeg process killed")
                    except Exception as e2:
                        self.log.debug("[DEBUG] _stream_worker: error killing ffmpeg: %s", e2)

            if not self._stop_requested:
                if forced_error:
                    self.log.error(
                        "[BACKEND] PlayerFFmpeg: stream failed or stalled; emitting error"
                    )
                    self._emit("error", None)
                elif not started_streaming:
                    self.log.error(
                        "[BACKEND] PlayerFFmpeg: connection failed before receiving audio data"
                        " (all attempts); emitting error"
                    )
                    self._emit("error", None)
                else:
                    self.log.debug("[DEBUG] _stream_worker: stream ended naturally")
                    self._emit("ended", None)
            else:
                self.log.debug("[DEBUG] _stream_worker: stream stopped by request")
                self._emit("stopped", None)

        except Exception as e:
            self.log.error(
                "[BACKEND] PlayerFFmpeg: unhandled exception in stream worker thread: %s", e
            )
            if not self._stop_requested:
                self._emit("error", None)
        finally:
            self.log.debug("[DEBUG] _stream_worker: final cleanup")
            self._playing = False
            self._current_stream = None
            if self._audio_stream:
                try:
                    if getattr(self._audio_stream, "is_active", lambda: False)():
                        try:
                            self._audio_stream.stop_stream()
                            self.log.debug("[DEBUG] _stream_worker: audio stream stopped")
                        except Exception as e:
                            self.log.debug(
                                "[DEBUG] _stream_worker: error stopping audio stream: %s", e
                            )
                    try:
                        self._audio_stream.close()
                        self.log.debug("[DEBUG] _stream_worker: audio stream closed")
                    except Exception as e:
                        self.log.debug("[DEBUG] _stream_worker: error closing audio stream: %s", e)
                except Exception as e:
                    self.log.debug("[DEBUG] _stream_worker: error in audio stream cleanup: %s", e)
                self._audio_stream = None
            with self._state_lock:
                try:
                    if self._stream_thread is threading.current_thread():
                        self._stream_thread = None
                except Exception:
                    pass
                self._ffmpeg_process = None
            self.log.debug("[DEBUG] _stream_worker: exited")
