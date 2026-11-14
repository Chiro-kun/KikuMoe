import threading
import time
from urllib.error import HTTPError

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from core.constants import (
    KEY_BETTERLYRICS_API_KEY,
    KEY_LYRICS_PROVIDER,
    LYRICS_PROVIDER_AUTO,
    LYRICS_PROVIDER_BETTERLYRICS,
    LYRICS_PROVIDER_BETTERLYRICS_FIRST,
    LYRICS_PROVIDER_LRCLIB,
)
from core.lyrics import (
    LyricsProvider,
    parse_lrc,
    parse_ttml_time,
    qrc_to_lrc,
    select_match,
    ttml_to_lrc,
)
from ui.widgets.lyrics_panel import LyricsPanel


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_parse_lrc_multiple_timestamps_and_empty_lines():
    assert parse_lrc("[ar:Artist]\n[00:12.50][00:03.1]Hello\n[00:20.00]") == [
        (3.1, "Hello"),
        (12.5, "Hello"),
        (20.0, ""),
    ]


def test_search_rejects_unrelated_tracks_and_wrong_duration():
    records = [
        {"trackName": "Other", "artistName": "Artist", "duration": 200},
        {"trackName": "Song", "artistName": "Artist", "duration": 300},
        {"trackName": "Song", "artistName": "Artist", "duration": 200, "syncedLyrics": "lrc"},
    ]
    assert select_match(records, "Song", "Artist", 200) is records[2]
    assert select_match(records[:2], "Song", "Artist", 200) is None


def test_provider_cancels_stale_fallback_and_reuses_cached_results(qapp, monkeypatch):
    provider = LyricsProvider()
    calls, results = [], []
    started, release = threading.Event(), threading.Event()

    def request(endpoint, params):
        calls.append((endpoint, params))
        if params["track_name"] == "Song":
            started.set()
            release.wait(2)
        return {"plainLyrics": params["track_name"]}

    monkeypatch.setattr(provider, "_request", request)
    monkeypatch.setattr(
        provider,
        "_request_betterlyrics",
        lambda *_a, **_kw: (_ for _ in ()).throw(
            HTTPError("https://api.betterlyrics.org", 404, "Not found", {}, None)
        ),
    )
    provider.finished.connect(lambda record, status: results.append((record, status)))
    provider.search("Song", "Artist", 200)
    assert started.wait(2)
    provider.search("New", "Artist", 180)
    release.set()
    deadline = time.monotonic() + 3
    while not results and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    assert results == [({"plainLyrics": "New"}, "ok")]
    assert len(calls) == 2
    provider.search("New", "Artist", 180)
    assert results[-1] == ({"plainLyrics": "New"}, "ok")
    assert len(calls) == 2


def test_panel_tracks_active_line_and_supports_plain_lyrics(qapp):
    panel = LyricsPanel()
    panel.show_record({"syncedLyrics": "[00:01.00]One\n[00:02.00]Two"}, "Plain")
    panel.set_position(1.5)
    assert panel.active == 0
    panel.set_position(2.0)
    assert panel.active == 1
    panel.show_record({"plainLyrics": "Just text"}, "Plain")
    assert not panel.lines
    assert panel.labels[0].text() == "Plain"
    assert panel.labels[1].text() == "Just text"
    panel.show_record({"syncedLyrics": "[00:01.00]One"}, "Plain", "Timing unavailable")
    assert not panel.lines
    assert panel.labels[0].text() == "Timing unavailable"
    assert panel.labels[1].text() == "One"
    panel.close()


def test_synced_lyrics_center_and_animate_through_line_changes(qapp):
    panel = LyricsPanel()
    panel.resize(320, 222)
    panel.show()
    assert panel.scroll.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    panel.show_record(
        {"syncedLyrics": "\n".join(f"[00:{n:02}.00]Line {n}" for n in range(1, 9))}, "Plain"
    )
    qapp.processEvents()
    assert panel.labels[0].alignment() & Qt.AlignmentFlag.AlignHCenter
    panel.set_position(1)
    QTest.qWait(450)
    first = panel.labels[0]
    assert first._color.name() == panel._accent
    assert (
        abs(
            first.mapTo(panel.scroll.viewport(), first.rect().center()).y()
            - panel.scroll.viewport().height() // 2
        )
        < 5
    )
    panel.set_position(8)
    QTest.qWait(450)
    last = panel.labels[-1]
    assert last._color.name() == panel._accent
    assert first._color.alpha() == 165
    assert (
        abs(
            last.mapTo(panel.scroll.viewport(), last.rect().center()).y()
            - panel.scroll.viewport().height() // 2
        )
        < 5
    )
    panel.close()


def test_lookup_falls_back_after_404_and_honors_retry_after(qapp, monkeypatch):
    provider = LyricsProvider()
    calls = []

    def request(endpoint, params):
        calls.append(endpoint)
        if endpoint == "get":
            raise HTTPError("https://lrclib.net", 404, "Not found", {}, None)
        return [{"trackName": "Song", "artistName": "Artist", "duration": 200}]

    monkeypatch.setattr(provider, "_request", request)
    record, status, retry = provider._lookup({}, ("Song", "Artist", 200), provider.generation)
    assert calls == ["get", "search"]
    assert status == "ok" and record["trackName"] == "Song" and retry == 0

    def rate_limited(endpoint, params):
        raise HTTPError("https://lrclib.net", 429, "Rate limited", {"Retry-After": "30"}, None)

    monkeypatch.setattr(provider, "_request", rate_limited)
    record, status, retry = provider._lookup({}, ("Song", "Artist", 200), provider.generation)
    assert record is None and status == "error"
    assert retry >= time.monotonic() + 29


def test_lyrics_panel_responsive_scaling_and_recenter(qapp):
    panel = LyricsPanel()
    panel.resize(480, LyricsPanel.BASE_HEIGHT)
    panel.show()
    panel.show_record(
        {"syncedLyrics": "\n".join(f"[00:{n:02}.00]Lyric line {n}" for n in range(1, 10))},
        "Plain",
    )
    panel.set_position(5)
    QTest.qWait(400)

    assert panel._font_px == LyricsPanel.BASE_FONT_PX
    assert panel.height() == LyricsPanel.BASE_HEIGHT
    assert f"font-size: {LyricsPanel.BASE_FONT_PX}px" in panel.labels[0].styleSheet()

    # Scale up to hero / fullscreen proportion
    panel.set_responsive_scale(1.0)
    QTest.qWait(420)
    assert panel._font_px == LyricsPanel.HERO_FONT_PX
    assert panel.height() == LyricsPanel.HERO_HEIGHT
    assert panel.content_layout.spacing() == 13
    assert all(
        f"font-size: {LyricsPanel.HERO_FONT_PX}px" in lbl.styleSheet() for lbl in panel.labels
    )
    active_lbl = panel.labels[panel.active]
    assert (
        abs(
            active_lbl.mapTo(panel.scroll.viewport(), active_lbl.rect().center()).y()
            - panel.scroll.viewport().height() // 2
        )
        < 5
    )

    # New track loaded while scaled must inherit hero font size
    panel.show_record({"plainLyrics": "New track words"}, "Plain")
    assert all(
        f"font-size: {LyricsPanel.HERO_FONT_PX}px" in lbl.styleSheet() for lbl in panel.labels
    )

    # Scale back to compact
    panel.set_responsive_scale(0.0)
    assert panel._font_px == LyricsPanel.BASE_FONT_PX
    assert panel.height() == LyricsPanel.BASE_HEIGHT
    assert panel.content_layout.spacing() == 9
    panel.close()


def _wait_for_lyrics_results(qapp, results, expected_count=1, timeout_s=3.0):
    deadline = time.monotonic() + timeout_s
    while len(results) < expected_count and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)


def test_parse_ttml_time_and_ttml_to_lrc_formats():
    assert parse_ttml_time("00:01:30.500") == pytest.approx(90.5)
    assert parse_ttml_time("1:16.656") == pytest.approx(76.656)
    assert parse_ttml_time("18.086") == pytest.approx(18.086)
    assert parse_ttml_time("2500ms") == pytest.approx(2.5)
    assert parse_ttml_time("bad") is None
    assert parse_ttml_time("") is None

    ttml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<tt xmlns="http://www.w3.org/ns/ttml" xmlns:ttm="http://www.w3.org/ns/ttml#metadata">'
        "<body><div>"
        '<p begin="0.000" end="1.539"><span begin="0.000" end="0.451">I</span> '
        '<span begin="0.451" end="1.539">lo—</span></p>'
        '<p begin="00:01:30.999" end="00:01:35.000">'
        '<span begin="00:01:30.999" end="00:01:32.000">The </span>'
        '<span ttm:role="x-bg"><span begin="00:01:32.000" end="00:01:34.000">(yeah)</span></span>'
        "</p>"
        "</div></body></tt>"
    )
    lrc = ttml_to_lrc(ttml)
    parsed = parse_lrc(lrc)
    assert parsed == [
        (0.0, "I lo—"),
        (91.0, "The (yeah)"),
    ]
    assert ttml_to_lrc("<!DOCTYPE foo><tt><body><p begin='1.0'>Hi</p></body></tt>") == ""


def test_qrc_to_lrc_strips_word_timing_and_decodes_xml_entities():
    qrc_xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        "<QrcInfos>"
        '<QrcHeadInfo SaveTime="306" Version="100"/>'
        '<LyricInfo LyricCount="1">'
        '<Lyric_1 LyricType="1" LyricContent="[ti:Song]\n'
        "[ar:Artist]\n"
        "[offset:0]\n"
        "[5767,324]&quot;Hello&quot; (5767,100)&amp; (5867,100)world(5967,120)\n"
        '[292333,1910]Let (292333,136)it (292469,97)go(292566,202)\n"/>'
        "</LyricInfo></QrcInfos>"
    )
    lrc = qrc_to_lrc(qrc_xml)
    parsed = parse_lrc(lrc)
    assert parsed == [
        (5.77, '"Hello" & world'),
        (292.33, "Let it go"),
    ]


def test_betterlyrics_falls_back_across_endpoints_and_sends_api_key(qapp, monkeypatch):
    provider = LyricsProvider()
    provider.configure(LYRICS_PROVIDER_BETTERLYRICS, betterlyrics_api_key="secret-key")
    bl_calls = []

    def fake_bl_request(endpoint, params):
        bl_calls.append((endpoint, dict(params), provider.betterlyrics_api_key))
        if endpoint == "/getLyrics":
            raise HTTPError("https://api.betterlyrics.org/getLyrics", 401, "Unauthorized", {}, None)
        if endpoint == "/kugou/getLyrics":
            raise HTTPError(
                "https://api.betterlyrics.org/kugou/getLyrics", 404, "Not found", {}, None
            )
        return {
            "lyrics": (
                '<QrcInfos><LyricInfo><Lyric_1 LyricContent="'
                "[12340,1000]Synced (12340,500)line(12840,500)"
                '"/></LyricInfo></QrcInfos>'
            ),
            "provider": "qq",
        }

    monkeypatch.setattr(provider, "_request_betterlyrics", fake_bl_request)
    results = []
    provider.finished.connect(lambda rec, st: results.append((rec, st)))
    provider.search("Idol", "YOASOBI", 213, album="THE BOOK 3")
    _wait_for_lyrics_results(qapp, results)

    assert [c[0] for c in bl_calls] == ["/getLyrics", "/kugou/getLyrics", "/qq/getLyrics"]
    assert bl_calls[0][1] == {"s": "Idol", "a": "YOASOBI", "al": "THE BOOK 3", "d": "213"}
    assert bl_calls[0][2] == "secret-key"
    rec, status = results[0]
    assert status == "ok"
    assert rec["provider"] == "betterlyrics_qq"
    assert parse_lrc(rec["syncedLyrics"]) == [(12.34, "Synced line")]


def test_betterlyrics_api_key_header_forwarded_in_http_request(monkeypatch):
    import io
    import urllib.request as _urllib_request

    captured = {}

    class FakeResp(io.BytesIO):
        headers = {"X-Cache-Status": "HIT"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    def fake_urlopen(req, timeout=8, context=None):
        captured["url"] = req.full_url
        captured["headers"] = {k.lower(): v for k, v in req.header_items()}
        return FakeResp(b'{"ttml": "<tt></tt>"}')

    monkeypatch.setattr(_urllib_request, "urlopen", fake_urlopen)
    provider = LyricsProvider()
    provider.configure(LYRICS_PROVIDER_BETTERLYRICS, betterlyrics_api_key="my-bl-key")
    payload = provider._request_betterlyrics("/getLyrics", {"s": "E85", "a": "Don Toliver"})
    assert payload == {"ttml": "<tt></tt>"}
    assert captured["url"].startswith("https://api.betterlyrics.org/getLyrics?")
    assert captured["headers"].get("x-api-key") == "my-bl-key"


def test_lyrics_cascade_modes_and_isolated_rate_limit(qapp, monkeypatch):
    provider = LyricsProvider()
    results = []
    provider.finished.connect(lambda rec, st: results.append((rec, st)))

    # 1) Auto mode: LRCLIB plain-only triggers Better Lyrics synced lookup
    provider.configure(LYRICS_PROVIDER_AUTO)
    monkeypatch.setattr(provider, "_request", lambda _ep, _p: {"plainLyrics": "Unsynced only"})
    monkeypatch.setattr(
        provider,
        "_request_betterlyrics",
        lambda ep, _p: (
            {"ttml": '<tt><body><p begin="0:02.000">From TTML</p></body></tt>'}
            if ep == "/getLyrics"
            else {}
        ),
    )
    provider.search("Song A", "Artist A", 180)
    _wait_for_lyrics_results(qapp, results, 1)
    assert results[-1][1] == "ok"
    assert results[-1][0]["provider"] == "betterlyrics_ttml"
    assert parse_lrc(results[-1][0]["syncedLyrics"]) == [(2.0, "From TTML")]

    # 2) Auto mode: LRCLIB 429 backoff does not block Better Lyrics
    monkeypatch.setattr(
        provider,
        "_request",
        lambda _ep, _p: (_ for _ in ()).throw(
            HTTPError("https://lrclib.net", 429, "Rate limited", {"Retry-After": "60"}, None)
        ),
    )
    monkeypatch.setattr(
        provider,
        "_request_betterlyrics",
        lambda ep, _p: (
            {"lyrics": "[00:05.00]From Kugou", "provider": "kugou"}
            if ep == "/kugou/getLyrics"
            else (_ for _ in ()).throw(
                HTTPError("https://api.betterlyrics.org", 404, "Not found", {}, None)
            )
        ),
    )
    provider.search("Song B", "Artist B", 190)
    _wait_for_lyrics_results(qapp, results, 2)
    assert results[-1][1] == "ok"
    assert results[-1][0]["provider"] == "betterlyrics_kugou"

    # 3) Better Lyrics first falls back to LRCLIB on Better Lyrics 404s
    called = []
    provider.retry_after = 0.0
    provider.configure(LYRICS_PROVIDER_BETTERLYRICS_FIRST)

    def fake_bl_miss(ep, _p):
        called.append(f"bl:{ep}")
        raise HTTPError("https://api.betterlyrics.org", 404, "Not found", {}, None)

    def fake_lrc_hit(ep, _p):
        called.append(f"lrc:{ep}")
        return {"syncedLyrics": "[00:01.00]From LRCLIB"}

    monkeypatch.setattr(provider, "_request_betterlyrics", fake_bl_miss)
    monkeypatch.setattr(provider, "_request", fake_lrc_hit)
    provider.search("Song C", "Artist C", 200)
    _wait_for_lyrics_results(qapp, results, 3)
    assert called[0].startswith("bl:")
    assert "lrc:get" in called
    assert parse_lrc(results[-1][0]["syncedLyrics"]) == [(1.0, "From LRCLIB")]

    # 4) LRCLIB-only never calls Better Lyrics
    called.clear()
    provider.configure(LYRICS_PROVIDER_LRCLIB)
    provider.search("Song D", "Artist D", 210)
    _wait_for_lyrics_results(qapp, results, 4)
    assert all(c.startswith("lrc:") for c in called)


def test_settings_dialog_and_main_window_sync_lyrics_provider(qapp, monkeypatch, tmp_path):
    from types import SimpleNamespace

    from PyQt6.QtCore import QSettings

    from ui import main_window, settings_dialog

    ini = QSettings(str(tmp_path / "lyrics_settings.ini"), QSettings.Format.IniFormat)
    ini.setValue(KEY_LYRICS_PROVIDER, LYRICS_PROVIDER_BETTERLYRICS_FIRST)
    ini.setValue(KEY_BETTERLYRICS_API_KEY, "initial-key")
    monkeypatch.setattr(settings_dialog, "QSettings", lambda *_a: ini)
    monkeypatch.setattr(
        settings_dialog.SettingsDialog, "_ensure_devices_populated", lambda self: None
    )

    dlg = settings_dialog.SettingsDialog()
    assert dlg.cmb_lyrics_provider.currentData() == LYRICS_PROVIDER_BETTERLYRICS_FIRST
    assert dlg.txt_betterlyrics_api_key.text() == "initial-key"
    assert not dlg.betterlyrics_key_row.isHidden()

    lrclib_idx = dlg.cmb_lyrics_provider.findData(LYRICS_PROVIDER_LRCLIB)
    dlg.cmb_lyrics_provider.setCurrentIndex(lrclib_idx)
    assert dlg.betterlyrics_key_row.isHidden()

    bl_idx = dlg.cmb_lyrics_provider.findData(LYRICS_PROVIDER_BETTERLYRICS)
    dlg.cmb_lyrics_provider.setCurrentIndex(bl_idx)
    assert not dlg.betterlyrics_key_row.isHidden()
    dlg.txt_betterlyrics_api_key.setText("  updated-key  ")
    dlg._save_settings()
    dlg.close()

    assert ini.value(KEY_LYRICS_PROVIDER) == LYRICS_PROVIDER_BETTERLYRICS
    assert ini.value(KEY_BETTERLYRICS_API_KEY) == "updated-key"

    lp = LyricsProvider()
    refreshed = []
    win = SimpleNamespace(
        settings=ini,
        lyrics_provider=lp,
        lyrics_button=SimpleNamespace(isChecked=lambda: True),
        _lyrics_track=("Old", "Artist", 100, ""),
        _refresh_lyrics=lambda force=False: refreshed.append(force),
    )
    main_window.ListenMoePlayer._sync_lyrics_settings(win)
    assert lp.provider_mode == LYRICS_PROVIDER_BETTERLYRICS
    assert lp.betterlyrics_api_key == "updated-key"
    assert refreshed == [True]


def test_betterlyrics_omits_album_without_api_key_and_caches_401_misses(qapp, monkeypatch):
    provider = LyricsProvider()
    provider.configure(LYRICS_PROVIDER_BETTERLYRICS, betterlyrics_api_key="")
    calls = []

    def fake_bl_request(endpoint, params):
        calls.append((endpoint, dict(params)))
        raise HTTPError(
            f"https://api.betterlyrics.org{endpoint}", 401, "API key required", {}, None
        )

    monkeypatch.setattr(provider, "_request_betterlyrics", fake_bl_request)
    results = []
    provider.finished.connect(lambda rec, st: results.append((rec, st)))

    provider.search("Day 1", "Red Velvet", 206, album="The Red")
    _wait_for_lyrics_results(qapp, results, 1)
    assert results[-1] == (None, "missing")
    assert all("al" not in params for _, params in calls)
    assert len(calls) == 3

    # Repeated lookup should hit the 401 negative cache instead of burning rate-limit tokens
    calls.clear()
    provider.search("Day 1", "Red Velvet", 206, album="The Red")
    _wait_for_lyrics_results(qapp, results, 2)
    assert results[-1] == (None, "missing")
    assert calls == []
