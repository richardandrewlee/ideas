"""
Instrument Identifier
----------------------
Classifies MIDI tracks into musical roles: drums, bass, melody,
chords/pads, percussion, etc.

Uses GM program numbers when available, falls back to heuristics
based on note range, polyphony, and channel.
"""

import logging
from typing import Optional

from .midi_parser import ParsedMidi, MidiTrack
from .song_dna import InstrumentTrack

logger = logging.getLogger(__name__)


# GM Program number → category mapping
GM_CATEGORIES: dict[range, str] = {
    range(0, 8):    "piano",
    range(8, 16):   "chromatic_percussion",
    range(16, 24):  "organ",
    range(24, 32):  "guitar",
    range(32, 40):  "bass",
    range(40, 48):  "strings",
    range(48, 56):  "ensemble",
    range(56, 64):  "brass",
    range(64, 72):  "reed",
    range(72, 80):  "pipe",
    range(80, 88):  "synth_lead",
    range(88, 96):  "synth_pad",
    range(96, 104): "synth_effects",
    range(104, 112): "ethnic",
    range(112, 120): "percussive",
    range(120, 128): "sound_effects",
}

# Roles that are primarily bass
BASS_PROGRAMS = set(range(32, 40))  # GM bass instruments
BASS_NAMES = {"bass", "bass guitar", "electric bass", "synth bass", "sub bass", "808"}

# Roles that are primarily melodic leads
LEAD_PROGRAMS = set(range(80, 88))  # Synth leads
LEAD_CATEGORIES = {"synth_lead", "pipe", "reed", "brass"}

# Roles that are pads/chords
PAD_PROGRAMS = set(range(88, 96))  # Synth pads
PAD_CATEGORIES = {"synth_pad", "organ", "ensemble", "strings"}


def _program_to_category(program: int) -> str:
    """Map a GM program number (0-127) to an instrument category string."""
    for r, cat in GM_CATEGORIES.items():
        if program in r:
            return cat
    return "unknown"


class InstrumentIdentifier:
    """Classifies all tracks in a parsed MIDI into musical roles."""

    def identify(self, parsed: ParsedMidi) -> list[InstrumentTrack]:
        """Classify every track in the parsed MIDI.

        Returns a list of InstrumentTrack objects with name, role,
        MIDI program, note stats, etc.
        """
        results: list[InstrumentTrack] = []
        non_drum_tracks: list[tuple[int, MidiTrack, InstrumentTrack]] = []

        for idx, track in enumerate(parsed.tracks):
            if not track.notes:
                continue

            inst = self._classify_track(track)
            results.append(inst)

            if not inst.is_drum:
                non_drum_tracks.append((idx, track, inst))

        # Second pass: resolve roles among non-drum tracks
        self._resolve_roles(non_drum_tracks, results)

        return results

    def _classify_track(self, track: MidiTrack) -> InstrumentTrack:
        """Initial classification of a single track."""
        notes = track.notes
        if not notes:
            return InstrumentTrack(name="empty", channel=track.channel or 0)

        pitches = [n.pitch for n in notes]
        velocities = [n.velocity for n in notes]
        channels = set(n.channel for n in notes)
        pitch_classes = list(set(p % 12 for p in pitches))

        inst = InstrumentTrack(
            name="",
            midi_program=track.program or 0,
            channel=track.channel or 0,
            note_count=len(notes),
            lowest_note=min(pitches),
            highest_note=max(pitches),
            avg_velocity=sum(velocities) / len(velocities),
            pitch_classes_used=sorted(pitch_classes),
        )

        # Check for drums
        if 9 in channels or track.channel == 9:
            inst.is_drum = True
            inst.name = "drums"
            return inst

        # Check if notes are in GM drum range with channel 9
        drum_notes = sum(1 for n in notes if n.channel == 9)
        if drum_notes > len(notes) * 0.7:
            inst.is_drum = True
            inst.name = "drums"
            return inst

        # Use GM program if available
        if track.program is not None:
            category = _program_to_category(track.program)
            inst.name = category

            if track.program in BASS_PROGRAMS:
                inst.name = "bass"
            elif track.program in LEAD_PROGRAMS:
                inst.name = "synth_lead"
            elif track.program in PAD_PROGRAMS:
                inst.name = "synth_pad"

            return inst

        # Heuristic: name from track name
        if track.name:
            lower_name = track.name.lower()
            for bass_name in BASS_NAMES:
                if bass_name in lower_name:
                    inst.name = "bass"
                    return inst
            if "drum" in lower_name or "perc" in lower_name:
                inst.is_drum = True
                inst.name = "drums"
                return inst
            if "lead" in lower_name or "melody" in lower_name or "vocal" in lower_name:
                inst.name = "melody"
                return inst
            if "pad" in lower_name or "string" in lower_name or "choir" in lower_name:
                inst.name = "synth_pad"
                return inst
            if "guitar" in lower_name:
                inst.name = "guitar"
                return inst
            if "piano" in lower_name or "keys" in lower_name:
                inst.name = "piano"
                return inst

        # Leave name blank for second-pass heuristic resolution
        inst.name = "unknown"
        return inst

    def _resolve_roles(
        self,
        non_drum_tracks: list[tuple[int, MidiTrack, InstrumentTrack]],
        all_results: list[InstrumentTrack],
    ) -> None:
        """Second pass: assign roles to unknown tracks using heuristics."""
        has_bass = any(i.name == "bass" for i in all_results)
        has_melody = any(i.name in ("melody", "synth_lead") for i in all_results)

        unknowns = [(idx, trk, inst) for idx, trk, inst in non_drum_tracks if inst.name == "unknown"]

        if not unknowns:
            return

        # Sort by median pitch to help identify bass vs melody
        def median_pitch(trk: MidiTrack) -> float:
            pitches = sorted(n.pitch for n in trk.notes)
            mid = len(pitches) // 2
            return pitches[mid] if pitches else 60

        unknowns.sort(key=lambda x: median_pitch(x[1]))

        for idx, trk, inst in unknowns:
            med = median_pitch(trk)
            polyphony = self._avg_polyphony(trk)

            # Bass: lowest track, mostly monophonic, median < 48 (C3)
            if not has_bass and med < 48 and polyphony < 1.5:
                inst.name = "bass"
                has_bass = True
                continue

            # Melody: high register, mostly monophonic, varied pitches
            if not has_melody and polyphony < 2.0 and len(inst.pitch_classes_used) >= 5:
                inst.name = "melody"
                has_melody = True
                continue

            # Chords/pads: polyphonic
            if polyphony >= 2.0:
                inst.name = "chords"
                continue

            # Default: classify by register
            if med < 55:
                inst.name = "bass" if not has_bass else "low_instrument"
                if inst.name == "bass":
                    has_bass = True
            elif med < 72:
                inst.name = "mid_instrument"
            else:
                inst.name = "high_instrument"

    @staticmethod
    def _avg_polyphony(track: MidiTrack) -> float:
        """Estimate average simultaneous notes (polyphony) for a track.

        Groups notes into beat-sized windows and counts concurrent notes.
        """
        if not track.notes or len(track.notes) < 2:
            return 1.0

        # Use simple windowing: group by proximity in ticks
        notes = sorted(track.notes, key=lambda n: n.tick)
        window = 60  # ticks — roughly a 32nd note at 480 tpb
        groups: list[int] = []
        group_start = notes[0].tick
        group_count = 1

        for n in notes[1:]:
            if n.tick - group_start <= window:
                group_count += 1
            else:
                groups.append(group_count)
                group_start = n.tick
                group_count = 1
        groups.append(group_count)

        return sum(groups) / len(groups) if groups else 1.0
