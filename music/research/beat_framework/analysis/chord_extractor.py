"""
Chord Extractor
----------------
Extracts chord progressions from MIDI by analyzing simultaneous notes
in non-drum, non-bass tracks.

Algorithm:
1. Collect all non-drum, non-bass track notes
2. Segment into beat-aligned windows
3. For each window, collect pitch classes of simultaneous notes
4. Template-match against known chord types (all 12 rotations)
5. Merge consecutive identical chords
"""

import logging
from typing import Optional

from .midi_parser import ParsedMidi, MidiTrack
from .song_dna import ChordEvent, InstrumentTrack

logger = logging.getLogger(__name__)


# Chord templates: intervals from root → quality name
# Represented as frozensets of semitone intervals from root
CHORD_TEMPLATES: dict[frozenset[int], str] = {
    frozenset({0, 4, 7}):       "major",
    frozenset({0, 3, 7}):       "minor",
    frozenset({0, 4, 7, 10}):   "dom7",
    frozenset({0, 3, 7, 10}):   "min7",
    frozenset({0, 4, 7, 11}):   "maj7",
    frozenset({0, 3, 6}):       "dim",
    frozenset({0, 3, 6, 9}):    "dim7",
    frozenset({0, 4, 8}):       "aug",
    frozenset({0, 2, 7}):       "sus2",
    frozenset({0, 5, 7}):       "sus4",
    frozenset({0, 4}):          "major",     # Dyad (power + third)
    frozenset({0, 3}):          "minor",     # Minor dyad
    frozenset({0, 7}):          "5",         # Power chord
}


class ChordExtractor:
    """Extracts chord progressions from MIDI harmonic content."""

    def extract(
        self,
        parsed: ParsedMidi,
        ticks_per_beat: int,
        instruments: Optional[list[InstrumentTrack]] = None,
    ) -> list[ChordEvent]:
        """Extract chord progression from a parsed MIDI file.

        Args:
            parsed: The parsed MIDI data.
            ticks_per_beat: Ticks per quarter note.
            instruments: Optional instrument classification to filter tracks.

        Returns:
            List of ChordEvent objects representing the chord progression.
        """
        # Collect harmonic notes (exclude drums and bass)
        harmonic_notes = self._get_harmonic_notes(parsed, instruments)

        if not harmonic_notes:
            return []

        # Segment into beat-aligned windows
        windows = self._segment_by_beat(harmonic_notes, ticks_per_beat)

        if not windows:
            return []

        # Identify chords per window
        raw_chords: list[Optional[ChordEvent]] = []
        for tick, pitch_classes in windows:
            chord = self._identify_chord(pitch_classes, tick, ticks_per_beat)
            raw_chords.append(chord)

        # Merge consecutive identical chords
        merged = self._merge_consecutive(raw_chords, ticks_per_beat, parsed)

        return merged

    def _get_harmonic_notes(
        self,
        parsed: ParsedMidi,
        instruments: Optional[list[InstrumentTrack]],
    ) -> list:
        """Get all notes suitable for chord detection (no drums, no bass)."""
        # Build set of channels/tracks to exclude
        exclude_channels: set[int] = {9}  # Always exclude drum channel

        if instruments:
            for inst in instruments:
                if inst.is_drum or inst.name == "bass":
                    exclude_channels.add(inst.channel)

        notes = []
        for track in parsed.tracks:
            # Skip if track is drums or bass by channel
            if track.channel in exclude_channels:
                continue
            # Skip if program indicates bass
            if track.program is not None and 32 <= track.program <= 39:
                continue

            for note in track.notes:
                if note.channel not in exclude_channels:
                    notes.append(note)

        notes.sort(key=lambda n: n.tick)
        return notes

    def _segment_by_beat(
        self,
        notes: list,
        ticks_per_beat: int,
    ) -> list[tuple[int, list[int]]]:
        """Group notes into beat-aligned windows, return (tick, pitch_classes) per window."""
        if not notes:
            return []

        max_tick = max(n.tick for n in notes)
        windows: list[tuple[int, list[int]]] = []

        beat_tick = 0
        while beat_tick <= max_tick:
            window_end = beat_tick + ticks_per_beat
            # Collect pitch classes of notes in this beat window
            pcs = set()
            for note in notes:
                if beat_tick <= note.tick < window_end:
                    pcs.add(note.pitch % 12)
                elif note.tick >= window_end:
                    break

            if pcs:
                windows.append((beat_tick, sorted(pcs)))

            beat_tick = window_end

        return windows

    def _identify_chord(
        self,
        pitch_classes: list[int],
        tick: int,
        ticks_per_beat: int,
    ) -> Optional[ChordEvent]:
        """Identify the chord from a set of pitch classes via template matching.

        Tries all 12 possible roots and matches against chord templates.
        Returns the best match or None.
        """
        if len(pitch_classes) < 2:
            return None

        pc_set = set(pitch_classes)
        best_match: Optional[ChordEvent] = None
        best_score = 0

        for root in range(12):
            # Transpose pitch classes relative to this root
            intervals = frozenset((pc - root) % 12 for pc in pc_set)

            for template, quality in CHORD_TEMPLATES.items():
                # How many template notes are present
                match_count = len(template & intervals)
                # Penalize extra notes not in template
                extra_count = len(intervals - template)

                if match_count < len(template):
                    continue  # Must have all template notes

                score = match_count * 2 - extra_count

                if score > best_score:
                    best_score = score
                    best_match = ChordEvent(
                        root=root,
                        quality=quality,
                        start_tick=tick,
                        duration_ticks=ticks_per_beat,
                        confidence=min(1.0, score / (len(template) * 2)),
                    )

        return best_match

    def _merge_consecutive(
        self,
        chords: list[Optional[ChordEvent]],
        ticks_per_beat: int,
        parsed: ParsedMidi,
    ) -> list[ChordEvent]:
        """Merge consecutive identical chords into single events with extended duration."""
        if not chords:
            return []

        merged: list[ChordEvent] = []
        current: Optional[ChordEvent] = None

        for chord in chords:
            if chord is None:
                continue

            if current is None:
                current = ChordEvent(
                    root=chord.root, quality=chord.quality,
                    start_tick=chord.start_tick,
                    duration_ticks=chord.duration_ticks,
                    confidence=chord.confidence,
                )
            elif current.root == chord.root and current.quality == chord.quality:
                # Extend duration
                current.duration_ticks += ticks_per_beat
                # Average confidence
                current.confidence = (current.confidence + chord.confidence) / 2
            else:
                # Compute bar number
                current.start_bar = parsed.tick_to_bar(current.start_tick)
                merged.append(current)
                current = ChordEvent(
                    root=chord.root, quality=chord.quality,
                    start_tick=chord.start_tick,
                    duration_ticks=chord.duration_ticks,
                    confidence=chord.confidence,
                )

        if current is not None:
            current.start_bar = parsed.tick_to_bar(current.start_tick)
            merged.append(current)

        return merged
