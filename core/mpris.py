"""MPRIS 2 service for Linux desktop media controls."""

# D-Bus signatures are string annotations interpreted by dbus-next at runtime.
# ruff: noqa: F821, F722
# mypy: disable-error-code="name-defined,no-redef,valid-type"
import asyncio
import os
import threading

from dbus_next import BusType, NameFlag, RequestNameReply, Variant
from dbus_next.aio import MessageBus
from dbus_next.constants import PropertyAccess
from dbus_next.service import ServiceInterface, dbus_property, method, signal
from PyQt6.QtCore import QObject, pyqtSignal

from core.media_state import MediaState

OBJECT_PATH = "/org/mpris/MediaPlayer2"


class MprisRoot(ServiceInterface):
    def __init__(self, bridge):
        super().__init__("org.mpris.MediaPlayer2")
        self.bridge = bridge

    @method()
    def Raise(self):
        self.bridge.command.emit("raise")

    @method()
    def Quit(self):
        pass

    @dbus_property(access=PropertyAccess.READ)
    def CanQuit(self) -> "b":  # type: ignore[valid-type]
        return False

    @dbus_property(access=PropertyAccess.READ)
    def CanRaise(self) -> "b":  # type: ignore[valid-type]
        return True

    @dbus_property(access=PropertyAccess.READ)
    def HasTrackList(self) -> "b":  # type: ignore[valid-type]
        return False

    @dbus_property(access=PropertyAccess.READ)
    def Identity(self) -> "s":  # type: ignore[valid-type]
        return "KikuMoe"

    @dbus_property(access=PropertyAccess.READ)
    def DesktopEntry(self) -> "s":  # type: ignore[valid-type]
        return "me.chiro.kikumoe"

    @dbus_property(access=PropertyAccess.READ)
    def SupportedUriSchemes(self) -> "as":  # type: ignore[valid-type]
        return []

    @dbus_property(access=PropertyAccess.READ)
    def SupportedMimeTypes(self) -> "as":  # type: ignore[valid-type]
        return []


class MprisPlayer(ServiceInterface):
    def __init__(self, bridge):
        super().__init__("org.mpris.MediaPlayer2.Player")
        self.bridge = bridge
        self.state = MediaState()

    @method()
    def Next(self):
        pass

    @method()
    def Previous(self):
        pass

    @method()
    def Pause(self):
        self.bridge.command.emit("pause")

    @method()
    def PlayPause(self):
        self.bridge.command.emit("toggle")

    @method()
    def Stop(self):
        self.bridge.command.emit("stop")

    @method()
    def Play(self):
        self.bridge.command.emit("play")

    @method()
    def Seek(self, offset: "x"):  # type: ignore[valid-type]
        pass

    @method()
    def SetPosition(self, track_id: "o", position: "x"):  # type: ignore[valid-type]
        pass

    @method()
    def OpenUri(self, uri: "s"):  # type: ignore[valid-type]
        pass

    @signal()
    def Seeked(self, position: "x") -> "x":  # type: ignore[valid-type]
        return position

    @dbus_property(access=PropertyAccess.READ)
    def PlaybackStatus(self) -> "s":  # type: ignore[valid-type]
        return self.state.status

    @dbus_property()
    def LoopStatus(self) -> "s":  # type: ignore[valid-type]
        return "None"

    @LoopStatus.setter
    def LoopStatus(self, value: "s"):  # type: ignore[valid-type,no-redef]
        pass

    @dbus_property()
    def Rate(self) -> "d":  # type: ignore[valid-type]
        return 1.0

    @Rate.setter
    def Rate(self, value: "d"):  # type: ignore[valid-type,no-redef]
        pass

    # Shuffle is intentionally omitted while only radio streams are supported.
    # This follows Chromium's compatibility behavior despite MPRIS listing it.
    # Add it when local playlist playback implements shuffle.

    @dbus_property(access=PropertyAccess.READ)
    def Metadata(self) -> "a{sv}":  # type: ignore[valid-type]
        state = self.state
        result = {"mpris:trackid": Variant("o", state.track_id)}
        if state.title:
            result["xesam:title"] = Variant("s", state.title)
        if state.artist:
            result["xesam:artist"] = Variant("as", [state.artist])
        if state.station:
            result["xesam:album"] = Variant("s", state.station)
        if state.cover_url:
            result["mpris:artUrl"] = Variant("s", state.cover_url)
        if state.duration_us > 0:
            result["mpris:length"] = Variant("x", state.duration_us)
        return result

    @dbus_property()
    def Volume(self) -> "d":  # type: ignore[valid-type]
        return self.state.volume

    @Volume.setter
    def Volume(self, value: "d"):  # type: ignore[valid-type,no-redef]
        self.bridge.volume.emit(max(0.0, min(1.0, value)))

    @dbus_property(access=PropertyAccess.READ)
    def Position(self) -> "x":  # type: ignore[valid-type]
        return self.state.position_us

    @dbus_property(access=PropertyAccess.READ)
    def MinimumRate(self) -> "d":  # type: ignore[valid-type]
        return 1.0

    @dbus_property(access=PropertyAccess.READ)
    def MaximumRate(self) -> "d":  # type: ignore[valid-type]
        return 1.0

    @dbus_property(access=PropertyAccess.READ)
    def CanGoNext(self) -> "b":  # type: ignore[valid-type]
        return False

    @dbus_property(access=PropertyAccess.READ)
    def CanGoPrevious(self) -> "b":  # type: ignore[valid-type]
        return False

    @dbus_property(access=PropertyAccess.READ)
    def CanPlay(self) -> "b":  # type: ignore[valid-type]
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanPause(self) -> "b":  # type: ignore[valid-type]
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanSeek(self) -> "b":  # type: ignore[valid-type]
        return False

    @dbus_property(access=PropertyAccess.READ)
    def CanControl(self) -> "b":  # type: ignore[valid-type]
        return True

    def update_state(self, state):
        previous = self.state
        self.state = state
        changed = {}
        if previous.status != state.status:
            changed["PlaybackStatus"] = state.status
        if (
            previous.title,
            previous.artist,
            previous.station,
            previous.cover_url,
            previous.track_id,
            previous.duration_us,
        ) != (
            state.title,
            state.artist,
            state.station,
            state.cover_url,
            state.track_id,
            state.duration_us,
        ):
            changed["Metadata"] = self.Metadata
        if previous.volume != state.volume:
            changed["Volume"] = state.volume
        if changed:
            self.emit_properties_changed(changed)
        if (
            previous.status == "Paused"
            and state.status == "Playing"
            and (
                previous.track_id == state.track_id
                and abs(previous.position_us - state.position_us) > 1000000
            )
        ):
            self.Seeked(state.position_us)


class MprisBridge(QObject):
    command = pyqtSignal(str)
    volume = pyqtSignal(float)

    def __init__(self, logger, parent=None):
        super().__init__(parent)
        self.log = logger
        self._state = MediaState()
        self._lock = threading.Lock()
        self._loop = None
        self._async_stop = None
        self._player = None
        self._stopping = threading.Event()
        self._thread = threading.Thread(target=self._run, name="KikuMoe-MPRIS", daemon=True)
        self._thread.start()

    def update(self, state):
        with self._lock:
            self._state = state
        loop = self._loop
        if loop is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(self._apply_state, state)
            except RuntimeError:
                pass

    def _apply_state(self, state):
        if self._player is not None:
            self._player.update_state(state)

    def _run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._async_stop = asyncio.Event()
        try:
            loop.run_until_complete(self._serve())
        finally:
            self._async_stop = None
            self._loop = None
            loop.close()

    async def _serve(self):
        while not self._stopping.is_set():
            bus = None
            try:
                bus = await MessageBus(bus_type=BusType.SESSION).connect()
                root = MprisRoot(self)
                player = MprisPlayer(self)
                with self._lock:
                    player.state = self._state
                bus.export(OBJECT_PATH, root)
                bus.export(OBJECT_PATH, player)
                name = "org.mpris.MediaPlayer2.kikumoe"
                reply = await bus.request_name(name, NameFlag.DO_NOT_QUEUE)
                if reply != RequestNameReply.PRIMARY_OWNER:
                    reply = await bus.request_name(
                        f"{name}.instance{os.getpid()}", NameFlag.DO_NOT_QUEUE
                    )
                    if reply != RequestNameReply.PRIMARY_OWNER:
                        raise RuntimeError("Could not register an MPRIS bus name")
                self._player = player
                with self._lock:
                    player.update_state(self._state)
                self.log.info("[MPRIS] Media controls connected")
                while bus.connected and not self._stopping.is_set():
                    try:
                        await asyncio.wait_for(self._async_stop.wait(), timeout=0.5)
                    except asyncio.TimeoutError:
                        pass
            except Exception as exc:
                if not self._stopping.is_set():
                    self.log.debug("[MPRIS] Session bus unavailable: %s", exc)
            finally:
                self._player = None
                if bus is not None:
                    bus.disconnect()
            if not self._stopping.is_set():
                try:
                    await asyncio.wait_for(self._async_stop.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass

    def stop(self):
        self._stopping.set()
        loop, event = self._loop, self._async_stop
        if loop is not None and event is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(event.set)
            except RuntimeError:
                pass
        if self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=1)
