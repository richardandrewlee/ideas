"""
MIDI Parser
-----------
Low-level MIDI file parser. Works with mido if installed,
falls back to a built-in pure-Python parser for portability.

Outputs a normalized event list regardless of which backend is used.
"""

import struct
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class MidiNote:
    """A single MIDI note event (note_on with velocity > 0)."""
    pitch:     int          # MIDI note number (0-127)
    velocity:  int          # Velocity (1-127)
    channel:   int          # MIDI channel (0-15; channel 9 = drums in GM)
    tick:      int          # Absolute tick position
    time_sec:  float = 0.0  # Absolute time in seconds (computed from tempo map)


@dataclass
class MidiTrack:
    name:    str = ""
    notes:   list[MidiNote] = field(default_factory=list)
    channel: Optional[int] = None  # Dominant channel


@dataclass
class ParsedMidi:
    ticks_per_beat: int = 480
    tempo:          int = 500000   # Microseconds per beat (default = 120 BPM)
    tracks:         list[MidiTrack] = field(default_factory=list)
    duration_ticks: int = 0

    @property
    def bpm(self) -> float:
        return round(60_000_000 / self.tempo, 2)

    @property
    def duration_bars(self) -> float:
        beats = self.duration_ticks / self.ticks_per_beat
        return beats / 4.0  # Assuming 4/4


class MidiParser:
    """Parses MIDI files into a normalized structure."""

    def parse(self, path: str) -> Optional[ParsedMidi]:
        """Parse a MIDI file. Returns None on failure."""
        path = str(path)

        # Try mido first (cleaner handling of edge cases)
        try:
            import mido
            return self._parse_with_mido(path, mido)
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"mido failed on {path}: {e}")

        # Fall back to pure-Python parser
        try:
            return self._parse_builtin(path)
        except Exception as e:
            logger.debug(f"Built-in parser failed on {path}: {e}")
            return None

    # -----------------------------------------------------------------------
    # mido backend
    # -----------------------------------------------------------------------

    def _parse_with_mido(self, path: str, mido) -> ParsedMidi:
        mid = mido.MidiFile(path)
        result = ParsedMidi(ticks_per_beat=mid.ticks_per_beat)

        for mido_track in mid.tracks:
            track = MidiTrack(name=mido_track.name)
            abs_tick = 0
            tempo    = 500_000
            channels: list[int] = []

            for msg in mido_track:
                abs_tick += msg.time
                if msg.type == "set_tempo":
                    tempo = msg.tempo
                    result.tempo = tempo
                elif msg.type == "note_on" and msg.velocity > 0:
                    note = MidiNote(
                        pitch=msg.note,
                        velocity=msg.velocity,
                        channel=msg.channel,
                        tick=abs_tick,
                        time_sec=mido.tick2second(abs_tick, mid.ticks_per_beat, tempo),
                    )
                    track.notes.append(note)
                    channels.append(msg.channel)

            if channels:
                from collections import Counter
                track.channel = Counter(channels).most_common(1)[0][0]

            result.duration_ticks = max(result.duration_ticks, abs_tick)
            result.tracks.append(track)

        return result

    # -----------------------------------------------------------------------
    # Pure-Python fallback parser
    # -----------------------------------------------------------------------

    def _parse_builtin(self, path: str) -> ParsedMidi:
        with open(path, "rb") as f:
            data = f.read()

        if data[:4] != b"MThd":
            raise ValueError("Not a valid MIDI file")

        header_len = struct.unpack(">I", data[4:8])[0]
        fmt, ntracks, ticks = struct.unpack(">HHH", data[8:14])
        result = ParsedMidi(ticks_per_beat=ticks)

        pos = 8 + header_len
        while pos < len(data) - 8:
            if data[pos:pos+4] != b"MTrk":
                break
            track_len = struct.unpack(">I", data[pos+4:pos+8])[0]
            track_data = data[pos+8 : pos+8+track_len]
            pos += 8 + track_len

            track = self._parse_track(track_data, result)
            result.tracks.append(track)

        return result

    def _parse_track(self, data: bytes, result: ParsedMidi) -> MidiTrack:
        track = MidiTrack()
        i = 0
        abs_tick = 0
        running_status = 0
        channels: list[int] = []

        while i < len(data):
            # Delta time (variable length)
            delta, i = self._read_varlen(data, i)
            abs_tick += delta

            if i >= len(data):
                break

            b = data[i]

            # Status byte
            if b & 0x80:
                running_status = b
                i += 1

            status_type = running_status & 0xF0
            channel     = running_status & 0x0F

            if status_type == 0x90 and i + 1 < len(data):   # note_on
                note_num = data[i]; vel = data[i+1]; i += 2
                if vel > 0:
                    track.notes.append(MidiNote(
                        pitch=note_num, velocity=vel,
                        channel=channel, tick=abs_tick,
                    ))
                    channels.append(channel)
                    result.duration_ticks = max(result.duration_ticks, abs_tick)

            elif status_type == 0x80 and i + 1 < len(data): # note_off
                i += 2
            elif status_type in (0xA0, 0xB0, 0xE0) and i + 1 < len(data):
                i += 2
            elif status_type in (0xC0, 0xD0) and i < len(data):
                i += 1
            elif running_status == 0xFF:                      # meta event
                if i >= len(data): break
                meta_type = data[i]; i += 1
                meta_len, i = self._read_varlen(data, i)
                if meta_type == 0x51 and meta_len == 3:       # set_tempo
                    result.tempo = (data[i] << 16) | (data[i+1] << 8) | data[i+2]
                elif meta_type == 0x03:                        # track name
                    try:
                        track.name = data[i:i+meta_len].decode("utf-8", errors="ignore")
                    except Exception:
                        pass
                i += meta_len
            elif running_status == 0xF0:                      # sysex
                while i < len(data) and data[i] != 0xF7:
                    i += 1
                i += 1
            else:
                i += 1  # Skip unknown

        if channels:
            from collections import Counter
            track.channel = Counter(channels).most_common(1)[0][0]

        return track

    @staticmethod
    def _read_varlen(data: bytes, pos: int) -> tuple[int, int]:
        value = 0
        while pos < len(data):
            b = data[pos]; pos += 1
            value = (value << 7) | (b & 0x7F)
            if not (b & 0x80):
                break
        return value, pos
