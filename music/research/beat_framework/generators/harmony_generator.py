"""
Harmony Generator
------------------
Generates harmonic parts (chords/pads) that follow the chord progression
with genre-appropriate voicings and rhythmic patterns.

Supports different voicing styles:
- Pad: sustained chords (house, ambient)
- Power chord: root + 5th (rock, metal)
- Stabs: short rhythmic hits (hip-hop, funk)
- Extended voicing: 7ths, 9ths (jazz)
"""

import random
import logging
from dataclasses import dataclass, field
from typing import Optional

from ..analysis.song_dna import SongKey, Mode, ChordEvent, SectionType
from .arrangement import ArrangementTemplate, ArrangementSection

logger = logging.getLogger(__name__)


@dataclass
class HarmonyHit:
    pitches: list[int]      # Chord voicing (3-5 MIDI notes)
    velocity: int
    step: int               # Absolute step in song
    duration_steps: int     # Sustain length
    tick_offset: int = 0


@dataclass
class HarmonyPart:
    genre: str
    instrument_name: str
    midi_program: int
    hits: list[HarmonyHit] = field(default_factory=list)
    steps_per_bar: int = 16


# Chord quality → intervals from root
CHORD_INTERVALS: dict[str, list[int]] = {
    "major":  [0, 4, 7],
    "minor":  [0, 3, 7],
    "dom7":   [0, 4, 7, 10],
    "min7":   [0, 3, 7, 10],
    "maj7":   [0, 4, 7, 11],
    "dim":    [0, 3, 6],
    "dim7":   [0, 3, 6, 9],
    "aug":    [0, 4, 8],
    "sus2":   [0, 2, 7],
    "sus4":   [0, 5, 7],
    "5":      [0, 7],
}

# Genre voicing configurations
VOICING_STYLES: dict[str, dict] = {
    "house": {
        "program": 89,       # Pad 2 (warm)
        "style": "pad",
        "register": (60, 84),
        "instrument": "synth_pad",
    },
    "techno": {
        "program": 81,       # Lead 2 (sawtooth)
        "style": "stab",
        "register": (55, 79),
        "instrument": "synth_lead",
    },
    "rock": {
        "program": 29,       # Overdriven Guitar
        "style": "power_chord",
        "register": (48, 72),
        "instrument": "guitar",
    },
    "hip-hop": {
        "program": 0,        # Acoustic Grand Piano
        "style": "stab",
        "register": (55, 79),
        "instrument": "piano",
    },
    "reggae": {
        "program": 16,       # Drawbar Organ
        "style": "skank",
        "register": (60, 84),
        "instrument": "organ",
    },
    "jazz": {
        "program": 0,        # Acoustic Grand Piano
        "style": "extended",
        "register": (48, 72),
        "instrument": "piano",
    },
    "blues": {
        "program": 0,        # Acoustic Grand Piano
        "style": "extended",
        "register": (48, 72),
        "instrument": "piano",
    },
    "pop": {
        "program": 0,        # Acoustic Grand Piano
        "style": "block",
        "register": (55, 79),
        "instrument": "piano",
    },
    "funk": {
        "program": 4,        # Electric Piano 1
        "style": "stab",
        "register": (55, 79),
        "instrument": "electric_piano",
    },
    "metal": {
        "program": 30,       # Distortion Guitar
        "style": "power_chord",
        "register": (40, 64),
        "instrument": "guitar",
    },
    "soul": {
        "program": 4,        # Electric Piano 1
        "style": "block",
        "register": (55, 79),
        "instrument": "electric_piano",
    },
    "drum-and-bass": {
        "program": 89,       # Pad 2 (warm)
        "style": "pad",
        "register": (55, 79),
        "instrument": "synth_pad",
    },
}

DEFAULT_VOICING = {
    "program": 0,
    "style": "block",
    "register": (55, 79),
    "instrument": "piano",
}

# Rhythm patterns per style (probability per beat, 4 beats per bar)
RHYTHM_PATTERNS: dict[str, list[float]] = {
    "pad":         [1.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],  # Whole note
    "block":       [1.0, 0, 0, 0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 0, 0, 0],  # Half notes
    "stab":        [1.0, 0, 0, 0, 0, 0, 0.7, 0, 0, 0, 0, 0, 0.5, 0, 0, 0],  # Syncopated
    "power_chord": [1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0, 0, 0, 0],  # Quarter notes
    "skank":       [0, 0, 1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0, 0],  # Off-beat
    "extended":    [1.0, 0, 0, 0, 0, 0, 0, 0, 0.6, 0, 0, 0, 0, 0, 0, 0],  # Sparse
}


class HarmonyGenerator:
    """Generates harmonic parts following chord progressions."""

    def __init__(self, seed: Optional[int] = None):
        self.rng = random.Random(seed)

    def generate(
        self,
        chord_progression: list[ChordEvent],
        arrangement: ArrangementTemplate,
        genre: str,
        key: Optional[SongKey] = None,
        bpm: float = 120.0,
    ) -> HarmonyPart:
        """Generate a harmony part following the chord progression."""
        voicing_config = VOICING_STYLES.get(genre.lower(), DEFAULT_VOICING)
        style = voicing_config["style"]
        register = voicing_config["register"]
        rhythm = RHYTHM_PATTERNS.get(style, RHYTHM_PATTERNS["block"])

        part = HarmonyPart(
            genre=genre,
            instrument_name=voicing_config["instrument"],
            midi_program=voicing_config["program"],
        )

        steps_per_bar = part.steps_per_bar
        current_bar = 0

        for section in arrangement.sections:
            section_density = section.drum_density

            # Skip harmony in breakdown sections (let it breathe)
            if section.section_type == SectionType.BREAKDOWN and self.rng.random() < 0.5:
                current_bar += section.bars
                continue

            for bar_in_section in range(section.bars):
                abs_bar = current_bar + bar_in_section
                bar_start_step = abs_bar * steps_per_bar

                chord = self._get_chord_at_bar(chord_progression, abs_bar, key)
                if chord is None:
                    continue

                for step_in_bar in range(steps_per_bar):
                    prob = rhythm[step_in_bar % len(rhythm)] * section_density

                    if self.rng.random() < prob:
                        pitches = self._voice_chord(chord, style, register)
                        vel = self._sample_velocity(section.energy, style)
                        dur = self._note_duration(style, step_in_bar, steps_per_bar)

                        part.hits.append(HarmonyHit(
                            pitches=pitches,
                            velocity=vel,
                            step=bar_start_step + step_in_bar,
                            duration_steps=dur,
                        ))

            current_bar += section.bars

        logger.debug(f"Generated harmony: {len(part.hits)} chord hits, style={style}")
        return part

    def _get_chord_at_bar(
        self,
        chords: list[ChordEvent],
        bar: int,
        key: Optional[SongKey],
    ) -> Optional[ChordEvent]:
        if not chords:
            # Generate a default chord based on key
            if key:
                return ChordEvent(root=key.value, quality="major")
            return ChordEvent(root=0, quality="major")
        for chord in reversed(chords):
            if chord.start_bar is not None and chord.start_bar <= bar:
                return chord
        return chords[0]

    def _voice_chord(
        self,
        chord: ChordEvent,
        style: str,
        register: tuple[int, int],
    ) -> list[int]:
        """Voice a chord within the register according to style."""
        intervals = CHORD_INTERVALS.get(chord.quality, [0, 4, 7])

        if style == "power_chord":
            intervals = [0, 7]  # Root + fifth only
        elif style == "extended" and len(intervals) == 3:
            # Add a 7th for jazz
            if chord.quality == "major":
                intervals = [0, 4, 7, 11]  # maj7
            elif chord.quality == "minor":
                intervals = [0, 3, 7, 10]  # min7

        # Build pitches starting from register bottom
        root = chord.root
        base_octave = register[0] // 12
        pitches = []

        for interval in intervals:
            pitch = root + interval + base_octave * 12
            # Ensure within register
            while pitch < register[0]:
                pitch += 12
            while pitch > register[1]:
                pitch -= 12
            pitches.append(pitch)

        return sorted(set(pitches))

    def _sample_velocity(self, energy: float, style: str) -> int:
        if style == "pad":
            base = int(50 + energy * 30)  # Softer for pads
        elif style == "stab":
            base = int(70 + energy * 40)  # Punchy for stabs
        else:
            base = int(60 + energy * 35)
        return max(1, min(127, base + self.rng.randint(-5, 5)))

    def _note_duration(self, style: str, step_in_bar: int, steps_per_bar: int) -> int:
        if style == "pad":
            return steps_per_bar  # Whole bar sustain
        elif style == "stab":
            return self.rng.choice([1, 2])  # Very short
        elif style == "power_chord":
            return 3  # Slightly longer than 16th
        elif style == "skank":
            return 1  # Very short chops
        elif style == "extended":
            return self.rng.choice([4, 8])  # Quarter to half note
        else:
            return 4  # Quarter note default
