"""Exercise the MPRIS service through an isolated real session bus on Linux."""

import os
import shutil
import subprocess
import sys
import textwrap

import pytest


@pytest.mark.skipif(
    not sys.platform.startswith("linux") or shutil.which("dbus-run-session") is None,
    reason="requires a Linux D-Bus session",
)
def test_mpris_session_bus_roundtrip():
    script = textwrap.dedent(
        """
        import asyncio
        import logging
        from PyQt6.QtCore import QCoreApplication
        from dbus_next import Message, MessageType, Variant
        from dbus_next.aio import MessageBus
        from core.media_state import MediaState
        from core.mpris import MprisBridge, OBJECT_PATH

        app = QCoreApplication([])
        bridge = MprisBridge(logging.getLogger('test.mpris'))
        events, volumes = [], []
        bridge.command.connect(events.append)
        bridge.volume.connect(volumes.append)
        bridge.update(MediaState(status='Playing', title='Song', artist='Artist',
                                 station='Radio', track_id='/me/chiro/kikumoe/track/t1',
                                 duration_us=120000000, position_us=10000000, volume=0.5))

        async def run():
            bus = await MessageBus().connect()
            name = 'org.mpris.MediaPlayer2.kikumoe'
            introspection = None
            for _ in range(100):
                try:
                    introspection = await bus.introspect(name, OBJECT_PATH)
                    break
                except Exception:
                    await asyncio.sleep(0.05)
            assert introspection is not None, 'MPRIS service did not register'
            proxy = bus.get_proxy_object(name, OBJECT_PATH, introspection)
            props = proxy.get_interface('org.freedesktop.DBus.Properties')
            player = proxy.get_interface('org.mpris.MediaPlayer2.Player')
            iface = 'org.mpris.MediaPlayer2.Player'
            assert (await props.call_get(iface, 'PlaybackStatus')).value == 'Playing'
            metadata = (await props.call_get(iface, 'Metadata')).value
            assert metadata['xesam:title'].value == 'Song'
            assert metadata['mpris:length'].value == 120000000
            assert (await props.call_get(iface, 'CanSeek')).value is False
            properties = await props.call_get_all(iface)
            assert 'Shuffle' not in properties
            assert properties['CanControl'].value is True
            changes = []
            props.on_properties_changed(
                lambda interface, values, invalid: changes.append((interface, values)))
            # dbus-next registers the signal match asynchronously. A later reply
            # from the same connection ensures the bus has processed AddMatch.
            reply = await bus.call(Message(destination='org.freedesktop.DBus',
                                           path='/org/freedesktop/DBus',
                                           interface='org.freedesktop.DBus',
                                           member='GetId'))
            assert reply.message_type == MessageType.METHOD_RETURN
            bridge.update(MediaState(status='Paused', title='New Song',
                                     track_id='/me/chiro/kikumoe/track/t2'))
            for _ in range(100):
                QCoreApplication.processEvents()
                if any('PlaybackStatus' in values and 'Metadata' in values
                       for _, values in changes):
                    break
                await asyncio.sleep(0.05)
            assert any('PlaybackStatus' in values and 'Metadata' in values
                       for _, values in changes), f'Unexpected changes: {changes!r}'
            await player.call_play_pause()
            await props.call_set(iface, 'Volume', Variant('d', 0.7))
            for _ in range(100):
                QCoreApplication.processEvents()
                if events and volumes:
                    break
                await asyncio.sleep(0.05)
            assert events == ['toggle']
            assert volumes == [0.7]
            bridge.stop()
            bus.disconnect()

        asyncio.run(run())
        """
    )
    result = subprocess.run(
        ["dbus-run-session", "--", sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=20,
        env=os.environ.copy(),
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
