import threading

from audio.player_ffmpeg import PlayerFFmpeg


def test_rapid_pause_does_not_stop_stream_during_write(monkeypatch):
    monkeypatch.setattr(PlayerFFmpeg, "_init_audio", lambda self: None)
    events = []
    player = PlayerFFmpeg(on_event=lambda code, value: events.append(code))
    player._ready = True
    player._playing = True
    player._volume = 1.0
    write_started = threading.Event()
    release_write = threading.Event()

    class Stream:
        def __init__(self):
            self.writes = []
            self.operations = []

        def is_active(self):
            return True

        def write(self, data, **kwargs):
            self.writes.append(data)
            if len(self.writes) == 1:
                write_started.set()
                assert release_write.wait(2)

        def stop_stream(self):
            self.operations.append("stop")

        def start_stream(self):
            self.operations.append("start")

    stream = Stream()
    player._audio_stream = stream
    data = b"\x01\x00" * 128
    worker = threading.Thread(target=player._write_audio_chunk, args=(data,))
    worker.start()
    try:
        assert write_started.wait(2)
        player.pause_toggle()
        assert player.is_paused()
        player.pause_toggle()
        assert not player.is_paused()
        player.pause_toggle()
        assert player.is_paused()
        assert stream.operations == []
    finally:
        release_write.set()
        worker.join(timeout=2)
    assert not worker.is_alive()
    player._write_audio_chunk(data)
    assert stream.writes[-1] == bytes(len(data))
    player.pause_toggle()
    player._write_audio_chunk(data)
    assert stream.writes[-1] == data
    assert stream.operations == []
    assert events == ["paused", "playing", "paused", "playing"]


def test_seek_restarts_ffmpeg_without_reopening_audio_or_emitting_stopped(monkeypatch, tmp_path):
    import subprocess as _subprocess

    audio_file = tmp_path / "sample.mp3"
    audio_file.write_bytes(b"ID3test")

    monkeypatch.setattr(PlayerFFmpeg, "_init_audio", lambda self: None)
    events = []
    player = PlayerFFmpeg(on_event=lambda code, value: events.append(code))
    player._ready = True
    player._volume = 1.0
    player._pyaudio_instance = object()
    player._ffmpeg_bin = str(tmp_path / "ffmpeg.exe")

    open_calls = []
    check_calls = []

    class Stream:
        def is_active(self):
            return True

        def start_stream(self):
            pass

        def write(self, data, **kwargs):
            pass

        def stop_stream(self):
            pass

        def close(self):
            pass

    def fake_open(self, device_idx):
        open_calls.append(device_idx)
        return Stream(), 48000

    monkeypatch.setattr(PlayerFFmpeg, "_open_pyaudio_stream", fake_open)
    monkeypatch.setattr(
        "audio.player_ffmpeg.subprocess.run",
        lambda *a, **kw: check_calls.append(a[0]) or type("R", (), {"returncode": 0})(),
    )

    spawned_cmds = []
    first_playing = threading.Event()
    second_started = threading.Event()
    second_wrote = threading.Event()

    class FakeStdout:
        def __init__(self, proc):
            self._proc = proc
            self._count = 0

        def read(self, n):
            if self._proc.killed.is_set():
                return b""
            if self._proc.idx == 0:
                if self._count < 8:
                    self._count += 1
                    return b"\x01\x00" * (n // 2)
                first_playing.set()
                self._proc.killed.wait(timeout=3.0)
                return b""
            if self._count < 4:
                self._count += 1
                if self._count == 3:
                    second_wrote.set()
                return b"\x02\x00" * (n // 2)
            second_started.wait(timeout=3.0)
            return b""

    class FakeProc:
        _next_pid = 1000

        def __init__(self, idx, cmd):
            FakeProc._next_pid += 1
            self.pid = FakeProc._next_pid
            self.idx = idx
            self.cmd = cmd
            self.killed = threading.Event()
            self.stdout = FakeStdout(self)
            self.stderr = type("Err", (), {"read": lambda _s: b""})()

        def poll(self):
            return -9 if self.killed.is_set() else None

        def kill(self):
            self.killed.set()

        def terminate(self):
            self.killed.set()

        def wait(self, timeout=None):
            return -9

    def fake_popen(cmd, **kwargs):
        idx = len(spawned_cmds)
        spawned_cmds.append(list(cmd))
        return FakeProc(idx, cmd)

    monkeypatch.setattr(_subprocess, "Popen", fake_popen)

    try:
        assert player._check_ffmpeg() is True
        assert player._check_ffmpeg() is True
        assert len(check_calls) == 1  # cached after first verification

        assert player.play_url(str(audio_file)) is True
        assert first_playing.wait(timeout=3.0)

        assert player.seek(60.0) is True
        assert second_wrote.wait(timeout=3.0)

        assert player.get_time() >= 60.0
        assert len(open_calls) == 1
        assert events == ["opening", "playing"]
        assert len(spawned_cmds) >= 2
        assert "-ss" in spawned_cmds[1]
        ss_idx = spawned_cmds[1].index("-ss")
        assert spawned_cmds[1][ss_idx + 1] == "60.000"
        assert ss_idx < spawned_cmds[1].index("-i")
    finally:
        second_started.set()
        player.stop()


def test_pause_during_stream_start_is_retained(monkeypatch):
    monkeypatch.setattr(PlayerFFmpeg, "_init_audio", lambda self: None)
    player = PlayerFFmpeg()
    player._ready = True
    player._playing = True
    assert player._audio_stream is None
    player.pause_toggle()
    assert player.is_paused()
    player.pause_toggle()
    assert not player.is_paused()
