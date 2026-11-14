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


def test_local_pause_suspends_decoding_preserves_time_and_resumes(monkeypatch, tmp_path):
    import subprocess as _subprocess
    import time as _time

    audio_file = tmp_path / "sample.mp3"
    audio_file.write_bytes(b"ID3test")

    monkeypatch.setattr(PlayerFFmpeg, "_init_audio", lambda self: None)
    events = []
    playing_ev = threading.Event()
    paused_ev = threading.Event()
    ended_ev = threading.Event()

    def on_event(code, value):
        events.append(code)
        if code == "playing":
            playing_ev.set()
        elif code == "paused":
            paused_ev.set()
        elif code == "ended":
            ended_ev.set()

    player = PlayerFFmpeg(on_event=on_event)
    player._ready = True
    player._volume = 1.0
    player._pyaudio_instance = object()
    player._ffmpeg_bin = str(tmp_path / "ffmpeg.exe")

    write_stats = {"nonzero": 0, "silence": 0}

    class Stream:
        def is_active(self):
            return True

        def start_stream(self):
            pass

        def write(self, data, **kwargs):
            if any(data):
                write_stats["nonzero"] += 1
            else:
                write_stats["silence"] += 1
            _time.sleep(0.015)

        def stop_stream(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(PlayerFFmpeg, "_open_pyaudio_stream", lambda self, _idx: (Stream(), 48000))
    monkeypatch.setattr(
        "audio.player_ffmpeg.subprocess.run",
        lambda *a, **kw: type("R", (), {"returncode": 0})(),
    )

    total_chunks = 18
    read_state = {"count": 0}

    class FakeStdout:
        def __init__(self, proc):
            self._proc = proc

        def read(self, n):
            if self._proc.killed.is_set():
                return b""
            if read_state["count"] < total_chunks:
                read_state["count"] += 1
                return b"\x01\x00" * (n // 2)
            return b""

    class FakeProc:
        pid = 4242

        def __init__(self):
            self.killed = threading.Event()
            self.stdout = FakeStdout(self)
            self.stderr = type("Err", (), {"read": lambda _s: b""})()

        def poll(self):
            if self.killed.is_set():
                return -9
            return 0 if read_state["count"] >= total_chunks else None

        def kill(self):
            self.killed.set()

        def terminate(self):
            self.killed.set()

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(_subprocess, "Popen", lambda *a, **kw: FakeProc())

    try:
        assert player.play_url(str(audio_file)) is True
        assert playing_ev.wait(timeout=2.0)
        _time.sleep(0.05)

        player.pause_toggle()
        assert paused_ev.wait(timeout=2.0)
        # Allow any single in-flight PCM chunk write to settle before sampling paused position
        _time.sleep(0.05)

        reads_at_pause = read_state["count"]
        nonzero_at_pause = write_stats["nonzero"]
        silence_at_pause = write_stats["silence"]
        t_paused_1 = player.get_time()
        assert t_paused_1 is not None and t_paused_1 > 0.0

        # Wait long enough that un-suspended decoding would finish all remaining chunks
        _time.sleep(0.35)

        t_paused_2 = player.get_time()
        assert player.is_playing() is True
        assert player.is_paused() is True
        assert "ended" not in events
        assert "error" not in events
        assert t_paused_2 == t_paused_1
        assert read_state["count"] <= reads_at_pause + 1
        assert read_state["count"] < total_chunks
        assert write_stats["nonzero"] == nonzero_at_pause
        assert write_stats["silence"] > silence_at_pause

        # Resume and let remaining chunks finish naturally to EOF
        playing_ev.clear()
        player.pause_toggle()
        assert playing_ev.wait(timeout=2.0)
        assert ended_ev.wait(timeout=3.0)

        assert read_state["count"] == total_chunks
        assert player.is_playing() is False
        assert player.is_paused() is False
        assert player.get_time() == 0.0
    finally:
        player.stop()


def test_stop_clears_paused_state_on_ffmpeg_player(monkeypatch, tmp_path):
    import subprocess as _subprocess

    audio_file = tmp_path / "sample.mp3"
    audio_file.write_bytes(b"ID3test")

    monkeypatch.setattr(PlayerFFmpeg, "_init_audio", lambda self: None)
    playing_ev = threading.Event()
    paused_ev = threading.Event()
    player = PlayerFFmpeg(
        on_event=lambda code, _v: (
            playing_ev.set() if code == "playing" else paused_ev.set() if code == "paused" else None
        )
    )
    player._ready = True
    player._pyaudio_instance = object()
    player._ffmpeg_bin = str(tmp_path / "ffmpeg.exe")

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

    monkeypatch.setattr(PlayerFFmpeg, "_open_pyaudio_stream", lambda self, _idx: (Stream(), 48000))
    monkeypatch.setattr(
        "audio.player_ffmpeg.subprocess.run",
        lambda *a, **kw: type("R", (), {"returncode": 0})(),
    )

    class FakeProc:
        pid = 4343

        def __init__(self):
            self.killed = threading.Event()
            self._reads = 0
            self.stdout = self
            self.stderr = type("Err", (), {"read": lambda _s: b""})()

        def read(self, n):
            if self.killed.is_set():
                return b""
            if self._reads < 8:
                self._reads += 1
                return b"\x01\x00" * (n // 2)
            self.killed.wait(timeout=2.0)
            return b""

        def poll(self):
            return -9 if self.killed.is_set() else None

        def kill(self):
            self.killed.set()

        def terminate(self):
            self.killed.set()

        def wait(self, timeout=None):
            return -9

    monkeypatch.setattr(_subprocess, "Popen", lambda *a, **kw: FakeProc())

    try:
        assert player.play_url(str(audio_file)) is True
        assert playing_ev.wait(timeout=2.0)
        player.pause_toggle()
        assert paused_ev.wait(timeout=2.0)
        assert player.is_paused() is True
    finally:
        player.stop()

    assert player.is_playing() is False
    assert player.is_paused() is False


def test_vlc_is_paused_reports_paused_state(monkeypatch):
    import types

    from audio.player_vlc import PlayerVLC

    class FakeState:
        Opening = 1
        Buffering = 2
        Playing = 3
        Paused = 4
        Stopped = 5

    class FakeEventType:
        MediaPlayerPlaying = 1
        MediaPlayerPaused = 2
        MediaPlayerStopped = 3
        MediaPlayerEncounteredError = 4
        MediaPlayerBuffering = 5
        MediaPlayerOpening = 6
        MediaPlayerEndReached = 7

    class FakeEventManager:
        def event_attach(self, *_a):
            pass

        def event_detach(self, *_a):
            pass

    class FakeMediaPlayer:
        def __init__(self):
            self._state = FakeState.Stopped

        def event_manager(self):
            return FakeEventManager()

        def get_state(self):
            return self._state

        def audio_set_volume(self, _v):
            pass

        def audio_set_mute(self, _m):
            pass

    class FakeInstance:
        def media_player_new(self):
            return FakeMediaPlayer()

    fake_vlc = types.SimpleNamespace(
        Instance=lambda _opts: FakeInstance(),
        EventType=FakeEventType,
        State=FakeState,
    )
    monkeypatch.setattr("audio.player_vlc.vlc", fake_vlc)
    monkeypatch.setattr("audio.player_vlc._found_libvlc", "/usr/lib/libvlc.so")

    p = PlayerVLC()
    assert p.is_paused() is False
    p.player._state = FakeState.Playing
    assert p.is_playing() is True
    assert p.is_paused() is False
    p.player._state = FakeState.Paused
    assert p.is_playing() is False
    assert p.is_paused() is True
