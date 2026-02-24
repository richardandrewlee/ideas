"""
Song Generator
---------------
Generates full-song percussion tracks with section-aware patterns,
transitions, fills, builds, and energy dynamics.

Wraps the StatisticalGenerator for bar-level generation but adds:
- Section awareness (different patterns per verse/chorus/bridge)
- Transitions between sections (fills, builds, crashes)
- Energy dynamics following the arrangement template
- Full-length output (3-5 minutes) instead of 2-8 bar loops
"""

import random
import logging
from dataclasses import dataclass, field
from typing import Optional

from .statistical_generator import StatisticalGenerator, RawBeat, RawHit, INSTRUMENT_TO_MIDI
from .arrangement import ArrangementTemplate, ArrangementSection
from ..analysis.pattern_analyzer import GenreProfile, PRIMARY_INSTRUMENTS
from ..analysis.song_dna import SectionType
from ..analysis.section_profile_builder import SectionDrumProfile, GenreArrangementProfile

logger = logging.getLogger(__name__)


@dataclass
class SectionBeat:
    """Drum pattern for one section of a song."""
    section_type: SectionType
    start_bar: int
    bars: int
    energy: float
    hits: list[RawHit] = field(default_factory=list)
    transition_hits: list[RawHit] = field(default_factory=list)


@dataclass
class SongBeat:
    """Full-song percussion track."""
    genre: str
    year: int
    bpm: float
    arrangement: ArrangementTemplate
    sections: list[SectionBeat] = field(default_factory=list)
    steps_per_bar: int = 16
    ticks_per_beat: int = 480

    @property
    def total_steps(self) -> int:
        return self.arrangement.total_bars * self.steps_per_bar

    @property
    def total_bars(self) -> int:
        return self.arrangement.total_bars

    def to_raw_beat(self) -> RawBeat:
        """Flatten to a single RawBeat for backward-compatible export."""
        beat = RawBeat(
            genre=self.genre,
            year=self.year,
            bpm=self.bpm,
            grid_steps=self.total_steps,
            steps_per_bar=self.steps_per_bar,
            ticks_per_beat=self.ticks_per_beat,
        )
        for section in self.sections:
            beat.hits.extend(section.hits)
            beat.hits.extend(section.transition_hits)
        beat.hits.sort(key=lambda h: (h.step, h.instrument))
        return beat


class SongGenerator:
    """Generates full-song percussion tracks with section awareness."""

    def __init__(self, seed: Optional[int] = None):
        self.stat_gen = StatisticalGenerator(seed=seed)
        self.rng = random.Random(seed)

    def generate_song(
        self,
        profile: GenreProfile,
        arrangement: ArrangementTemplate,
        arrangement_profile: Optional[GenreArrangementProfile] = None,
    ) -> SongBeat:
        """Generate a full song percussion track.

        Args:
            profile: Base genre profile for drum patterns.
            arrangement: Song structure template.
            arrangement_profile: Optional per-section profiles for finer control.

        Returns:
            A SongBeat with section-aware percussion.
        """
        bpm = self.stat_gen._sample_bpm(profile)

        song = SongBeat(
            genre=profile.genre,
            year=profile.year,
            bpm=bpm,
            arrangement=arrangement,
            steps_per_bar=profile.steps_per_bar,
        )

        current_bar = 0

        for i, section_def in enumerate(arrangement.sections):
            # Get section-specific profile or scale base
            section_profile = self._get_section_profile(
                section_def, profile, arrangement_profile
            )

            # Generate the section
            section_beat = self._generate_section(
                section_def, section_profile, profile, current_bar
            )

            # Generate transition at end of section
            if section_def.has_fill_at_end and i < len(arrangement.sections) - 1:
                next_section = arrangement.sections[i + 1]
                transition = self._generate_transition(
                    section_def, next_section, profile, current_bar
                )
                section_beat.transition_hits = transition

            song.sections.append(section_beat)
            current_bar += section_def.bars

        total_hits = sum(len(s.hits) + len(s.transition_hits) for s in song.sections)
        logger.info(
            f"Generated full song: {arrangement.total_bars} bars, "
            f"{len(song.sections)} sections, {total_hits} hits at {bpm:.1f} BPM"
        )

        return song

    def _generate_section(
        self,
        section_def: ArrangementSection,
        section_profile: SectionDrumProfile,
        base_profile: GenreProfile,
        start_bar: int,
    ) -> SectionBeat:
        """Generate bars for a single section with density scaling."""
        section_beat = SectionBeat(
            section_type=section_def.section_type,
            start_bar=start_bar,
            bars=section_def.bars,
            energy=section_def.energy,
        )

        for bar_idx in range(section_def.bars):
            abs_bar = start_bar + bar_idx
            bar_start_step = abs_bar * base_profile.steps_per_bar

            # Fills on the last bar of each 4-bar phrase within the section
            is_phrase_end = ((bar_idx + 1) % 4 == 0) and bar_idx < section_def.bars - 1

            for step_in_bar in range(base_profile.steps_per_bar):
                abs_step = bar_start_step + step_in_bar
                grid_step = step_in_bar % base_profile.grid_steps

                in_fill_zone = is_phrase_end and step_in_bar >= (base_profile.steps_per_bar - 4)

                for inst in PRIMARY_INSTRUMENTS:
                    # Get probability from section profile
                    probs = section_profile.hit_probability.get(inst, [])
                    if not probs:
                        probs = base_profile.hit_probability.get(inst, [])
                    if not probs:
                        continue

                    prob = probs[grid_step % len(probs)]

                    # Add variation
                    delta = self.rng.uniform(-0.1, 0.1)
                    prob = max(0.0, min(1.0, prob + delta * prob))

                    if in_fill_zone:
                        prob = self.stat_gen._apply_fill_logic(
                            inst, step_in_bar, prob, base_profile.steps_per_bar
                        )

                    if self.rng.random() < prob:
                        vel_mean = section_profile.velocity_mean.get(
                            inst, base_profile.velocity_mean.get(inst, 80)
                        )
                        vel_std = section_profile.velocity_std.get(
                            inst, base_profile.velocity_std.get(inst, 10)
                        )
                        vel = max(1, min(127, int(self.rng.gauss(vel_mean, vel_std))))

                        section_beat.hits.append(RawHit(
                            instrument=inst,
                            midi_note=INSTRUMENT_TO_MIDI.get(inst, 38),
                            step=abs_step,
                            velocity=vel,
                            tick_offset=0,
                        ))

        return section_beat

    def _generate_transition(
        self,
        from_section: ArrangementSection,
        to_section: ArrangementSection,
        profile: GenreProfile,
        current_bar: int,
    ) -> list[RawHit]:
        """Generate transition hits between sections."""
        transition_type = from_section.transition_type
        if transition_type == "none":
            return []

        end_bar = current_bar + from_section.bars
        bar_start_step = (end_bar - 1) * profile.steps_per_bar

        if transition_type == "fill":
            return self._generate_fill(profile, bar_start_step)
        elif transition_type == "build":
            return self._generate_build(profile, bar_start_step, bars=2)
        elif transition_type == "crash":
            return self._generate_crash_accent(profile, end_bar)
        elif transition_type == "breakdown":
            return []  # Breakdown is handled by low density in the section itself

        return []

    def _generate_fill(self, profile: GenreProfile, bar_start_step: int) -> list[RawHit]:
        """Generate a 1-bar drum fill in the last 4 steps."""
        hits = []
        fill_start = bar_start_step + profile.steps_per_bar - 4

        # Tom cascade: high → mid → low
        tom_pattern = [
            ("tom_high", fill_start, 95),
            ("tom_mid",  fill_start + 1, 90),
            ("tom_low",  fill_start + 2, 85),
            ("snare",    fill_start + 3, 100),
        ]

        for inst, step, vel in tom_pattern:
            vel_var = max(1, min(127, vel + self.rng.randint(-8, 8)))
            hits.append(RawHit(
                instrument=inst,
                midi_note=INSTRUMENT_TO_MIDI.get(inst, 38),
                step=step,
                velocity=vel_var,
                tick_offset=0,
            ))

        return hits

    def _generate_build(self, profile: GenreProfile, bar_start_step: int, bars: int = 2) -> list[RawHit]:
        """Generate a multi-bar snare/hat build toward climax."""
        hits = []
        total_steps = bars * profile.steps_per_bar
        build_start = bar_start_step - (bars - 1) * profile.steps_per_bar

        for i in range(total_steps):
            abs_step = build_start + i
            progress = i / total_steps  # 0.0 → 1.0

            # Increasing density: start with quarter notes, end with 16ths
            if progress < 0.25:
                play = (i % 4 == 0)
            elif progress < 0.5:
                play = (i % 2 == 0)
            elif progress < 0.75:
                play = True
            else:
                play = True  # Full density

            if play:
                vel = int(60 + progress * 60)  # 60 → 120
                vel = max(1, min(127, vel + self.rng.randint(-5, 5)))
                hits.append(RawHit(
                    instrument="snare",
                    midi_note=INSTRUMENT_TO_MIDI["snare"],
                    step=abs_step,
                    velocity=vel,
                    tick_offset=0,
                ))

        return hits

    def _generate_crash_accent(self, profile: GenreProfile, target_bar: int) -> list[RawHit]:
        """Generate a crash cymbal on the downbeat of the next section."""
        step = target_bar * profile.steps_per_bar
        return [
            RawHit(
                instrument="crash",
                midi_note=INSTRUMENT_TO_MIDI["crash"],
                step=step,
                velocity=self.rng.randint(105, 120),
                tick_offset=0,
            ),
            RawHit(
                instrument="kick",
                midi_note=INSTRUMENT_TO_MIDI["kick"],
                step=step,
                velocity=self.rng.randint(110, 127),
                tick_offset=0,
            ),
        ]

    def _get_section_profile(
        self,
        section_def: ArrangementSection,
        base_profile: GenreProfile,
        arrangement_profile: Optional[GenreArrangementProfile],
    ) -> SectionDrumProfile:
        """Get the drum profile for a section, falling back to scaled base."""
        if arrangement_profile:
            key = section_def.section_type.value
            if key in arrangement_profile.section_profiles:
                return arrangement_profile.section_profiles[key]

        # Fall back: scale base profile by section density
        return self._scale_base_profile(base_profile, section_def)

    def _scale_base_profile(
        self,
        base: GenreProfile,
        section: ArrangementSection,
    ) -> SectionDrumProfile:
        """Quick scaling of base profile by section density."""
        scaled = SectionDrumProfile(
            section_type=section.section_type,
            genre=base.genre,
        )

        density = section.drum_density
        for inst, probs in base.hit_probability.items():
            scaled.hit_probability[inst] = [min(1.0, p * density) for p in probs]

        for inst, mean in base.velocity_mean.items():
            offset = (section.energy - 0.5) * 20
            scaled.velocity_mean[inst] = max(40, min(120, mean + offset))

        scaled.velocity_std = dict(base.velocity_std)
        scaled.timing_std = dict(base.timing_std)
        scaled.density = {inst: d * density for inst, d in base.density.items()}

        return scaled
