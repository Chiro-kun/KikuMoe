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
