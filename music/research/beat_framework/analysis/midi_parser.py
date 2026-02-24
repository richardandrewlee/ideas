"""
MIDI Parser
-----------
Low-level MIDI file parser. Works with mido if installed,
falls back to a built-in pure-Python parser for portability.

Outputs a normalized event list regardless of which backend is used.
Captures all MIDI events: notes (with duration), key signatures, time
signatures, program changes, control changes, markers, and tempo maps.
"""

import struct
import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class MidiNote:
    """A single MIDI note event (note_on with velocity > 0)."""
    pitch:          int          # MIDI note number (0-127)
    velocity:       int          # Velocity (1-127)
    channel:        int          # MIDI channel (0-15; channel 9 = drums in GM)
    tick:           int          # Absolute tick position
    duration_ticks: int = 0      # Ticks until note_off (0 = unknown)
    time_sec:       float = 0.0  # Absolute time in seconds (computed from tempo map)


@dataclass
class MidiEvent:
    """Non-note MIDI event (meta or channel)."""
    event_type: str              # "key_signature", "time_signature", "program_change",
                                 # "control_change", "marker", "set_tempo"
    tick: int = 0                # Absolute tick position
    data: dict = field(default_factory=dict)
    # key_signature:  data = {"key": int, "mode": int}  (key: -7..7 flats/sharps, mode: 0=major 1=minor)
    # time_signature: data = {"numerator": int, "denominator": int}
    # program_change: data = {"program": int, "channel": int}
    # control_change: data = {"control": int, "value": int, "channel": int}
    # marker:         data = {"text": str}
    # set_tempo:      data = {"tempo": int}  (microseconds per beat)


@dataclass
class MidiTrack:
    name:    str = ""
    notes:   list[MidiNote] = field(default_factory=list)
    events:  list[MidiEvent] = field(default_factory=list)
    channel: Optional[int] = None  # Dominant channel
    program: Optional[int] = None  # GM program number from first program_change


@dataclass
class ParsedMidi:
    ticks_per_beat:  int = 480
    tempo:           int = 500000   # Microseconds per beat (default = 120 BPM)
    tracks:          list[MidiTrack] = field(default_factory=list)
    duration_ticks:  int = 0

    # Extended metadata
    key_signature:   Optional[tuple[int, int]] = None    # (key, mode) from first key_sig event
    time_signatures: list[tuple[int, int, int]] = field(default_factory=list)  # (tick, numerator, denominator)
    tempo_map:       list[tuple[int, int]] = field(default_factory=list)       # (tick, microseconds_per_beat)
    markers:         list[tuple[int, str]] = field(default_factory=list)       # (tick, text)

    @property
    def bpm(self) -> float:
        return round(60_000_000 / self.tempo, 2)

    @property
    def duration_bars(self) -> float:
        beats = self.duration_ticks / self.ticks_per_beat
        num = self.time_signatures[0][1] if self.time_signatures else 4
        return beats / num

    def tick_to_bar(self, tick: int) -> int:
        beats = tick / self.ticks_per_beat
        num = self.time_signatures[0][1] if self.time_signatures else 4
        return int(beats / num)

    def get_all_notes(self) -> list[MidiNote]:
        """All notes across all tracks, sorted by tick."""
        notes = []
        for t in self.tracks:
            notes.extend(t.notes)
        notes.sort(key=lambda n: n.tick)
        return notes

    def get_non_drum_notes(self) -> list[MidiNote]:
        """All notes except channel 9 (drums), sorted by tick."""
        notes = []
        for t in self.tracks:
            for n in t.notes:
                if n.channel != 9:
                    notes.append(n)
        notes.sort(key=lambda n: n.tick)
        return notes


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
            tempo = 500_000
            channels: list[int] = []
            # For pairing note_on/note_off to compute duration
            pending_notes: dict[tuple[int, int], MidiNote] = {}  # (channel, pitch) -> note

            for msg in mido_track:
                abs_tick += msg.time

                if msg.type == "set_tempo":
                    tempo = msg.tempo
                    result.tempo = tempo
                    result.tempo_map.append((abs_tick, tempo))
                    track.events.append(MidiEvent("set_tempo", abs_tick, {"tempo": tempo}))

                elif msg.type == "key_signature":
                    # mido provides key as string like "C" or "Am"
                    key_str = msg.key
                    key_val, mode_val = self._mido_key_to_int(key_str)
                    if result.key_signature is None:
                        result.key_signature = (key_val, mode_val)
                    track.events.append(MidiEvent("key_signature", abs_tick,
                                                  {"key": key_val, "mode": mode_val, "key_str": key_str}))

                elif msg.type == "time_signature":
                    result.time_signatures.append((abs_tick, msg.numerator, msg.denominator))
                    track.events.append(MidiEvent("time_signature", abs_tick,
                                                  {"numerator": msg.numerator, "denominator": msg.denominator}))

                elif msg.type == "program_change":
                    if track.program is None:
                        track.program = msg.program
                    track.events.append(MidiEvent("program_change", abs_tick,
                                                  {"program": msg.program, "channel": msg.channel}))

                elif msg.type == "control_change":
                    track.events.append(MidiEvent("control_change", abs_tick,
                                                  {"control": msg.control, "value": msg.value,
                                                   "channel": msg.channel}))

                elif msg.type == "marker" or msg.type == "cue_marker":
                    text = msg.text if hasattr(msg, "text") else ""
                    result.markers.append((abs_tick, text))
                    track.events.append(MidiEvent("marker", abs_tick, {"text": text}))

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
                    pending_notes[(msg.channel, msg.note)] = note

                elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                    key = (msg.channel, msg.note)
                    if key in pending_notes:
                        pending_notes[key].duration_ticks = abs_tick - pending_notes[key].tick
                        del pending_notes[key]

            if channels:
                track.channel = Counter(channels).most_common(1)[0][0]

            result.duration_ticks = max(result.duration_ticks, abs_tick)
            result.tracks.append(track)

        return result

    @staticmethod
    def _mido_key_to_int(key_str: str) -> tuple[int, int]:
        """Convert mido key string (e.g. 'C', 'Am', 'F#m') to (pitch_class, mode)."""
        key_str = key_str.strip()
        mode = 1 if key_str.endswith("m") else 0
        root = key_str.rstrip("m").strip()
        pitch_map = {
            "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
            "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
            "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11, "Cb": 11,
        }
        return pitch_map.get(root, 0), mode

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
        pending_notes: dict[tuple[int, int], MidiNote] = {}

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
                    note = MidiNote(
                        pitch=note_num, velocity=vel,
                        channel=channel, tick=abs_tick,
                    )
                    track.notes.append(note)
                    channels.append(channel)
                    result.duration_ticks = max(result.duration_ticks, abs_tick)
                    pending_notes[(channel, note_num)] = note
                else:
                    # note_on with vel=0 is note_off
                    key = (channel, note_num)
                    if key in pending_notes:
                        pending_notes[key].duration_ticks = abs_tick - pending_notes[key].tick
                        del pending_notes[key]

            elif status_type == 0x80 and i + 1 < len(data):  # note_off
                note_num = data[i]; i += 2
                key = (channel, note_num)
                if key in pending_notes:
                    pending_notes[key].duration_ticks = abs_tick - pending_notes[key].tick
                    del pending_notes[key]

            elif status_type == 0xB0 and i + 1 < len(data):  # control_change
                ctrl = data[i]; val = data[i+1]; i += 2
                track.events.append(MidiEvent("control_change", abs_tick,
                                              {"control": ctrl, "value": val, "channel": channel}))

            elif status_type == 0xC0 and i < len(data):       # program_change
                prog = data[i]; i += 1
                if track.program is None:
                    track.program = prog
                track.events.append(MidiEvent("program_change", abs_tick,
                                              {"program": prog, "channel": channel}))

            elif status_type == 0xA0 and i + 1 < len(data):   # poly aftertouch
                i += 2
            elif status_type == 0xD0 and i < len(data):        # channel pressure
                i += 1
            elif status_type == 0xE0 and i + 1 < len(data):   # pitch bend
                i += 2

            elif running_status == 0xFF:                        # meta event
                if i >= len(data): break
                meta_type = data[i]; i += 1
                meta_len, i = self._read_varlen(data, i)

                if meta_type == 0x51 and meta_len == 3:         # set_tempo
                    tempo_val = (data[i] << 16) | (data[i+1] << 8) | data[i+2]
                    result.tempo = tempo_val
                    result.tempo_map.append((abs_tick, tempo_val))
                    track.events.append(MidiEvent("set_tempo", abs_tick, {"tempo": tempo_val}))

                elif meta_type == 0x59 and meta_len == 2:       # key_signature
                    key_byte = data[i]   # Signed: -7..7 (flats/sharps)
                    mode_byte = data[i+1]  # 0=major, 1=minor
                    # Convert signed byte
                    if key_byte > 127:
                        key_byte -= 256
                    # Convert sharps/flats to pitch class
                    pitch_class = (key_byte * 7) % 12
                    if result.key_signature is None:
                        result.key_signature = (pitch_class, mode_byte)
                    track.events.append(MidiEvent("key_signature", abs_tick,
                                                  {"key": pitch_class, "mode": mode_byte}))

                elif meta_type == 0x58 and meta_len >= 2:       # time_signature
                    num = data[i]
                    denom = 2 ** data[i+1]
                    result.time_signatures.append((abs_tick, num, denom))
                    track.events.append(MidiEvent("time_signature", abs_tick,
                                                  {"numerator": num, "denominator": denom}))

                elif meta_type == 0x03:                          # track name
                    try:
                        track.name = data[i:i+meta_len].decode("utf-8", errors="ignore")
                    except Exception:
                        pass

                elif meta_type == 0x06:                          # marker
                    try:
                        text = data[i:i+meta_len].decode("utf-8", errors="ignore")
                        result.markers.append((abs_tick, text))
                        track.events.append(MidiEvent("marker", abs_tick, {"text": text}))
                    except Exception:
                        pass

                i += meta_len

            elif running_status == 0xF0:                        # sysex
                while i < len(data) and data[i] != 0xF7:
                    i += 1
                i += 1
            else:
                i += 1  # Skip unknown

        if channels:
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
