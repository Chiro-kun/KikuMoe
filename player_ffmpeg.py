from __future__ import annotations
from typing import Optional, Callable, Any
import os
import threading
import time
import subprocess
import sys
import struct
import re
from logger import get_logger
from PyQt5.QtCore import QSettings
from constants import APP_NAME, APP_VERSION, ORG_NAME, APP_SETTINGS, KEY_AUDIO_DEVICE_INDEX

try:
    import pyaudio
except Exception:
    pyaudio = None  # type: ignore


class PlayerFFmpeg:
    def __init__(self, on_event: Optional[Callable[[str, Optional[int]], None]] = None) -> None:
        self._on_event = on_event
        self._muted: bool = False
        self._volume: float = 1.0
        self._ready: bool = False
        self._playing: bool = False
        self._current_stream: Optional[str] = None
        # stop event replaces boolean flag to safely notify worker thread
        self._stop_requested = False
        self._stop_event = threading.Event()
        # lock protecting _ffmpeg_process and _audio_stream
        self._state_lock = threading.Lock()
        self._stream_thread: Optional[threading.Thread] = None
        self._audio_stream: Optional[Any] = None
        self._pyaudio_instance: Optional[Any] = None  # type: ignore
        self._ffmpeg_process: Optional[subprocess.Popen] = None
        # Track pause state explicitly
        self._paused: bool = False
        self.log = get_logger('PlayerFFmpeg')
        # Build dynamic User-Agent from constants (e.g., "KikuMoe/1.8.0.0")
        try:
            self._user_agent = f"{APP_NAME}/{APP_VERSION}"
        except Exception:
            self._user_agent = "KikuMoe/1.8"
        self._init_audio()

    def _init_audio(self) -> None:
        self._ready = False
        if pyaudio is None:
            return
        try:
            self._pyaudio_instance = pyaudio.PyAudio()
            self._ready = True
        except Exception:
            self._ready = False

    def is_ready(self) -> bool:
        return bool(self._ready and pyaudio is not None)

    def reinitialize(self, libvlc_path: Optional[str] = None, network_caching_ms: Optional[int] = None) -> bool:
        return self.is_ready()

    def _emit(self, code: str, value: Optional[int] = None) -> None:
        if self._on_event:
            try:
                self._on_event(code, value)
            except Exception:
                pass

    def _check_ffmpeg(self) -> bool:
        """Check if ffmpeg is available."""
        try:
            result = subprocess.run(['ffmpeg', '-version'],
                                    capture_output=True, check=False, timeout=5, **({"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}))
            return result.returncode == 0
        except Exception:
            return False

    def _get_output_device_index(self) -> Optional[int]:
        """Legge l'indice del dispositivo di output da QSettings; None => predefinito di Windows."""
        try:
            settings = QSettings(ORG_NAME, APP_SETTINGS)
            val = settings.value(KEY_AUDIO_DEVICE_INDEX, '')
            if val in (None, ''):
                return None
            try:
                return int(val)
            except Exception:
                return None
        except Exception:
            return None

    def _sanitize_stream_url(self, raw: str) -> str:
        """Estrae e sanifica un URL di streaming, rimuovendo in modo aggressivo apici/backtick e punteggiatura finale.
        Usa una classe di caratteri consentiti per l'URL (coerente con la UI) per evitare di catturare simboli indesiderati.
        """
        try:
            s = (raw or "")
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
            if lower.endswith('/mp3.') or lower.endswith('.mp3.'):
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
            self._emit('error', None)
            return False

        try:
            self.log.debug("[DEBUG] play_url: requested for %s", url)
            # Sanitize URL in ingresso (whitelist dei caratteri + estrazione http(s))
            raw_in = url
            safe_url = self._sanitize_stream_url(raw_in)
            if safe_url != raw_in:
                try:
                    self.log.debug("[DEBUG] play_url: sanitized url: %r from raw: %r", safe_url, raw_in)
                except Exception:
                    pass
            # Stop any current stream first (only if needed)
            need_stop = False
            with self._state_lock:
                need_stop = bool(self._playing or (self._stream_thread and self._stream_thread.is_alive()))
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
                self._emit('error', None)
                return False

            return True
        except Exception:
            self._playing = False
            self._current_stream = None
            self._emit('error', None)
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
                proc = self._ffmpeg_process
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
            if self._stream_thread and self._stream_thread.is_alive():
                try:
                    self.log.debug("[DEBUG] Waiting for stream thread to terminate after stop...")
                    self._stream_thread.join(timeout=2.0)
                except Exception:
                    pass
                if self._stream_thread.is_alive():
                    self.log.debug("[DEBUG] Stream thread did not terminate after stop.")
            # Clear thread reference if it's no longer alive
            if self._stream_thread and not self._stream_thread.is_alive():
                self._stream_thread = None

            # Ora che il thread è terminato, è sicuro rilasciare/ricreare PyAudio (se necessario)
            if self._pyaudio_instance:
                try:
                    self._pyaudio_instance.terminate()
                except Exception:
                    pass
                self._pyaudio_instance = None
                try:
                    import pyaudio
                    self._pyaudio_instance = pyaudio.PyAudio()
                except Exception:
                    self._ready = False

            self._current_stream = None
            # Evita doppio emit: se c'era un worker attivo, sarà il worker ad emettere 'stopped'
            if not had_worker_running:
                self._emit('stopped', None)
        except Exception as e:
            try:
                self.log.debug("[DEBUG] stop: exception during stop: %s", e)
            except Exception:
                pass

    def pause_toggle(self) -> None:
        if not self.is_ready():
            return

        try:
            if self._playing:
                if self._audio_stream and getattr(self._audio_stream, "is_active", lambda: False)():
                    try:
                        self._audio_stream.stop_stream()
                        self._paused = True
                        try:
                            self.log.debug("[DEBUG] pause_toggle: paused")
                        except Exception:
                            pass
                    except Exception:
                        pass
                    self._emit('paused', None)
                elif self._audio_stream:
                    try:
                        self._audio_stream.start_stream()
                        self._paused = False
                        try:
                            self.log.debug("[DEBUG] pause_toggle: resumed -> playing")
                        except Exception:
                            pass
                    except Exception:
                        pass
                    self._emit('playing', None)
        except Exception:
            self._emit('error', None)

    def set_volume(self, vol: int) -> None:
        self._volume = max(0.0, min(1.0, float(vol) / 100.0))

    def set_mute(self, mute: bool) -> None:
        self._muted = bool(mute)

    def get_volume(self) -> int:
        return int(self._volume * 100)

    def get_mute(self) -> bool:
        return self._muted

    def is_playing(self) -> bool:
        return bool(self._playing and not self._stop_requested)

    def is_paused(self) -> bool:
        return bool(self._paused)

    def get_version(self) -> Optional[str]:
        """Return ffmpeg version string if available."""
        try:
            result = subprocess.run(['ffmpeg', '-version'],
                                    capture_output=True, text=True, timeout=5, **({"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}))
            if result.returncode == 0:
                return result.stdout.split('\n')[0]
        except Exception:
            pass
        return None

    def get_configured_path(self) -> Optional[str]:
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
                proc = self._ffmpeg_process
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
                    self.log.debug("[DEBUG] Waiting for stream thread to terminate after force_cleanup...")
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

    def force_kill_all_vlc(self) -> None:
        """Kill any remaining ffmpeg processes (method name kept for UI compatibility)."""
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/f", "/im", "ffmpeg.exe"],
                               capture_output=True, check=False, **({"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}))
            else:
                subprocess.run(["pkill", "-f", "ffmpeg"],
                               capture_output=True, check=False)
        except Exception:
            pass

    def _stream_worker(self, url: str) -> None:
        self.log.debug("[DEBUG] _stream_worker: started for url: %s", url)
        try:
            self._emit('opening', None)

            # Check ffmpeg availability
            self.log.debug("[DEBUG] _stream_worker: checking ffmpeg availability")
            if not self._check_ffmpeg():
                self.log.debug("[DEBUG] _stream_worker: ffmpeg not available")
                self._emit('error', None)
                return

            # Open audio stream
            self.log.debug("[DEBUG] _stream_worker: opening PyAudio stream")
            if self._pyaudio_instance is not None and hasattr(self._pyaudio_instance, "open"):
                pa_format = getattr(pyaudio, "paInt16", None)
                try:
                    device_idx = self._get_output_device_index()
                    if device_idx is None:
                        self.log.debug("[DEBUG] _stream_worker: using Windows default output device")
                    else:
                        self.log.debug("[DEBUG] _stream_worker: using output_device_index=%s", device_idx)
                    open_kwargs = {
                        'format': pa_format,
                        'channels': 2,
                        'rate': 44100,
                        'output': True,
                        'frames_per_buffer': 1024,
                    }
                    if device_idx is not None:
                        open_kwargs['output_device_index'] = device_idx
                    # Try open; if fails with a specific device, retry with default system device
                    try:
                        self._audio_stream = self._pyaudio_instance.open(**open_kwargs)
                    except Exception as oe:
                        if device_idx is not None:
                            try:
                                self.log.debug("[DEBUG] _stream_worker: failed to open with device %s, retrying with Windows default: %s", device_idx, oe)
                            except Exception:
                                pass
                            try:
                                open_kwargs.pop('output_device_index', None)
                                self._audio_stream = self._pyaudio_instance.open(**open_kwargs)
                            except Exception as oe2:
                                self.log.debug("[DEBUG] _stream_worker: also failed to open default device: %s", oe2)
                                raise
                        else:
                            raise
                    self.log.debug("[DEBUG] _stream_worker: PyAudio stream opened")
                    try:
                        if hasattr(self._audio_stream, "start_stream"):
                            self._audio_stream.start_stream()
                            self.log.debug("[DEBUG] _stream_worker: PyAudio stream started")
                    except Exception as se:
                        self.log.debug("[DEBUG] _stream_worker: could not start PyAudio stream: %s", se)
                except Exception as e:
                    self.log.debug("[DEBUG] _stream_worker: failed to open PyAudio stream: %s", e)
                    self._emit('error', None)
                    return
            else:
                self.log.debug("[DEBUG] _stream_worker: PyAudio instance not ready")
                self._emit('error', None)
                return

            # Sanitize URL (robusta e coerente con play_url)
            raw_url = url
            safe_url = self._sanitize_stream_url(raw_url)
            self.log.debug("[DEBUG] _stream_worker: sanitized url: %r from raw: %r", safe_url, raw_url)

            # Costruisci lista di URL candidati con fallback automatici
            candidates: List[str] = [safe_url]
            try:
                u = safe_url.lower()
                if '/kpop/' in u:
                    # Preferisci HTTPS Vorbis prima di M3U/HTTP
                    candidates.append('https://listen.moe/kpop/stream')
                    candidates.append('https://listen.moe/kpop/stream.m3u')
                    candidates.append('http://listen.moe:9999/kpop/stream')
                else:
                    candidates.append('https://listen.moe/stream')
                    candidates.append('https://listen.moe/stream.m3u')
                    candidates.append('http://listen.moe:9999/stream')
            except Exception:
                pass

            # Tenta in sequenza ogni URL candidato finché non si ricevono dati
            started_streaming = False
            forced_error = False
            for attempt_idx, cur_url in enumerate(candidates):
                if self._stop_event.is_set():
                    break
                try:
                    self.log.debug("[DEBUG] _stream_worker: attempt %d with url: %s", attempt_idx + 1, cur_url)
                except Exception:
                    pass

                # FFmpeg command to decode stream and output raw audio (with robust HTTP options)
                is_mp3 = False
                try:
                    uu = cur_url.lower()
                    is_mp3 = ("/mp3" in uu) or uu.endswith(".mp3")
                except Exception:
                    is_mp3 = False

                ffmpeg_cmd = [
                    'ffmpeg',
                    '-hide_banner',
                    '-nostdin',
                    # Network/HTTP options for robust streaming
                    '-rw_timeout', '15000000',
                    '-user_agent', self._user_agent,
                ]
                # Add reconnect options to handle stream switches gracefully
                try:
                    ffmpeg_cmd.extend([
                        '-reconnect', '1',
                        '-reconnect_streamed', '1',
                        '-reconnect_at_eof', '1',
                        '-reconnect_delay_max', '2',
                        '-reconnect_on_network_error', '1',
                    ])
                except Exception:
                    pass

                # Apply MP3-specific headers (some servers expect audio/mpeg Accept)
                if is_mp3:
                    try:
                        ffmpeg_cmd.extend([
                            '-headers', 'Accept: audio/mpeg\r\nIcy-MetaData: 0\r\n',
                        ])
                        self.log.debug("[DEBUG] _stream_worker: applying MP3-specific headers")
                    except Exception:
                        pass

                # Input URL
                ffmpeg_cmd.extend(['-i', cur_url])

                # Output format: raw PCM s16le to stdout
                ffmpeg_cmd.extend([
                    '-vn',
                    '-fflags', 'nobuffer',
                    '-f', 's16le',
                    '-ar', '44100',
                    '-ac', '2',
                    '-acodec', 'pcm_s16le',
                    '-af', f'volume={self._volume:.2f}',
                    '-loglevel', 'error',
                    '-',
                ])

                # Launch ffmpeg process
                with self._state_lock:
                    self._ffmpeg_process = None
                try:
                    self.log.debug("[DEBUG] _stream_worker: launching ffmpeg: %r", ffmpeg_cmd)
                    self._ffmpeg_process = subprocess.Popen(
                        ffmpeg_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        stdin=subprocess.DEVNULL,
                        bufsize=0,
                        **({"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {})
                    )
                    self.log.debug("[DEBUG] _stream_worker: ffmpeg process started, pid: %s", self._ffmpeg_process.pid)
                except Exception as e:
                    self.log.debug("[DEBUG] _stream_worker: failed to start ffmpeg: %s", e)
                    self._ffmpeg_process = None
                    # Prova prossimo candidato
                    continue

                # Loop di lettura dei dati
                chunk_size = 4096
                empty_reads = 0
                stall_timeout = 10.0
                last_data_ts = time.time()
                # Watchdog di stallo: se non arrivano dati per troppo tempo, forza riavvio di ffmpeg
                watchdog_stop = threading.Event()
                forced_error_ref = {'v': False}

                def _stall_watchdog_local():
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
                        if delta > stall_timeout:
                            try:
                                self.log.debug("[DEBUG] _stall_watchdog: stall detected (%.2fs > %.2fs), terminating ffmpeg", delta, stall_timeout)
                            except Exception:
                                pass
                            forced_error_ref['v'] = True
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
                    # Se il watchdog non parte, prosegui comunque (sarà lo stdout.read a segnalare problemi)
                    pass

                while True:
                    with self._state_lock:
                        if self._stop_event.is_set():
                            self.log.debug("[DEBUG] _stream_worker: stop event set, breaking loop")
                            break
                        proc = self._ffmpeg_process
                    if proc is None:
                        self.log.debug("[DEBUG] _stream_worker: ffmpeg process missing")
                        forced_error = True
                        break
                    if proc.poll() is not None:
                        code = proc.poll()
                        self.log.debug("[DEBUG] _stream_worker: ffmpeg process ended with code: %s", code)
                        # Try to read stderr if possible
                        err = b""
                        try:
                            if proc.stderr:
                                err = proc.stderr.read() or b""
                                if err:
                                    self.log.debug("[DEBUG] ffmpeg stderr: %s", err.decode(errors='ignore'))
                        except Exception as e:
                            self.log.debug("[DEBUG] error reading ffmpeg stderr: %s", e)
                        # Se il watchdog ha segnalato stallo, marca come errore forzato
                        try:
                            if 'forced_error_ref' in locals() and forced_error_ref.get('v'):
                                forced_error = True
                        except Exception:
                            pass
                        # Se ffmpeg è terminato con codice != 0 o ha scritto su stderr, considera errore
                        if not forced_error:
                            try:
                                if code not in (0, None):
                                    forced_error = True
                                elif err and err.strip():
                                    forced_error = True
                            except Exception:
                                pass
                        # Fine tentativo corrente: passa al prossimo URL
                        break

                        
                    if proc.stdout is None:
                        self.log.debug("[DEBUG] _stream_worker: ffmpeg stdout is None")
                        forced_error = True
                        break

                    try:
                        chunk = proc.stdout.read(chunk_size)
                    except Exception as e:
                        self.log.debug("[DEBUG] _stream_worker: exception reading ffmpeg stdout: %s", e)
                        forced_error = True
                        break

                    if not chunk:
                        empty_reads += 1
                        # If ffmpeg is still running, wait a bit and retry instead of breaking immediately
                        if proc.poll() is None:
                            if empty_reads % 20 == 0:
                                self.log.debug("[DEBUG] _stream_worker: empty chunk (x%d), waiting for data...", empty_reads)
                            time.sleep(0.05)
                            continue
                        else:
                            self.log.debug("[DEBUG] _stream_worker: ffmpeg stdout EOF or empty chunk after process ended")
                            break

                    # got data
                    empty_reads = 0
                    last_data_ts = time.time()
                    if not started_streaming:
                        started_streaming = True
                        self._emit('playing', None)

                    n_bytes = (len(chunk) // 2) * 2
                    if n_bytes == 0:
                        time.sleep(0.01)
                        continue
                    data = chunk[:n_bytes]

                    # Avoid writing to PyAudio when paused/stream inactive to prevent [Errno -9988] spam
                    stream_active = False
                    if self._audio_stream is not None:
                        try:
                            stream_active = getattr(self._audio_stream, "is_active", lambda: False)()
                        except Exception:
                            stream_active = False

                    if not self._muted:
                        try:
                            samples = struct.unpack(f'<{n_bytes // 2}h', data)
                            volume_samples = [int(sample * self._volume) for sample in samples]
                            volume_samples = [max(-32768, min(32767, s)) for s in volume_samples]
                            volume_chunk = struct.pack(f'<{len(volume_samples)}h', *volume_samples)
                            if self._audio_stream is not None and stream_active:
                                self._audio_stream.write(volume_chunk)
                            else:
                                # Paused or no audio stream: skip writing to avoid errors
                                time.sleep(0.02)
                                continue
                        except Exception as e:
                            # Log errors only if stream is active; otherwise likely paused/closed
                            if stream_active:
                                self.log.debug("[DEBUG] _stream_worker: error in audio processing: %s", e)
                                try:
                                    if self._audio_stream is not None and stream_active:
                                        self._audio_stream.write(b'\x00' * n_bytes)
                                except Exception as e2:
                                    self.log.debug("[DEBUG] _stream_worker: error writing silence: %s", e2)
                            else:
                                time.sleep(0.02)
                                continue
                    else:
                        try:
                            if self._audio_stream is not None and stream_active:
                                self._audio_stream.write(b'\x00' * n_bytes)
                            else:
                                # Paused or no audio stream: skip writing to avoid errors
                                time.sleep(0.02)
                                continue
                        except Exception as e:
                            if stream_active:
                                self.log.debug("[DEBUG] _stream_worker: error writing silence (muted): %s", e)
                            else:
                                # Suppress spam when paused/closed
                                pass

                # prova a spegnere il watchdog
                try:
                    watchdog_stop.set()
                    if 'watchdog_thread' in locals() and watchdog_thread.is_alive():
                        watchdog_thread.join(timeout=1.0)
                except Exception:
                    pass
                # Propaga eventuale errore forzato dal watchdog per questo tentativo
                try:
                    if 'forced_error_ref' in locals() and forced_error_ref.get('v'):
                        forced_error = True
                except Exception:
                    pass

                        
                    if proc.stdout is None:
                        self.log.debug("[DEBUG] _stream_worker: ffmpeg stdout is None")
                        forced_error = True
                        break

                    try:
                        chunk = proc.stdout.read(chunk_size)
                    except Exception as e:
                        self.log.debug("[DEBUG] _stream_worker: exception reading ffmpeg stdout: %s", e)
                        forced_error = True
                        break

                    if not chunk:
                        empty_reads += 1
                        # If ffmpeg is still running, wait a bit and retry instead of breaking immediately
                        if proc.poll() is None:
                            if empty_reads % 20 == 0:
                                self.log.debug("[DEBUG] _stream_worker: empty chunk (x%d), waiting for data...", empty_reads)
                            time.sleep(0.05)
                            continue
                        else:
                            self.log.debug("[DEBUG] _stream_worker: ffmpeg stdout EOF or empty chunk after process ended")
                            break

                    # got data
                    empty_reads = 0
                    last_data_ts = time.time()
                    if not started_streaming:
                        started_streaming = True
                        self._emit('playing', None)

                    n_bytes = (len(chunk) // 2) * 2
                    if n_bytes == 0:
                        time.sleep(0.01)
                        continue
                    data = chunk[:n_bytes]

                    # Avoid writing to PyAudio when paused/stream inactive to prevent [Errno -9988] spam
                    stream_active = False
                    if self._audio_stream is not None:
                        try:
                            stream_active = getattr(self._audio_stream, "is_active", lambda: False)()
                        except Exception:
                            stream_active = False

                    if not self._muted:
                        try:
                            samples = struct.unpack(f'<{n_bytes // 2}h', data)
                            volume_samples = [int(sample * self._volume) for sample in samples]
                            volume_samples = [max(-32768, min(32767, s)) for s in volume_samples]
                            volume_chunk = struct.pack(f'<{len(volume_samples)}h', *volume_samples)
                            if self._audio_stream is not None and stream_active:
                                self._audio_stream.write(volume_chunk)
                            else:
                                # Paused or no audio stream: skip writing to avoid errors
                                time.sleep(0.02)
                                continue
                        except Exception as e:
                            # Log errors only if stream is active; otherwise likely paused/closed
                            if stream_active:
                                self.log.debug("[DEBUG] _stream_worker: error in audio processing: %s", e)
                                try:
                                    if self._audio_stream is not None and stream_active:
                                        self._audio_stream.write(b'\x00' * n_bytes)
                                except Exception as e2:
                                    self.log.debug("[DEBUG] _stream_worker: error writing silence: %s", e2)
                            else:
                                time.sleep(0.02)
                                continue
                    else:
                        try:
                            if self._audio_stream is not None and stream_active:
                                self._audio_stream.write(b'\x00' * n_bytes)
                            else:
                                # Paused or no audio stream: skip writing to avoid errors
                                time.sleep(0.02)
                                continue
                        except Exception as e:
                            if stream_active:
                                self.log.debug("[DEBUG] _stream_worker: error writing silence (muted): %s", e)
                            else:
                                # Suppress spam when paused/closed
                                pass

                # prova a spegnere il watchdog
                try:
                    watchdog_stop.set()
                    if 'watchdog_thread' in locals() and watchdog_thread.is_alive():
                        watchdog_thread.join(timeout=1.0)
                except Exception:
                    pass

                # Fine tentativo: se non abbiamo iniziato a ricevere dati, chiudi il processo e prova il prossimo
                with self._state_lock:
                    proc = self._ffmpeg_process
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
                proc = self._ffmpeg_process
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
                    self.log.debug("[DEBUG] _stream_worker: emitting error due to forced_error")
                    self._emit('error', None)
                elif not started_streaming:
                    self.log.debug("[DEBUG] _stream_worker: connection failed before receiving data (all attempts)")
                    self._emit('error', None)
                else:
                    self.log.debug("[DEBUG] _stream_worker: stream ended naturally")
                    self._emit('ended', None)
            else:
                self.log.debug("[DEBUG] _stream_worker: stream stopped by request")
                self._emit('stopped', None)

        except Exception as e:
            self.log.debug("[DEBUG] _stream_worker: outer exception: %s", e)
            if not self._stop_requested:
                self._emit('error', None)
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
                            self.log.debug("[DEBUG] _stream_worker: error stopping audio stream: %s", e)
                    try:
                        self._audio_stream.close()
                        self.log.debug("[DEBUG] _stream_worker: audio stream closed")
                    except Exception as e:
                        self.log.debug("[DEBUG] _stream_worker: error closing audio stream: %s", e)
                except Exception as e:
                    self.log.debug("[DEBUG] _stream_worker: error in audio stream cleanup: %s", e)
                self._audio_stream = None
            with self._state_lock:
                # Clear thread reference if we're the worker thread
                try:
                    if self._stream_thread is threading.current_thread():
                        self._stream_thread = None
                except Exception:
                    # Fallback: ensure at least process ref is dropped
                    pass
                self._ffmpeg_process = None
            self.log.debug("[DEBUG] _stream_worker: exited")
