from __future__ import annotations
from typing import Optional, Callable, Any
import os
import threading
import time
import subprocess
import tempfile
import signal
import sys
import struct
import traceback
import re

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
                                    capture_output=True, check=False, timeout=5)
            return result.returncode == 0
        except Exception:
            return False

    def play_url(self, url: str) -> bool:
        if not self.is_ready():
            # Backend (ffmpeg) non pronto: emette errore generico
            self._emit('error', None)
            return False

        try:
            print("[DEBUG] play_url: requested for", url)
            # Sanitize URL in ingresso (whitelist dei caratteri + estrazione http(s))
            raw_in = url
            pattern = r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&()*+,;=%]+"
            m_raw = re.search(pattern, raw_in)
            if m_raw:
                safe_url = m_raw.group(0)
            else:
                filtered = ''.join(ch for ch in raw_in if (ch.isalnum() or ch in "-._~:/?#[]@!$&()*+,;=%"))
                m_f = re.search(pattern, filtered)
                safe_url = m_f.group(0) if m_f else filtered.strip()
            if safe_url != raw_in:
                print(f"[DEBUG] play_url: sanitized url: {safe_url!r} from raw: {raw_in!r}")
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
                print("[DEBUG] play_url: no active stream, skip stop.")

            # Attendi che il thread sia effettivamente terminato
            if self._stream_thread and self._stream_thread.is_alive():
                print("[DEBUG] Waiting for previous stream thread to finish...")
                self._stream_thread.join(timeout=2.0)
                if self._stream_thread.is_alive():
                    print("[DEBUG] Previous stream thread did not terminate in time.")

            # Check if we're already playing the same URL (controlla PRIMA di settare i flag)
            if self._current_stream == safe_url and self._playing:
                print("[DEBUG] Already playing this stream, skipping.")
                return True

            # Reset state safely (azzera PRIMA di creare il thread)
            with self._state_lock:
                self._current_stream = safe_url
                self._stop_requested = False
                self._stop_event.clear()
                self._playing = True

            print("[DEBUG] play_url: starting stream thread")
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
        print("[DEBUG] stop: called")
        if not self.is_ready():
            return
        if not self._playing and not (self._stream_thread and self._stream_thread.is_alive()):
            print("[DEBUG] stop: already stopped, skipping redundant stop.")
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

            # Importante: non chiudere/fermare l'audio stream qui (thread principale)
            # per evitare race con il thread di streaming che potrebbe essere in write().
            # Lasciamo che sia il worker a chiudere _audio_stream nel suo finally.

            # Wait for thread to finish with timeout
            if self._stream_thread and self._stream_thread.is_alive():
                try:
                    print("[DEBUG] Waiting for stream thread to terminate after stop...")
                    self._stream_thread.join(timeout=2.0)
                except Exception:
                    pass
                if self._stream_thread.is_alive():
                    print("[DEBUG] Stream thread did not terminate after stop.")
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
        except Exception:
            self._emit('error', None)

    def pause_toggle(self) -> None:
        if not self.is_ready():
            return

        try:
            if self._playing:
                if self._audio_stream and getattr(self._audio_stream, "is_active", lambda: False)():
                    try:
                        self._audio_stream.stop_stream()
                        self._paused = True
                    except Exception:
                        pass
                    self._emit('paused', None)
                elif self._audio_stream:
                    try:
                        self._audio_stream.start_stream()
                        self._paused = False
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
                                    capture_output=True, text=True, timeout=5)
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
                    print("[DEBUG] Waiting for stream thread to terminate after force_cleanup...")
                    self._stream_thread.join(timeout=2.0)
                except Exception:
                    pass
                if self._stream_thread.is_alive():
                    print("[DEBUG] Stream thread did not terminate after force_cleanup.")
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
                               capture_output=True, check=False)
            else:
                subprocess.run(["pkill", "-f", "ffmpeg"],
                               capture_output=True, check=False)
        except Exception:
            pass

    def _stream_worker(self, url: str) -> None:
        print("[DEBUG] _stream_worker: started for url:", url)
        try:
            self._emit('opening', None)

            # Check ffmpeg availability
            print("[DEBUG] _stream_worker: checking ffmpeg availability")
            if not self._check_ffmpeg():
                print("[DEBUG] _stream_worker: ffmpeg not available")
                self._emit('error', None)
                return

            # Open audio stream
            print("[DEBUG] _stream_worker: opening PyAudio stream")
            if self._pyaudio_instance is not None and hasattr(self._pyaudio_instance, "open"):
                pa_format = getattr(pyaudio, "paInt16", None)
                try:
                    self._audio_stream = self._pyaudio_instance.open(
                        format=pa_format,
                        channels=2,
                        rate=44100,
                        output=True,
                        frames_per_buffer=1024
                    )
                    print("[DEBUG] _stream_worker: PyAudio stream opened")
                except Exception as e:
                    print("[DEBUG] _stream_worker: failed to open PyAudio stream:", e)
                    self._emit('error', None)
                    return
            else:
                print("[DEBUG] _stream_worker: PyAudio instance not ready")
                self._emit('error', None)
                return

            # Sanitize URL (robusta e coerente con play_url): whitelist + estrazione http(s)
            raw_url = url
            pattern = r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&()*+,;=%]+"
            m_raw = re.search(pattern, raw_url)
            if m_raw:
                safe_url = m_raw.group(0)
            else:
                filtered = ''.join(ch for ch in raw_url if (ch.isalnum() or ch in "-._~:/?#[]@!$&()*+,;=%"))
                m_f = re.search(pattern, filtered)
                safe_url = m_f.group(0) if m_f else filtered.strip()
            print(f"[DEBUG] _stream_worker: sanitized url: {safe_url!r} from raw: {raw_url!r}")

            # FFmpeg command to decode stream and output raw audio (with robust HTTP options)
            ffmpeg_cmd = [
                'ffmpeg',
                '-hide_banner',
                '-nostdin',
                '-reconnect', '1',
                '-reconnect_streamed', '1',
                '-reconnect_delay_max', '5',
                '-rw_timeout', '15000000',
                '-user_agent', 'KikuMoe/1.5',
                '-headers', 'Connection: close\r\n',
                '-i', safe_url,
                '-vn',
                '-fflags', 'nobuffer',
                '-f', 's16le',
                '-ar', '44100',
                '-ac', '2',
                '-acodec', 'pcm_s16le',
                '-af', 'volume=1.0',
                '-loglevel', 'error',
                '-'
            ]

            print("[DEBUG] _stream_worker: launching ffmpeg:", ffmpeg_cmd)
            # Delay 'playing' emit until we actually receive audio data
            
            # Start ffmpeg process
            with self._state_lock:
                try:
                    self._ffmpeg_process = subprocess.Popen(
                        ffmpeg_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        stdin=subprocess.DEVNULL,
                        bufsize=0
                    )
                    print("[DEBUG] _stream_worker: ffmpeg process started, pid:", self._ffmpeg_process.pid)
                except Exception as e:
                    print("[DEBUG] _stream_worker: failed to start ffmpeg:", e)
                    self._ffmpeg_process = None
                    self._emit('error', None)
                    return

            started_streaming = False
            chunk_size = 4096
            while True:
                with self._state_lock:
                    if self._stop_event.is_set():
                        print("[DEBUG] _stream_worker: stop event set, breaking loop")
                        break
                    proc = self._ffmpeg_process
                if proc is None or proc.poll() is not None:
                    print("[DEBUG] _stream_worker: ffmpeg process ended or missing")
                    print("[DEBUG] ffmpeg poll:", proc.poll() if proc else None)
                    # Try to read stderr if possible
                    try:
                        if proc and proc.stderr:
                            err = proc.stderr.read()
                            print("[DEBUG] ffmpeg stderr:", err.decode(errors='ignore'))
                    except Exception as e:
                        print("[DEBUG] error reading ffmpeg stderr:", e)
                    break

                if proc.stdout is None:
                    print("[DEBUG] _stream_worker: ffmpeg stdout is None")
                    break

                try:
                    chunk = proc.stdout.read(chunk_size)
                except Exception as e:
                    print("[DEBUG] _stream_worker: exception reading ffmpeg stdout:", e)
                    break

                if not chunk:
                    print("[DEBUG] _stream_worker: ffmpeg stdout EOF or empty chunk")
                    break

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
                            print("[DEBUG] _stream_worker: error in audio processing:", e)
                            try:
                                if self._audio_stream is not None and stream_active:
                                    self._audio_stream.write(b'\x00' * n_bytes)
                            except Exception as e2:
                                print("[DEBUG] _stream_worker: error writing silence:", e2)
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
                            print("[DEBUG] _stream_worker: error writing silence (muted):", e)
                        else:
                            # Suppress spam when paused/closed
                            pass

            print("[DEBUG] _stream_worker: cleaning up ffmpeg process")
            with self._state_lock:
                proc = self._ffmpeg_process
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=2.0)
                    print("[DEBUG] _stream_worker: ffmpeg process terminated")
                except Exception as e:
                    print("[DEBUG] _stream_worker: error terminating ffmpeg:", e)
                    try:
                        proc.kill()
                        print("[DEBUG] _stream_worker: ffmpeg process killed")
                    except Exception as e2:
                        print("[DEBUG] _stream_worker: error killing ffmpeg:", e2)

            if not self._stop_requested:
                if not started_streaming:
                    print("[DEBUG] _stream_worker: connection failed before receiving data")
                    self._emit('error', None)
                else:
                    print("[DEBUG] _stream_worker: stream ended naturally")
                    self._emit('ended', None)
            else:
                print("[DEBUG] _stream_worker: stream stopped by request")
                self._emit('stopped', None)

        except Exception as e:
            print("[DEBUG] _stream_worker: outer exception:", e)
            if not self._stop_requested:
                self._emit('error', None)
        finally:
            print("[DEBUG] _stream_worker: final cleanup")
            self._playing = False
            self._current_stream = None
            if self._audio_stream:
                try:
                    if getattr(self._audio_stream, "is_active", lambda: False)():
                        try:
                            self._audio_stream.stop_stream()
                            print("[DEBUG] _stream_worker: audio stream stopped")
                        except Exception as e:
                            print("[DEBUG] _stream_worker: error stopping audio stream:", e)
                    try:
                        self._audio_stream.close()
                        print("[DEBUG] _stream_worker: audio stream closed")
                    except Exception as e:
                        print("[DEBUG] _stream_worker: error closing audio stream:", e)
                except Exception as e:
                    print("[DEBUG] _stream_worker: error in audio stream cleanup:", e)
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
            print("[DEBUG] _stream_worker: exited")
