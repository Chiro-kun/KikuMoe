"""Unit tests for core/local_metadata.py."""

from __future__ import annotations

import struct
from pathlib import Path

from core.local_metadata import LocalTrackInfo, extract_track_metadata


def test_track_info_fallback_names():
    info = LocalTrackInfo(file_path="C:/Music/LiSA - Gurenge.mp3")
    assert info.display_title() == "Gurenge"
    assert info.display_artist() == "LiSA"

    info2 = LocalTrackInfo(file_path="C:/Music/SoloSong.flac")
    assert info2.display_title() == "SoloSong"
    assert info2.display_artist() == "Unknown Artist"


def test_mp3_id3v23_parsing(tmp_path: Path):
    mp3_file = tmp_path / "test.mp3"

    # Construct ID3v2.3 tag:
    # Header: "ID3", ver 3, flags 0, synchsafe size
    # Frame 1: TIT2 (Title)
    title_text = b"Crossing Field"
    tit2_frame = b"TIT2" + struct.pack(">IH", len(title_text) + 1, 0) + b"\x03" + title_text

    # Frame 2: TPE1 (Artist)
    artist_text = b"LiSA"
    tpe1_frame = b"TPE1" + struct.pack(">IH", len(artist_text) + 1, 0) + b"\x03" + artist_text

    # Frame 3: TLEN (Duration ms)
    tlen_text = b"249000"
    tlen_frame = b"TLEN" + struct.pack(">IH", len(tlen_text) + 1, 0) + b"\x03" + tlen_text

    # Frame 4: APIC (Cover picture)
    fake_png = b"\x89PNG\r\n\x1a\nfakeimagecontent"
    apic_payload = b"\x00" + b"image/png\x00" + b"\x03" + b"Cover\x00" + fake_png
    apic_frame = b"APIC" + struct.pack(">IH", len(apic_payload), 0) + apic_payload

    # Frame 5: USLT (Lyrics)
    lyrics_text = b"Guren no hana yo sakihokore"
    uslt_payload = b"\x03" + b"eng" + b"Desc\x00" + lyrics_text
    uslt_frame = b"USLT" + struct.pack(">IH", len(uslt_payload), 0) + uslt_payload

    tag_body = tit2_frame + tpe1_frame + tlen_frame + apic_frame + uslt_frame
    tag_size = len(tag_body)

    # Synchsafe tag size (7 bits per byte)
    s0 = (tag_size >> 21) & 0x7F
    s1 = (tag_size >> 14) & 0x7F
    s2 = (tag_size >> 7) & 0x7F
    s3 = tag_size & 0x7F
    id3_header = b"ID3\x03\x00\x00" + bytes([s0, s1, s2, s3])

    mp3_file.write_bytes(id3_header + tag_body + b"\x00" * 2048)

    info = extract_track_metadata(str(mp3_file))
    assert info.title == "Crossing Field"
    assert info.artist == "LiSA"
    assert info.duration_seconds == 249.0
    assert info.cover_bytes == fake_png
    assert info.cover_mime == "image/png"
    assert info.lyrics == "Guren no hana yo sakihokore"
    assert not info.is_synced_lyrics


def test_sidecar_lrc_discovery(tmp_path: Path):
    audio = tmp_path / "song.flac"
    audio.write_bytes(b"fLaC" + b"\x00" * 100)

    lrc_file = tmp_path / "song.lrc"
    lrc_content = (
        "[00:12.50] Dareka no tame ni tsuyoku nareru nara\n[00:18.20] Arigatou kanashimi yo"
    )
    lrc_file.write_text(lrc_content, encoding="utf-8")

    info = extract_track_metadata(str(audio))
    assert info.lyrics == lrc_content
    assert info.is_synced_lyrics is True


def test_flac_metadata_and_streaminfo(tmp_path: Path):
    flac_file = tmp_path / "track.flac"

    # Block 0: STREAMINFO (34 bytes)
    # 10 bytes min/max block/frame size
    # 8 bytes: sample_rate (20b), channels (3b), bits (5b), total_samples (36b)
    # sample_rate = 48000, channels = 2, bits = 16, total_samples = 480000 (10 sec)
    # Pack: val = (48000 << 44) | (1 << 41) | (15 << 36) | (480000)
    sample_rate = 48000
    total_samples = 480000  # 10.0 seconds
    streaminfo_val = (sample_rate << 44) | (1 << 41) | (15 << 36) | total_samples
    streaminfo_data = (
        b"\x10\x00\x10\x00\x00\x00\x00\x00\x00\x00"
        + struct.pack(">Q", streaminfo_val)
        + b"\x00" * 16
    )
    block0 = bytes([0x00, 0x00, 0x00, len(streaminfo_data)]) + streaminfo_data

    # Block 4: VORBIS_COMMENT
    comments = ["TITLE=Homura", "ARTIST=LiSA", "ALBUM=Demon Slayer Movie"]
    vendor = b"reference libFLAC"
    vc_body = struct.pack("<I", len(vendor)) + vendor
    vc_body += struct.pack("<I", len(comments))
    for c in comments:
        c_bytes = c.encode("utf-8")
        vc_body += struct.pack("<I", len(c_bytes)) + c_bytes

    block4 = bytes([0x84, 0x00, 0x00, len(vc_body)]) + vc_body  # 0x84 = last block + type 4

    flac_file.write_bytes(b"fLaC" + block0 + block4)

    info = extract_track_metadata(str(flac_file))
    assert info.title == "Homura"
    assert info.artist == "LiSA"
    assert info.album == "Demon Slayer Movie"
    assert info.duration_seconds == 10.0


def test_wav_metadata_and_duration(tmp_path: Path):
    wav_file = tmp_path / "sound.wav"

    # 44-byte standard PCM stereo 44100Hz 16-bit
    channels = 2
    sample_rate = 44100
    bits = 16
    byte_rate = sample_rate * channels * (bits // 8)  # 176400 bytes/sec
    data_size = 176400 * 5  # exactly 5 seconds

    fmt_chunk = struct.pack(
        "<4sIHHIIHH",
        b"fmt ",
        16,
        1,  # PCM
        channels,
        sample_rate,
        byte_rate,
        channels * (bits // 8),
        bits,
    )
    data_chunk = struct.pack("<4sI", b"data", data_size) + b"\x00" * 100

    riff_header = struct.pack("<4sI4s", b"RIFF", 4 + len(fmt_chunk) + len(data_chunk), b"WAVE")
    wav_file.write_bytes(riff_header + fmt_chunk + data_chunk)

    info = extract_track_metadata(str(wav_file))
    assert info.duration_seconds == 5.0


def test_m4a_metadata(tmp_path: Path):
    m4a_file = tmp_path / "track.m4a"

    # moov atom with mvhd (timescale=1000, duration=15000 -> 15.0s)
    # and udta.meta.ilst with ©nam and ©ART
    mvhd_payload = b"\x00" * 12 + struct.pack(">II", 1000, 15000)
    mvhd_atom = struct.pack(">I4s", len(mvhd_payload) + 8, b"mvhd") + mvhd_payload

    # ilst tags
    def _make_tag(name: bytes, text: str) -> bytes:
        encoded = text.encode("utf-8")
        data_atom = (
            struct.pack(">I4s", len(encoded) + 16, b"data")
            + b"\x00\x00\x00\x01\x00\x00\x00\x00"
            + encoded
        )
        return struct.pack(">I4s", len(data_atom) + 8, name) + data_atom

    ilst_payload = _make_tag(b"\xa9nam", "Unlasting") + _make_tag(b"\xa9ART", "LiSA")
    ilst_atom = struct.pack(">I4s", len(ilst_payload) + 8, b"ilst") + ilst_payload

    meta_payload = b"\x00\x00\x00\x00" + ilst_atom
    meta_atom = struct.pack(">I4s", len(meta_payload) + 8, b"meta") + meta_payload

    udta_payload = meta_atom
    udta_atom = struct.pack(">I4s", len(udta_payload) + 8, b"udta") + udta_payload

    moov_payload = mvhd_atom + udta_atom
    moov_atom = struct.pack(">I4s", len(moov_payload) + 8, b"moov") + moov_payload

    m4a_file.write_bytes(moov_atom)

    info = extract_track_metadata(str(m4a_file))
    assert info.title == "Unlasting"
    assert info.artist == "LiSA"
    assert info.duration_seconds == 15.0


def test_ogg_metadata(tmp_path: Path):
    ogg_file = tmp_path / "audio.ogg"

    # Vorbis comments
    comments = ["TITLE=Akeboshi", "ARTIST=LiSA"]
    vendor = b"Xiph.Org libVorbis"
    vc_body = struct.pack("<I", len(vendor)) + vendor
    vc_body += struct.pack("<I", len(comments))
    for c in comments:
        c_bytes = c.encode("utf-8")
        vc_body += struct.pack("<I", len(c_bytes)) + c_bytes

    payload = b"OggS\x00\x00" + b"\x00" * 20 + b"\x03vorbis" + vc_body
    ogg_file.write_bytes(payload)

    info = extract_track_metadata(str(ogg_file))
    assert info.title == "Akeboshi"
    assert info.artist == "LiSA"
