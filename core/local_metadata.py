"""Zero-dependency local audio metadata and lyrics extractor for KikuMoe.

Parses tags, duration, embedded cover art, and lyrics directly from binary headers
for MP3 (ID3v1/ID3v2), FLAC, OGG/Opus, M4A/AAC, and WAV files using standard library.
"""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LocalTrackInfo:
    """Extracted metadata and assets for a local audio track."""

    file_path: str
    title: str = ""
    artist: str = ""
    album: str = ""
    duration_seconds: float = 0.0
    cover_bytes: bytes | None = None
    cover_mime: str | None = None
    lyrics: str | None = None
    is_synced_lyrics: bool = False

    def display_title(self) -> str:
        """Returns clean title or fallback to filename stem."""
        if self.title.strip():
            return self.title.strip()
        stem = Path(self.file_path).stem
        # If stem is "Artist - Title", try splitting
        if " - " in stem:
            parts = stem.split(" - ", 1)
            return parts[1].strip()
        return stem.strip()

    def display_artist(self) -> str:
        """Returns clean artist or fallback from filename stem."""
        if self.artist.strip():
            return self.artist.strip()
        stem = Path(self.file_path).stem
        if " - " in stem:
            parts = stem.split(" - ", 1)
            return parts[0].strip()
        return "Unknown Artist"


def _decode_string(data: bytes, encoding_byte: int) -> str:
    """Decode ID3 text frame according to standard encoding byte."""
    if not data:
        return ""
    try:
        if encoding_byte == 0:
            return data.decode("iso-8859-1", errors="replace").rstrip("\x00")
        elif encoding_byte == 1:
            return data.decode("utf-16", errors="replace").rstrip("\x00")
        elif encoding_byte == 2:
            return data.decode("utf-16-be", errors="replace").rstrip("\x00")
        elif encoding_byte == 3:
            return data.decode("utf-8", errors="replace").rstrip("\x00")
    except Exception:
        pass
    # Fallback UTF-8 / latin-1
    try:
        return data.decode("utf-8", errors="replace").rstrip("\x00")
    except Exception:
        return data.decode("latin-1", errors="replace").rstrip("\x00")


def _read_synchsafe_int(data: bytes) -> int:
    """Decode a 4-byte ID3 synchsafe integer (7 bits per byte)."""
    if len(data) < 4:
        return 0
    return (
        ((data[0] & 0x7F) << 21)
        | ((data[1] & 0x7F) << 14)
        | ((data[2] & 0x7F) << 7)
        | (data[3] & 0x7F)
    )


# =========================================================================
# 1. MP3 / ID3v2 Parser
# =========================================================================


def _parse_id3v2(f: io.BufferedReader, info: LocalTrackInfo) -> None:
    """Parse ID3v2 tags (v2.2, v2.3, v2.4)."""
    f.seek(0)
    header = f.read(10)
    if len(header) < 10 or header[:3] != b"ID3":
        return

    version_major = header[3]
    tag_size = _read_synchsafe_int(header[6:10])
    tag_data = f.read(tag_size)
    offset = 0
    data_len = len(tag_data)

    while offset < data_len - 10:
        if version_major in (3, 4):
            # ID3v2.3 / ID3v2.4 frame header: 4-byte ID, 4-byte size, 2-byte flags
            frame_id = tag_data[offset : offset + 4]
            if frame_id[0] == 0:
                break
            try:
                frame_name = frame_id.decode("ascii")
            except Exception:
                break

            if version_major == 4:
                frame_size = _read_synchsafe_int(tag_data[offset + 4 : offset + 8])
            else:
                frame_size = struct.unpack(">I", tag_data[offset + 4 : offset + 8])[0]

            frame_content = tag_data[offset + 10 : offset + 10 + frame_size]
            offset += 10 + frame_size

            if not frame_content:
                continue

            enc = frame_content[0]
            val_bytes = frame_content[1:]

            if frame_name == "TIT2":
                info.title = _decode_string(val_bytes, enc).strip()
            elif frame_name == "TPE1":
                info.artist = _decode_string(val_bytes, enc).strip()
            elif frame_name == "TALB":
                info.album = _decode_string(val_bytes, enc).strip()
            elif frame_name == "TLEN":
                try:
                    ms_str = _decode_string(val_bytes, enc).strip()
                    info.duration_seconds = max(0.0, float(ms_str) / 1000.0)
                except Exception:
                    pass
            elif frame_name == "USLT":
                # Unsynchronized lyric: enc(1) + lang(3) + descriptor(null-term) + lyrics
                try:
                    if len(val_bytes) >= 3:
                        text_part = val_bytes[3:]
                        # Skip null-terminated descriptor
                        desc_sep = b"\x00\x00" if enc in (1, 2) else b"\x00"
                        if desc_sep in text_part:
                            _, lyrics_raw = text_part.split(desc_sep, 1)
                        else:
                            lyrics_raw = text_part
                        parsed_lyr = _decode_string(lyrics_raw, enc).strip()
                        if parsed_lyr and not info.lyrics:
                            info.lyrics = parsed_lyr
                except Exception:
                    pass
            elif frame_name == "APIC" and not info.cover_bytes:
                # Attached picture: enc(1) + mime(null-term) + type(1) + desc(null-term) + data
                try:
                    idx = 0
                    null_pos = val_bytes.find(b"\x00", idx)
                    if null_pos != -1:
                        mime = val_bytes[idx:null_pos].decode("ascii", errors="ignore")
                        idx = null_pos + 1
                        if idx < len(val_bytes):
                            # pic_type = val_bytes[idx]
                            idx += 1
                            # description
                            desc_sep = b"\x00\x00" if enc in (1, 2) else b"\x00"
                            desc_pos = val_bytes.find(desc_sep, idx)
                            if desc_pos != -1:
                                idx = desc_pos + len(desc_sep)
                            pic_data = val_bytes[idx:]
                            if pic_data:
                                info.cover_bytes = pic_data
                                info.cover_mime = mime or "image/jpeg"
                except Exception:
                    pass
        elif version_major == 2:
            # ID3v2.2: 3-byte ID, 3-byte size
            frame_id = tag_data[offset : offset + 3]
            if frame_id[0] == 0:
                break
            try:
                frame_name = frame_id.decode("ascii")
            except Exception:
                break
            frame_size = int.from_bytes(tag_data[offset + 3 : offset + 6], "big")
            frame_content = tag_data[offset + 6 : offset + 6 + frame_size]
            offset += 6 + frame_size

            if not frame_content:
                continue
            enc = frame_content[0]
            val_bytes = frame_content[1:]

            if frame_name == "TT2":
                info.title = _decode_string(val_bytes, enc).strip()
            elif frame_name == "TP1":
                info.artist = _decode_string(val_bytes, enc).strip()
            elif frame_name == "TAL":
                info.album = _decode_string(val_bytes, enc).strip()
            elif frame_name == "TLE":
                try:
                    info.duration_seconds = float(_decode_string(val_bytes, enc)) / 1000.0
                except Exception:
                    pass
            elif frame_name == "PIC" and not info.cover_bytes:
                try:
                    # PIC: enc(1) + format(3) + type(1) + desc(null-term) + data
                    if len(val_bytes) >= 5:
                        fmt_str = val_bytes[:3].decode("ascii", errors="ignore").lower()
                        mime = "image/png" if fmt_str == "png" else "image/jpeg"
                        idx = 4
                        desc_sep = b"\x00\x00" if enc in (1, 2) else b"\x00"
                        desc_pos = val_bytes.find(desc_sep, idx)
                        if desc_pos != -1:
                            idx = desc_pos + len(desc_sep)
                        info.cover_bytes = val_bytes[idx:]
                        info.cover_mime = mime
                except Exception:
                    pass
        else:
            break


def _estimate_mp3_duration(f: io.BufferedReader, file_size: int, info: LocalTrackInfo) -> None:
    """If ID3 TLEN is missing, probe first MP3 audio frame for Xing/Info header or bitrate."""
    if info.duration_seconds > 0:
        return

    f.seek(0)
    # Skip ID3 if present
    head = f.read(10)
    audio_start = 0
    if len(head) == 10 and head[:3] == b"ID3":
        audio_start = 10 + _read_synchsafe_int(head[6:10])

    f.seek(audio_start)
    chunk = f.read(4096)
    if not chunk:
        return

    # Look for sync word 0xFFE / 0xFFF
    for i in range(len(chunk) - 4):
        if chunk[i] == 0xFF and (chunk[i + 1] & 0xE0) == 0xE0:
            frame_data = chunk[i:]
            # Look for Xing or Info header (typically at offset 36 in stereo or 21 in mono)
            for marker in (b"Xing", b"Info"):
                pos = frame_data.find(marker)
                if pos != -1 and len(frame_data) >= pos + 12:
                    flags = struct.unpack(">I", frame_data[pos + 4 : pos + 8])[0]
                    if flags & 0x01:  # FRAMES flag set
                        total_frames = struct.unpack(">I", frame_data[pos + 8 : pos + 12])[0]
                        # Standard MPEG Layer 3 samples per frame = 1152
                        # Assuming 44100Hz default
                        info.duration_seconds = round((total_frames * 1152) / 44100.0, 2)
                        return
            break

    # Fallback estimation based on audio payload at standard 192kbps
    audio_bytes = max(0, file_size - audio_start)
    if audio_bytes > 0:
        info.duration_seconds = round(audio_bytes / (192 * 1024 / 8), 1)


# =========================================================================
# 2. FLAC Parser
# =========================================================================


def _parse_flac(f: io.BufferedReader, info: LocalTrackInfo) -> None:
    """Parse native FLAC STREAMINFO, VORBIS_COMMENT, and PICTURE blocks."""
    f.seek(0)
    if f.read(4) != b"fLaC":
        return

    while True:
        header = f.read(4)
        if len(header) < 4:
            break
        is_last = bool(header[0] & 0x80)
        block_type = header[0] & 0x7F
        block_len = int.from_bytes(header[1:4], "big")
        data = f.read(block_len)
        if len(data) < block_len:
            break

        if block_type == 0 and len(data) >= 34:
            # STREAMINFO: sample rate (20b), channels (3b), bits (5b), total samples (36b)
            # data[10:18] holds sample rate & sample count
            val = struct.unpack(">Q", data[10:18])[0]
            sample_rate = val >> 44
            # total samples is lowest 36 bits
            total_samples = val & 0xFFFFFFFFF
            if sample_rate > 0 and total_samples > 0:
                info.duration_seconds = round(total_samples / float(sample_rate), 2)
        elif block_type == 4:
            # VORBIS_COMMENT
            _parse_vorbis_comments(data, info)
        elif block_type == 6 and not info.cover_bytes:
            # PICTURE
            try:
                # 4B picture type, 4B mime len, mime, 4B desc len, desc, 16B props, data len, data
                offset = 4
                mime_len = struct.unpack(">I", data[offset : offset + 4])[0]
                offset += 4
                mime = data[offset : offset + mime_len].decode("ascii", errors="ignore")
                offset += mime_len
                desc_len = struct.unpack(">I", data[offset : offset + 4])[0]
                offset += 4 + desc_len + 16
                data_len = struct.unpack(">I", data[offset : offset + 4])[0]
                offset += 4
                pic_data = data[offset : offset + data_len]
                if pic_data:
                    info.cover_bytes = pic_data
                    info.cover_mime = mime or "image/jpeg"
            except Exception:
                pass

        if is_last:
            break


def _parse_vorbis_comments(data: bytes, info: LocalTrackInfo) -> None:
    """Parse standard Vorbis Comments byte buffer."""
    try:
        offset = 0
        vendor_len = struct.unpack("<I", data[offset : offset + 4])[0]
        offset += 4 + vendor_len
        comment_count = struct.unpack("<I", data[offset : offset + 4])[0]
        offset += 4
        for _ in range(comment_count):
            if offset + 4 > len(data):
                break
            c_len = struct.unpack("<I", data[offset : offset + 4])[0]
            offset += 4
            comment = data[offset : offset + c_len].decode("utf-8", errors="replace")
            offset += c_len
            if "=" in comment:
                k, v = comment.split("=", 1)
                key_upper = k.strip().upper()
                val = v.strip()
                if key_upper == "TITLE" and not info.title:
                    info.title = val
                elif key_upper == "ARTIST" and not info.artist:
                    info.artist = val
                elif key_upper == "ALBUM" and not info.album:
                    info.album = val
                elif key_upper in ("LYRICS", "UNSYNCEDLYRICS") and not info.lyrics:
                    info.lyrics = val
    except Exception:
        pass


# =========================================================================
# 3. OGG / Opus Parser
# =========================================================================


def _parse_ogg(f: io.BufferedReader, file_size: int, info: LocalTrackInfo) -> None:
    """Extract metadata from OGG Vorbis or Opus file."""
    f.seek(0)
    chunk = f.read(65536)
    if not chunk.startswith(b"OggS"):
        return

    # Check for Vorbis comment marker
    vorbis_pos = chunk.find(b"\x03vorbis")
    if vorbis_pos != -1:
        # Vorbis comments start right after the 7-byte header
        _parse_vorbis_comments(chunk[vorbis_pos + 7 :], info)

    # Check for Opus tags marker
    opus_pos = chunk.find(b"OpusTags")
    if opus_pos != -1:
        _parse_vorbis_comments(chunk[opus_pos + 8 :], info)

    # Duration fallback from file size at 160kbps
    if info.duration_seconds <= 0 and file_size > 0:
        info.duration_seconds = round(file_size / (160 * 1024 / 8), 1)


# =========================================================================
# 4. M4A / MP4 / AAC Parser
# =========================================================================


def _parse_m4a(f: io.BufferedReader, file_size: int, info: LocalTrackInfo) -> None:
    """Parse ISO base media file format (MP4/M4A) atoms."""
    f.seek(0)

    def _read_atoms(start: int, end: int) -> None:
        curr = start
        while curr < end - 8:
            f.seek(curr)
            head = f.read(8)
            if len(head) < 8:
                break
            size, atom_type = struct.unpack(">I4s", head)
            if size == 1:
                # 64-bit size
                ext_size_bytes = f.read(8)
                if len(ext_size_bytes) == 8:
                    size = struct.unpack(">Q", ext_size_bytes)[0]
                else:
                    break
            elif size == 0:
                size = end - curr

            if size < 8:
                break

            atom_end = min(curr + size, end)

            if atom_type in (b"moov", b"udta", b"trak", b"mdia", b"minf", b"stbl"):
                _read_atoms(curr + 8, atom_end)
            elif atom_type == b"mvhd":
                # Movie header contains timescale & duration
                mvhd_data = f.read(min(size - 8, 32))
                if len(mvhd_data) >= 20:
                    version = mvhd_data[0]
                    if version == 0:
                        timescale = struct.unpack(">I", mvhd_data[12:16])[0]
                        duration = struct.unpack(">I", mvhd_data[16:20])[0]
                        if timescale > 0:
                            info.duration_seconds = round(duration / float(timescale), 2)
                    elif version == 1 and len(mvhd_data) >= 32:
                        timescale = struct.unpack(">I", mvhd_data[20:24])[0]
                        duration = struct.unpack(">Q", mvhd_data[24:32])[0]
                        if timescale > 0:
                            info.duration_seconds = round(duration / float(timescale), 2)
            elif atom_type == b"meta":
                # meta atom has a 4-byte version/flags before child atoms
                _read_atoms(curr + 12, atom_end)
            elif atom_type == b"ilst":
                _parse_m4a_ilst(curr + 8, atom_end)

            curr = atom_end

    def _parse_m4a_ilst(start: int, end: int) -> None:
        curr = start
        while curr < end - 8:
            f.seek(curr)
            head = f.read(8)
            if len(head) < 8:
                break
            size, tag_name = struct.unpack(">I4s", head)
            if size < 8 or curr + size > end:
                break
            tag_data = f.read(size - 8)
            curr += size

            # tag_data contains child 'data' atoms (4B 'data' + 8B flags/locale = 12B)
            d_pos = tag_data.find(b"data")
            if d_pos != -1:
                skip_offset = 12 if len(tag_data) >= d_pos + 12 else 4
                payload = tag_data[d_pos + skip_offset :]
                text_val = payload.decode("utf-8", errors="replace").strip("\x00 \t\r\n")
                if tag_name == b"\xa9nam":
                    info.title = text_val
                elif tag_name == b"\xa9ART":
                    info.artist = text_val
                elif tag_name == b"\xa9alb":
                    info.album = text_val
                elif tag_name == b"\xa9lyr":
                    info.lyrics = text_val
                elif tag_name == b"covr" and not info.cover_bytes:
                    info.cover_bytes = payload
                    info.cover_mime = (
                        "image/png" if payload.startswith(b"\x89PNG") else "image/jpeg"
                    )

    try:
        _read_atoms(0, min(file_size, 1024 * 1024 * 5))
    except Exception:
        pass


# =========================================================================
# 5. WAV Parser
# =========================================================================


def _parse_wav(f: io.BufferedReader, file_size: int, info: LocalTrackInfo) -> None:
    """Parse RIFF/WAVE header and format chunk."""
    f.seek(0)
    riff = f.read(12)
    if len(riff) < 12 or riff[:4] != b"RIFF" or riff[8:12] != b"WAVE":
        return

    byte_rate = 0
    data_size = 0

    while True:
        head = f.read(8)
        if len(head) < 8:
            break
        chunk_id, chunk_size = struct.unpack("<4sI", head)
        chunk_data = f.read(chunk_size)
        if chunk_id == b"fmt " and len(chunk_data) >= 16:
            byte_rate = struct.unpack("<I", chunk_data[8:12])[0]
        elif chunk_id == b"data":
            data_size = chunk_size

        # Pad to word boundary
        if chunk_size % 2 == 1:
            f.seek(1, io.SEEK_CUR)

    if byte_rate > 0 and data_size > 0:
        info.duration_seconds = round(data_size / float(byte_rate), 2)
    elif byte_rate > 0 and file_size > 44:
        info.duration_seconds = round((file_size - 44) / float(byte_rate), 2)


# =========================================================================
# 6. Sidecar .lrc & Unified Discovery Cascade
# =========================================================================


def _find_sidecar_lrc(file_path: str) -> str | None:
    """Find companion .lrc file in the same directory."""
    p = Path(file_path)
    parent = p.parent
    stem = p.stem

    candidates = [
        parent / f"{stem}.lrc",
        parent / f"{stem}.LRC",
    ]

    for cand in candidates:
        if cand.is_file():
            try:
                for enc in ("utf-8", "utf-8-sig", "iso-8859-1", "cp1252"):
                    try:
                        return cand.read_text(encoding=enc).strip()
                    except UnicodeDecodeError:
                        continue
            except Exception:
                pass
    return None


def extract_track_metadata(file_path: str) -> LocalTrackInfo:
    """Extract complete metadata, album art, and lyrics from an audio file.

    Zero external binaries required; operates safely on any standard format.
    """
    path_obj = Path(file_path)
    info = LocalTrackInfo(file_path=str(path_obj.resolve()))

    if not path_obj.is_file():
        return info

    ext = path_obj.suffix.lower()
    file_size = path_obj.stat().st_size

    try:
        with open(file_path, "rb") as f:
            if ext == ".mp3":
                _parse_id3v2(f, info)
                _estimate_mp3_duration(f, file_size, info)
            elif ext == ".flac":
                _parse_flac(f, info)
            elif ext in (".ogg", ".opus"):
                _parse_ogg(f, file_size, info)
            elif ext in (".m4a", ".aac", ".mp4"):
                _parse_m4a(f, file_size, info)
            elif ext == ".wav":
                _parse_wav(f, file_size, info)
    except Exception:
        pass

    # Sidecar .lrc has highest precedence for lyrics
    sidecar_lrc = _find_sidecar_lrc(file_path)
    if sidecar_lrc:
        info.lyrics = sidecar_lrc

    # Check if lyrics have synchronized timestamps [mm:ss.xx]
    if info.lyrics:
        info.is_synced_lyrics = bool(
            "[" in info.lyrics and ":" in info.lyrics and "]" in info.lyrics
        )

    return info
