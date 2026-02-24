"""
Multi-Instrument Generator
---------------------------
Orchestrates all generators (drums, bass, harmony) to produce
a complete multi-instrument song arrangement.

This is the top-level generator for full production output.
"""

import random
import logging
from dataclasses import dataclass, field
from typing import Optional

from .song_generator import SongGenerator, SongBeat
from .bass_generator import BassGenerator, BassLine
from .harmony_generator import HarmonyGenerator, HarmonyPart
from .arrangement import ArrangementEngine, ArrangementTemplate
from ..analysis.pattern_analyzer import GenreProfile
from ..analysis.song_dna import SongKey, Mode, ChordEvent, SongDNA

logger = logging.getLogger(__name__)


@dataclass
class FullArrangement:
    """Complete multi-instrument song output."""
    genre: str
    year: int
    bpm: float
    key: Optional[SongKey] = None
    mode: Optional[Mode] = None
    arrangement: Optional[ArrangementTemplate] = None
    drums: Optional[SongBeat] = None
    bass: Optional[BassLine] = None
    harmony: Optional[HarmonyPart] = None
    chord_progression: list[ChordEvent] = field(default_factory=list)

    @property
    def total_bars(self) -> int:
        if self.arrangement:
            return self.arrangement.total_bars
        return 0


class MultiInstrumentGenerator:
    """Generates complete multi-instrument arrangements."""

    def __init__(self, seed: Optional[int] = None):
        self.song_gen = SongGenerator(seed=seed)
        self.bass_gen = BassGenerator(seed=seed)
        self.harmony_gen = HarmonyGenerator(seed=seed)
        self.arrangement_engine = ArrangementEngine()
        self.rng = random.Random(seed)

    def generate(
        self,
        profile: GenreProfile,
        genre: str,
        year: int,
        key: Optional[SongKey] = None,
        mode: Optional[Mode] = None,
        chord_progression: Optional[list[ChordEvent]] = None,
        arrangement: Optional[ArrangementTemplate] = None,
        include_bass: bool = True,
        include_harmony: bool = True,
    ) -> FullArrangement:
        """Generate a complete multi-instrument arrangement.

        Args:
            profile: Genre profile for drum patterns.
            genre: Genre name.
            year: Year.
            key: Song key (if None, generates in C major).
            mode: Mode (major/minor).
            chord_progression: Chord progression (if None, generates a default).
            arrangement: Song structure (if None, uses genre default).
            include_bass: Whether to generate bass line.
            include_harmony: Whether to generate harmony part.

        Returns:
            A FullArrangement with drums, bass, and harmony.
        """
        if arrangement is None:
            arrangement = self.arrangement_engine.get_template(genre)

        if key is None:
            key = SongKey.C
        if mode is None:
            mode = Mode.MAJOR

        if chord_progression is None:
            chord_progression = self._generate_default_progression(key, mode, arrangement)

        # Generate drums
        drums = self.song_gen.generate_song(profile=profile, arrangement=arrangement)

        result = FullArrangement(
            genre=genre,
            year=year,
            bpm=drums.bpm,
            key=key,
            mode=mode,
            arrangement=arrangement,
            drums=drums,
            chord_progression=chord_progression,
        )

        # Generate bass
        if include_bass:
            result.bass = self.bass_gen.generate(
                chord_progression=chord_progression,
                arrangement=arrangement,
                genre=genre,
                key=key,
                mode=mode,
                bpm=drums.bpm,
            )

        # Generate harmony
        if include_harmony:
            result.harmony = self.harmony_gen.generate(
                chord_progression=chord_progression,
                arrangement=arrangement,
                genre=genre,
                key=key,
                bpm=drums.bpm,
            )

        total_notes = (
            sum(len(s.hits) for s in drums.sections) +
            (len(result.bass.hits) if result.bass else 0) +
            (len(result.harmony.hits) if result.harmony else 0)
        )
        logger.info(
            f"Full arrangement: {genre}/{year}, {arrangement.total_bars} bars, "
            f"key={key.label} {mode.value}, {total_notes} total notes"
        )

        return result

    def from_song_dna(
        self,
        dna: SongDNA,
        profile: GenreProfile,
        include_bass: bool = True,
        include_harmony: bool = True,
    ) -> FullArrangement:
        """Generate a full arrangement informed by an analyzed song's DNA."""
        arrangement = self.arrangement_engine.from_song_dna(dna)

        return self.generate(
            profile=profile,
            genre=dna.genre,
            year=dna.year,
            key=dna.key,
            mode=dna.mode,
            chord_progression=dna.chord_progression or None,
            arrangement=arrangement,
            include_bass=include_bass,
            include_harmony=include_harmony,
        )

    def _generate_default_progression(
        self,
        key: SongKey,
        mode: Mode,
        arrangement: ArrangementTemplate,
    ) -> list[ChordEvent]:
        """Generate a simple chord progression when none is provided."""
        root = key.value

        if mode == Mode.MINOR:
            # i - VI - III - VII (common minor progression)
            progression = [
                (root, "minor"),
                ((root + 8) % 12, "major"),
                ((root + 3) % 12, "major"),
                ((root + 10) % 12, "major"),
            ]
        else:
            # I - V - vi - IV (most common pop progression)
            progression = [
                (root, "major"),
                ((root + 7) % 12, "major"),
                ((root + 9) % 12, "minor"),
                ((root + 5) % 12, "major"),
            ]

        # Distribute across bars
        chords: list[ChordEvent] = []
        current_bar = 0
        for section in arrangement.sections:
            for bar in range(section.bars):
                abs_bar = current_bar + bar
                chord_idx = bar % len(progression)
                chord_root, quality = progression[chord_idx]
                chords.append(ChordEvent(
                    root=chord_root,
                    quality=quality,
                    start_bar=abs_bar,
                    confidence=0.8,
                ))
            current_bar += section.bars

        return chords
