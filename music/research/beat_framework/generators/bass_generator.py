"""
Bass Line Generator
--------------------
Generates bass lines that follow chord progressions with
genre-appropriate rhythmic patterns and note choices.

Bass lines are informed by:
- Chord progression (root notes, fifths, passing tones)
- Genre rhythm templates
- Section energy (busier in chorus, sparser in verse)
- Key and mode context
"""

import random
import logging
from dataclasses import dataclass, field
from typing import Optional

from ..analysis.song_dna import SongKey, Mode, ChordEvent, SectionType
from .arrangement import ArrangementTemplate, ArrangementSection

logger = logging.getLogger(__name__)


@dataclass
class BassHit:
    pitch: int              # MIDI note (typically 28-55)
    velocity: int
    step: int               # Absolute step in song
    duration_steps: int     # How many steps this note sustains
    tick_offset: int = 0


@dataclass
class BassLine:
    genre: str
    bpm: float
    key: Optional[SongKey] = None
    mode: Optional[Mode] = None
    hits: list[BassHit] = field(default_factory=list)
    steps_per_bar: int = 16
    midi_program: int = 33  # GM Electric Bass (finger)


# Per-genre bass rhythm patterns (probability per 16th note step in one bar)
BASS_RHYTHM_TEMPLATES: dict[str, dict] = {
    "house": {
        "pattern": [1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0, 0, 0, 0],
        "octave": 2,
        "style": "root_pump",
        "program": 38,  # Synth Bass 1
    },
    "techno": {
        "pattern": [1.0, 0, 0, 0.3, 0, 0, 1.0, 0, 0, 0.3, 0, 0, 1.0, 0, 0, 0],
        "octave": 2,
        "style": "driving",
        "program": 38,
    },
    "rock": {
        "pattern": [1.0, 0, 0, 0, 0.3, 0, 0, 0, 1.0, 0, 0, 0, 0.3, 0, 0, 0],
        "octave": 2,
        "style": "root_fifth",
        "program": 33,  # Electric Bass (finger)
    },
    "hip-hop": {
        "pattern": [0.9, 0, 0, 0.3, 0, 0, 0.7, 0, 0, 0, 0.4, 0, 0, 0, 0, 0.3],
        "octave": 1,
        "style": "syncopated_808",
        "program": 38,
    },
    "reggae": {
        "pattern": [0.0, 0, 0, 0, 0.9, 0, 0, 0, 0.0, 0, 0, 0, 0.7, 0, 0.4, 0],
        "octave": 2,
        "style": "offbeat",
        "program": 33,
    },
    "jazz": {
        "pattern": [0.9, 0, 0, 0, 0.8, 0, 0, 0, 0.9, 0, 0, 0, 0.8, 0, 0.5, 0],
        "octave": 2,
        "style": "walking",
        "program": 32,  # Acoustic Bass
    },
    "blues": {
        "pattern": [0.9, 0, 0, 0, 0.7, 0, 0, 0, 0.9, 0, 0, 0, 0.7, 0, 0.5, 0],
        "octave": 2,
        "style": "walking",
        "program": 32,
    },
    "pop": {
        "pattern": [1.0, 0, 0, 0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 0, 0, 0],
        "octave": 2,
        "style": "root_simple",
        "program": 33,
    },
    "funk": {
        "pattern": [0.9, 0, 0.6, 0, 0.3, 0, 0.7, 0, 0, 0.5, 0, 0, 0.8, 0, 0.4, 0.3],
        "octave": 2,
        "style": "syncopated",
        "program": 36,  # Slap Bass 1
    },
    "metal": {
        "pattern": [1.0, 1.0, 0, 1.0, 1.0, 0, 1.0, 1.0, 0, 1.0, 1.0, 0, 1.0, 1.0, 0, 1.0],
        "octave": 1,
        "style": "chugging",
        "program": 33,
    },
    "drum-and-bass": {
        "pattern": [0.9, 0, 0, 0, 0, 0, 0.8, 0, 0, 0, 0.7, 0, 0, 0, 0, 0.6],
        "octave": 1,
        "style": "reese",
        "program": 38,
    },
}

DEFAULT_RHYTHM = {
    "pattern": [1.0, 0, 0, 0, 0.5, 0, 0, 0, 1.0, 0, 0, 0, 0.5, 0, 0, 0],
    "octave": 2,
    "style": "root_simple",
    "program": 33,
}

# Scale intervals for passing tones
MAJOR_SCALE = [0, 2, 4, 5, 7, 9, 11]
MINOR_SCALE = [0, 2, 3, 5, 7, 8, 10]


class BassGenerator:
    """Generates bass lines following chord progressions."""

    def __init__(self, seed: Optional[int] = None):
        self.rng = random.Random(seed)

    def generate(
        self,
        chord_progression: list[ChordEvent],
        arrangement: ArrangementTemplate,
        genre: str,
        key: Optional[SongKey] = None,
        mode: Optional[Mode] = None,
        bpm: float = 120.0,
    ) -> BassLine:
        """Generate a bass line following the chord progression and arrangement."""
        rhythm_template = BASS_RHYTHM_TEMPLATES.get(genre.lower(), DEFAULT_RHYTHM)

        bass = BassLine(
            genre=genre,
            bpm=bpm,
            key=key,
            mode=mode,
            midi_program=rhythm_template.get("program", 33),
        )

        octave = rhythm_template["octave"]
        pattern = rhythm_template["pattern"]
        style = rhythm_template["style"]
        steps_per_bar = bass.steps_per_bar

        current_bar = 0
        for section in arrangement.sections:
            section_density = section.drum_density

            for bar_in_section in range(section.bars):
                abs_bar = current_bar + bar_in_section
                bar_start_step = abs_bar * steps_per_bar

                # Find the chord for this bar
                chord = self._get_chord_at_bar(chord_progression, abs_bar, steps_per_bar, key)
                root_pitch = self._chord_root_to_pitch(chord, octave)

                for step_in_bar in range(steps_per_bar):
                    prob = pattern[step_in_bar % len(pattern)] * section_density

                    if self.rng.random() < prob:
                        # Choose pitch: primarily root, sometimes fifth or passing tone
                        pitch = self._choose_pitch(
                            root_pitch, chord, style, step_in_bar, key, mode
                        )
                        vel = self._sample_velocity(section.energy)
                        dur = self._note_duration(style, step_in_bar, steps_per_bar)

                        bass.hits.append(BassHit(
                            pitch=pitch,
                            velocity=vel,
                            step=bar_start_step + step_in_bar,
                            duration_steps=dur,
                        ))

            current_bar += section.bars

        logger.debug(f"Generated bass line: {len(bass.hits)} notes, style={style}")
        return bass

    def _get_chord_at_bar(
        self,
        chords: list[ChordEvent],
        bar: int,
        steps_per_bar: int,
        key: Optional[SongKey],
    ) -> Optional[ChordEvent]:
        """Find the chord active at a given bar."""
        if not chords:
            return None
        for chord in reversed(chords):
            if chord.start_bar is not None and chord.start_bar <= bar:
                return chord
        return chords[0] if chords else None

    def _chord_root_to_pitch(self, chord: Optional[ChordEvent], octave: int) -> int:
        """Convert chord root pitch class to MIDI note in the bass register."""
        if chord is None:
            return 36 + (octave - 2) * 12  # Default C2
        return chord.root + (octave + 1) * 12

    def _choose_pitch(
        self,
        root_pitch: int,
        chord: Optional[ChordEvent],
        style: str,
        step_in_bar: int,
        key: Optional[SongKey],
        mode: Optional[Mode],
    ) -> int:
        """Choose the bass note pitch based on style and harmonic context."""
        roll = self.rng.random()

        if style == "walking" and step_in_bar % 4 == 2:
            # Walking bass: passing tones on off-beats
            scale = MINOR_SCALE if mode == Mode.MINOR else MAJOR_SCALE
            interval = self.rng.choice(scale)
            return root_pitch + interval

        if style in ("root_fifth", "chugging") and step_in_bar % 8 == 4:
            return root_pitch + 7  # Perfect fifth

        if roll < 0.75:
            return root_pitch  # Root note (most common)
        elif roll < 0.90:
            return root_pitch + 7  # Fifth
        else:
            # Octave jump
            return root_pitch + 12 if self.rng.random() < 0.5 else root_pitch - 12

    def _sample_velocity(self, energy: float) -> int:
        base = int(60 + energy * 50)  # 60-110
        return max(1, min(127, base + self.rng.randint(-8, 8)))

    def _note_duration(self, style: str, step_in_bar: int, steps_per_bar: int) -> int:
        """Determine note duration in steps."""
        if style in ("root_pump", "chugging"):
            return 2  # Short, punchy
        elif style == "walking":
            return 3  # Slightly longer
        elif style in ("syncopated", "syncopated_808", "reese"):
            return self.rng.choice([2, 3, 4])
        else:
            return 4  # Quarter note
