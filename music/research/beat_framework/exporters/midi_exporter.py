"""
MIDI Exporter
-------------
Converts a RawBeat to a standard MIDI file (.mid).

Output:
    - Format 1 MIDI (multi-track: one track per instrument group)
    - Channel 10 (9 zero-indexed) for drums, per GM standard
    - Humanized tick offsets applied from hit.tick_offset
    - Optional: additional melodic/bass track stubs for DAW context

Works with mido if installed, otherwise uses a pure-Python MIDI writer.
"""

import struct
import logging
from pathlib import Path
from typing import Optional

from ..generators.statistical_generator import RawBeat, RawHit, INSTRUMENT_TO_MIDI

logger = logging.getLogger(__name__)

DRUM_CHANNEL = 9  # 0-indexed channel 10

# Group instruments into logical tracks for Format 1 MIDI
TRACK_GROUPS = {
    "Kick":      ["kick"],
    "Snare":     ["snare", "clap"],
    "Hi-Hats":   ["hihat_closed", "hihat_open"],
    "Cymbals":   ["crash", "ride", "splash", "china"],
    "Toms":      ["tom_low", "tom_mid", "tom_high"],
    "Percussion":["tambourine", "cowbell", "maracas", "cabasa", "claves",
                  "bongo_hi", "bongo_lo", "conga_mute", "conga_hi", "conga_lo"],
}


class MidiExporter:
    """Exports a RawBeat to a MIDI file."""

    def export(
        self,
        beat: RawBeat,
        output_path: str,
        multi_track: bool = True,
        loop_count: int = 1,
    ) -> str:
        """
        Write a RawBeat to a .mid file.

        Args:
            beat:         The beat to export.
            output_path:  Destination path (will create parent dirs).
            multi_track:  If True, write Format 1 (separate tracks per group).
                          If False, write Format 0 (single merged track).
            loop_count:   How many times to repeat the pattern in the MIDI file.

        Returns:
            The output path as a string.
        """
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Expand hits across loop_count repetitions
        all_hits = list(beat.hits)
        if loop_count > 1:
            total_steps = beat.grid_steps
            for repeat in range(1, loop_count):
                for hit in beat.hits:
                    all_hits.append(RawHit(
                        instrument=hit.instrument,
                        midi_note=hit.midi_note,
                        step=hit.step + total_steps * repeat,
                        velocity=hit.velocity,
                        tick_offset=hit.tick_offset,
                    ))

        try:
            import mido
            self._export_mido(beat, all_hits, output_path, multi_track)
        except ImportError:
            self._export_builtin(beat, all_hits, output_path, multi_track)

        logger.info(f"MIDI exported → {output_path}")
        return output_path

    # -----------------------------------------------------------------------
    # mido backend
    # -----------------------------------------------------------------------

    def _export_mido(
        self,
        beat: RawBeat,
        hits: list[RawHit],
        path: str,
        multi_track: bool,
    ) -> None:
        import mido

        tpb   = beat.ticks_per_beat
        tempo = int(60_000_000 / beat.bpm)

        if multi_track:
            mid = mido.MidiFile(type=1, ticks_per_beat=tpb)

            # Tempo track
            tempo_track = mido.MidiTrack()
            tempo_track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))
            tempo_track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
            mid.tracks.append(tempo_track)

            # One track per instrument group
            for group_name, instruments in TRACK_GROUPS.items():
                group_hits = [h for h in hits if h.instrument in instruments]
                if not group_hits:
                    continue
                track = mido.MidiTrack()
                track.name = group_name
                track.append(mido.MetaMessage("track_name", name=group_name, time=0))
                self._hits_to_mido_track(track, group_hits, beat, tempo)
                mid.tracks.append(track)
        else:
            mid = mido.MidiFile(type=0, ticks_per_beat=tpb)
            track = mido.MidiTrack()
            track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))
            self._hits_to_mido_track(track, hits, beat, tempo)
            mid.tracks.append(track)

        mid.save(path)

    def _hits_to_mido_track(self, track, hits: list[RawHit], beat: RawBeat, tempo: int) -> None:
        import mido

        ticks_per_step = beat.ticks_per_step

        # Build absolute-tick events (note_on + note_off pairs)
        events = []
        for hit in hits:
            abs_tick = int(hit.step * ticks_per_step + hit.tick_offset)
            abs_tick = max(0, abs_tick)
            events.append((abs_tick,     "note_on",  hit.midi_note, hit.velocity))
            events.append((abs_tick + 1, "note_off", hit.midi_note, 0))

        # Sort by tick, then note_off before note_on at same tick
        events.sort(key=lambda e: (e[0], 0 if e[1] == "note_off" else 1))

        # Convert to delta times
        prev_tick = 0
        for abs_tick, msg_type, note, vel in events:
            delta = max(0, abs_tick - prev_tick)
            prev_tick = abs_tick
            if msg_type == "note_on":
                track.append(mido.Message("note_on",  channel=DRUM_CHANNEL, note=note, velocity=vel, time=delta))
            else:
                track.append(mido.Message("note_off", channel=DRUM_CHANNEL, note=note, velocity=0,   time=delta))

        track.append(mido.MetaMessage("end_of_track", time=0))

    # -----------------------------------------------------------------------
    # Pure-Python fallback writer
    # -----------------------------------------------------------------------

    def _export_builtin(
        self,
        beat: RawBeat,
        hits: list[RawHit],
        path: str,
        multi_track: bool,
    ) -> None:
        tempo   = int(60_000_000 / beat.bpm)
        tpb     = beat.ticks_per_beat
        tps     = beat.ticks_per_step

        # Build event list
        events = []
        for hit in hits:
            abs_tick = int(hit.step * tps + hit.tick_offset)
            abs_tick = max(0, abs_tick)
            events.append((abs_tick,     0x99, hit.midi_note, hit.velocity))  # note_on ch10
            events.append((abs_tick + 1, 0x89, hit.midi_note, 0))             # note_off ch10

        events.sort(key=lambda e: e[0])

        # Build track bytes
        track_bytes = bytearray()
        # Tempo meta event at tick 0
        track_bytes += self._meta_event(0, 0x51, struct.pack(">I", tempo)[1:])
        # Time sig 4/4
        track_bytes += self._meta_event(0, 0x58, bytes([4, 2, 24, 8]))

        prev_tick = 0
        for abs_tick, status, note, vel in events:
            delta = max(0, abs_tick - prev_tick)
            prev_tick = abs_tick
            track_bytes += self._varlen(delta)
            track_bytes += bytes([status, note, vel])

        track_bytes += self._meta_event(0, 0x2F, b"")  # end_of_track

        # Assemble MIDI file
        header = b"MThd" + struct.pack(">IHHH", 6, 0, 1, tpb)
        track_chunk = b"MTrk" + struct.pack(">I", len(track_bytes)) + bytes(track_bytes)

        with open(path, "wb") as f:
            f.write(header + track_chunk)

    @staticmethod
    def _varlen(value: int) -> bytes:
        result = [value & 0x7F]
        value >>= 7
        while value:
            result.insert(0, (value & 0x7F) | 0x80)
            value >>= 7
        return bytes(result)

    def export_song(
        self,
        song_beat,
        output_path: str,
        loop_count: int = 1,
    ) -> str:
        """Export a SongBeat (full-song percussion) to MIDI with section markers.

        Converts the SongBeat to a RawBeat and exports with markers.
        """
        raw = song_beat.to_raw_beat()
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        try:
            import mido
            self._export_song_mido(song_beat, raw, output_path)
        except ImportError:
            # Fallback: export as plain MIDI without markers
            self.export(raw, output_path, multi_track=True, loop_count=loop_count)

        logger.info(f"Song MIDI exported → {output_path} ({song_beat.total_bars} bars)")
        return output_path

    def _export_song_mido(self, song_beat, raw_beat: RawBeat, path: str) -> None:
        """Export with mido, adding section markers."""
        import mido

        tpb = raw_beat.ticks_per_beat
        tempo = int(60_000_000 / raw_beat.bpm)
        tps = raw_beat.ticks_per_step

        mid = mido.MidiFile(type=1, ticks_per_beat=tpb)

        # Tempo track with markers
        tempo_track = mido.MidiTrack()
        tempo_track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))
        tempo_track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))

        # Add section markers
        marker_events = []
        for section in song_beat.sections:
            tick = int(section.start_bar * song_beat.steps_per_bar * tps)
            label = f"{section.section_type.value} (energy={section.energy:.1f})"
            marker_events.append((tick, label))

        marker_events.sort(key=lambda e: e[0])
        prev_tick = 0
        for tick, label in marker_events:
            delta = max(0, tick - prev_tick)
            prev_tick = tick
            tempo_track.append(mido.MetaMessage("marker", text=label, time=delta))

        tempo_track.append(mido.MetaMessage("end_of_track", time=0))
        mid.tracks.append(tempo_track)

        # Instrument tracks
        all_hits = list(raw_beat.hits)
        for group_name, instruments in TRACK_GROUPS.items():
            group_hits = [h for h in all_hits if h.instrument in instruments]
            if not group_hits:
                continue
            track = mido.MidiTrack()
            track.name = group_name
            track.append(mido.MetaMessage("track_name", name=group_name, time=0))
            self._hits_to_mido_track(track, group_hits, raw_beat, tempo)
            mid.tracks.append(track)

        mid.save(path)

    def export_full_arrangement(
        self,
        full_arrangement,
        output_path: str,
    ) -> str:
        """Export a FullArrangement (drums + bass + harmony) to multi-track MIDI.

        Drums on channel 9 (GM standard), bass on channel 0, harmony on channel 1.
        Each instrument gets its own track with program change messages.
        """
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        try:
            import mido
            self._export_full_mido(full_arrangement, output_path)
        except ImportError:
            self._export_full_builtin(full_arrangement, output_path)

        total_notes = 0
        if full_arrangement.drums:
            total_notes += sum(len(s.hits) for s in full_arrangement.drums.sections)
        if full_arrangement.bass:
            total_notes += len(full_arrangement.bass.hits)
        if full_arrangement.harmony:
            total_notes += len(full_arrangement.harmony.hits)
        logger.info(
            f"Full arrangement MIDI exported → {output_path} "
            f"({full_arrangement.total_bars} bars, {total_notes} notes)"
        )
        return output_path

    def _export_full_mido(self, arrangement, path: str) -> None:
        """Export full arrangement with mido: drums + bass + harmony tracks."""
        import mido

        bpm = arrangement.bpm
        tpb = 480
        tempo = int(60_000_000 / bpm)
        steps_per_bar = 16
        tps = tpb // 4  # ticks per 16th note step

        mid = mido.MidiFile(type=1, ticks_per_beat=tpb)

        # Tempo track with section markers
        tempo_track = mido.MidiTrack()
        tempo_track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))
        tempo_track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))

        if arrangement.arrangement:
            marker_events = []
            current_bar = 0
            for section in arrangement.arrangement.sections:
                tick = int(current_bar * steps_per_bar * tps)
                label = f"{section.section_type.value} (energy={section.energy:.1f})"
                marker_events.append((tick, label))
                current_bar += section.bars

            marker_events.sort(key=lambda e: e[0])
            prev_tick = 0
            for tick, label in marker_events:
                delta = max(0, tick - prev_tick)
                prev_tick = tick
                tempo_track.append(mido.MetaMessage("marker", text=label, time=delta))

        tempo_track.append(mido.MetaMessage("end_of_track", time=0))
        mid.tracks.append(tempo_track)

        # Drum tracks (channel 9)
        if arrangement.drums:
            raw = arrangement.drums.to_raw_beat()
            all_hits = list(raw.hits)
            for group_name, instruments in TRACK_GROUPS.items():
                group_hits = [h for h in all_hits if h.instrument in instruments]
                if not group_hits:
                    continue
                track = mido.MidiTrack()
                track.name = group_name
                track.append(mido.MetaMessage("track_name", name=group_name, time=0))
                self._hits_to_mido_track(track, group_hits, raw, tempo)
                mid.tracks.append(track)

        # Bass track (channel 0)
        BASS_CHANNEL = 0
        if arrangement.bass and arrangement.bass.hits:
            bass_track = mido.MidiTrack()
            bass_track.name = "Bass"
            bass_track.append(mido.MetaMessage("track_name", name="Bass", time=0))
            bass_track.append(mido.Message(
                "program_change", channel=BASS_CHANNEL,
                program=arrangement.bass.midi_program, time=0
            ))

            events = []
            for hit in arrangement.bass.hits:
                abs_tick = int(hit.step * tps + hit.tick_offset)
                abs_tick = max(0, abs_tick)
                dur_ticks = max(1, int(hit.duration_steps * tps))
                events.append((abs_tick, "note_on", hit.pitch, hit.velocity))
                events.append((abs_tick + dur_ticks, "note_off", hit.pitch, 0))

            events.sort(key=lambda e: (e[0], 0 if e[1] == "note_off" else 1))

            prev_tick = 0
            for abs_tick, msg_type, note, vel in events:
                delta = max(0, abs_tick - prev_tick)
                prev_tick = abs_tick
                if msg_type == "note_on":
                    bass_track.append(mido.Message(
                        "note_on", channel=BASS_CHANNEL, note=note, velocity=vel, time=delta
                    ))
                else:
                    bass_track.append(mido.Message(
                        "note_off", channel=BASS_CHANNEL, note=note, velocity=0, time=delta
                    ))

            bass_track.append(mido.MetaMessage("end_of_track", time=0))
            mid.tracks.append(bass_track)

        # Harmony track (channel 1)
        HARMONY_CHANNEL = 1
        if arrangement.harmony and arrangement.harmony.hits:
            harmony_track = mido.MidiTrack()
            harmony_track.name = arrangement.harmony.instrument_name or "Harmony"
            harmony_track.append(mido.MetaMessage(
                "track_name", name=harmony_track.name, time=0
            ))
            harmony_track.append(mido.Message(
                "program_change", channel=HARMONY_CHANNEL,
                program=arrangement.harmony.midi_program, time=0
            ))

            events = []
            for hit in arrangement.harmony.hits:
                abs_tick = int(hit.step * tps + hit.tick_offset)
                abs_tick = max(0, abs_tick)
                dur_ticks = max(1, int(hit.duration_steps * tps))
                for pitch in hit.pitches:
                    events.append((abs_tick, "note_on", pitch, hit.velocity))
                    events.append((abs_tick + dur_ticks, "note_off", pitch, 0))

            events.sort(key=lambda e: (e[0], 0 if e[1] == "note_off" else 1))

            prev_tick = 0
            for abs_tick, msg_type, note, vel in events:
                delta = max(0, abs_tick - prev_tick)
                prev_tick = abs_tick
                if msg_type == "note_on":
                    harmony_track.append(mido.Message(
                        "note_on", channel=HARMONY_CHANNEL, note=note, velocity=vel, time=delta
                    ))
                else:
                    harmony_track.append(mido.Message(
                        "note_off", channel=HARMONY_CHANNEL, note=note, velocity=0, time=delta
                    ))

            harmony_track.append(mido.MetaMessage("end_of_track", time=0))
            mid.tracks.append(harmony_track)

        mid.save(path)

    def _export_full_builtin(self, arrangement, path: str) -> None:
        """Fallback: export full arrangement using pure-Python writer."""
        tpb = 480
        tempo = int(60_000_000 / arrangement.bpm)
        tps = tpb // 4

        events = []

        # Drum events (channel 9)
        if arrangement.drums:
            raw = arrangement.drums.to_raw_beat()
            for hit in raw.hits:
                abs_tick = int(hit.step * tps + hit.tick_offset)
                abs_tick = max(0, abs_tick)
                events.append((abs_tick,     0x99, hit.midi_note, hit.velocity))
                events.append((abs_tick + 1, 0x89, hit.midi_note, 0))

        # Bass events (channel 0)
        if arrangement.bass:
            for hit in arrangement.bass.hits:
                abs_tick = int(hit.step * tps + hit.tick_offset)
                abs_tick = max(0, abs_tick)
                dur_ticks = max(1, int(hit.duration_steps * tps))
                events.append((abs_tick, 0x90, hit.pitch, hit.velocity))
                events.append((abs_tick + dur_ticks, 0x80, hit.pitch, 0))

        # Harmony events (channel 1)
        if arrangement.harmony:
            for hit in arrangement.harmony.hits:
                abs_tick = int(hit.step * tps + hit.tick_offset)
                abs_tick = max(0, abs_tick)
                dur_ticks = max(1, int(hit.duration_steps * tps))
                for pitch in hit.pitches:
                    events.append((abs_tick, 0x91, pitch, hit.velocity))
                    events.append((abs_tick + dur_ticks, 0x81, pitch, 0))

        events.sort(key=lambda e: e[0])

        # Build track bytes
        track_bytes = bytearray()
        track_bytes += self._meta_event(0, 0x51, struct.pack(">I", tempo)[1:])
        track_bytes += self._meta_event(0, 0x58, bytes([4, 2, 24, 8]))

        prev_tick = 0
        for abs_tick, status, note, vel in events:
            delta = max(0, abs_tick - prev_tick)
            prev_tick = abs_tick
            track_bytes += self._varlen(delta)
            track_bytes += bytes([status, note, vel])

        track_bytes += self._meta_event(0, 0x2F, b"")

        header = b"MThd" + struct.pack(">IHHH", 6, 0, 1, tpb)
        track_chunk = b"MTrk" + struct.pack(">I", len(track_bytes)) + bytes(track_bytes)

        with open(path, "wb") as f:
            f.write(header + track_chunk)

    @staticmethod
    def _meta_event(delta: int, meta_type: int, data: bytes) -> bytes:
        def varlen(v):
            r = [v & 0x7F]; v >>= 7
            while v: r.insert(0, (v & 0x7F) | 0x80); v >>= 7
            return bytes(r)
        return varlen(delta) + bytes([0xFF, meta_type]) + varlen(len(data)) + data
