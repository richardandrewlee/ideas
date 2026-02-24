"""
Statistical Beat Generator
--------------------------
Generates drum patterns by sampling from a GenreProfile's probability
distributions. Each run produces a unique but genre-authentic beat.

Generation process:
    1. Sample BPM from genre's BPM distribution
    2. For each instrument × step, roll against hit_probability
    3. If hit, sample velocity from velocity distribution
    4. Optionally apply fills every N bars
    5. Return a RawBeat object ready for humanization and export
"""

import random
import logging
from dataclasses import dataclass, field
from typing import Optional

from ..analysis.pattern_analyzer import GenreProfile, PRIMARY_INSTRUMENTS
from ..analysis.drum_extractor import GM_DRUM_MAP

logger = logging.getLogger(__name__)

# Reverse map: instrument name → preferred MIDI note (GM standard)
INSTRUMENT_TO_MIDI: dict[str, int] = {
    "kick":         36,
    "snare":        38,
    "hihat_closed": 42,
    "hihat_open":   46,
    "crash":        49,
    "ride":         51,
    "tom_low":      45,
    "tom_mid":      47,
    "tom_high":     50,
    "clap":         39,
    "tambourine":   54,
    "cowbell":      56,
    "splash":       55,
    "china":        52,
    "maracas":      70,
}


@dataclass
class RawHit:
    instrument: str
    midi_note:  int
    step:       int     # 0-based within grid
    velocity:   int     # 1-127
    tick_offset: int    # timing humanization (added by Humanizer)


@dataclass
class RawBeat:
    """
    A generated beat before export.
    Can be passed to Humanizer, then to MidiExporter / WavRenderer / JsonExporter.
    """
    genre:         str
    year:          int
    bpm:           float
    grid_steps:    int = 32
    steps_per_bar: int = 16
    ticks_per_beat: int = 480
    hits:          list[RawHit] = field(default_factory=list)

    @property
    def ticks_per_step(self) -> float:
        return self.ticks_per_beat / (self.steps_per_bar / 4)

    @property
    def duration_ticks(self) -> int:
        return int(self.grid_steps * self.ticks_per_step)


class StatisticalGenerator:
    """
    Generates beats by sampling from a GenreProfile.

    Usage:
        gen = StatisticalGenerator(seed=42)
        beat = gen.generate(profile, num_bars=4)
    """

    def __init__(self, seed: Optional[int] = None):
        self.rng = random.Random(seed)

    def generate(
        self,
        profile: GenreProfile,
        num_bars: int = 4,
        variation_factor: float = 0.15,
        add_fills: bool = True,
        fill_every_n_bars: int = 4,
    ) -> RawBeat:
        """
        Generate a beat from a GenreProfile.

        Args:
            profile:          The genre profile to sample from.
            num_bars:         Total bars to generate.
            variation_factor: How much to perturb probabilities each bar (0–1).
                              Adds bar-to-bar variation without losing genre feel.
            add_fills:        Whether to add drum fills on the last beat of
                              every fill_every_n_bars bars.
            fill_every_n_bars: How often to insert a fill.

        Returns:
            A RawBeat ready for humanization and export.
        """
        # Sample BPM
        bpm = self._sample_bpm(profile)

        total_steps = profile.steps_per_bar * num_bars
        beat = RawBeat(
            genre=profile.genre,
            year=profile.year,
            bpm=bpm,
            grid_steps=total_steps,
            steps_per_bar=profile.steps_per_bar,
        )

        for bar_idx in range(num_bars):
            bar_start_step = bar_idx * profile.steps_per_bar
            is_fill_bar = add_fills and ((bar_idx + 1) % fill_every_n_bars == 0)

            for step_in_bar in range(profile.steps_per_bar):
                abs_step = bar_start_step + step_in_bar
                grid_step = step_in_bar % profile.grid_steps  # wraps to 32-step template

                # Fill: suppress normal kick/HH on last 4 steps, boost toms
                in_fill_zone = is_fill_bar and step_in_bar >= (profile.steps_per_bar - 4)

                for inst in PRIMARY_INSTRUMENTS:
                    prob = self._get_probability(
                        profile, inst, grid_step, variation_factor
                    )

                    if in_fill_zone:
                        prob = self._apply_fill_logic(inst, step_in_bar, prob, profile.steps_per_bar)

                    if self.rng.random() < prob:
                        vel = self._sample_velocity(profile, inst)
                        beat.hits.append(RawHit(
                            instrument=inst,
                            midi_note=INSTRUMENT_TO_MIDI.get(inst, 38),
                            step=abs_step,
                            velocity=vel,
                            tick_offset=0,  # Humanizer fills this in
                        ))

        logger.debug(
            f"Generated {len(beat.hits)} hits across {num_bars} bars "
            f"at {bpm:.1f} BPM ({profile.genre}/{profile.year})"
        )
        return beat

    def generate_variations(
        self,
        profile: GenreProfile,
        count: int = 4,
        num_bars: int = 4,
    ) -> list[RawBeat]:
        """Generate multiple unique variations from the same profile."""
        return [
            self.generate(
                profile,
                num_bars=num_bars,
                variation_factor=0.10 + 0.10 * (i / max(count - 1, 1)),
            )
            for i in range(count)
        ]

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _sample_bpm(self, profile: GenreProfile) -> float:
        raw = self.rng.gauss(profile.bpm_mean, profile.bpm_std)
        return round(max(40.0, min(220.0, raw)), 1)

    def _get_probability(
        self,
        profile: GenreProfile,
        instrument: str,
        step: int,
        variation_factor: float,
    ) -> float:
        probs = profile.hit_probability.get(instrument, [])
        if not probs:
            return 0.0
        base_prob = probs[step % len(probs)]

        # Add per-bar variation: small random perturbation
        delta = self.rng.uniform(-variation_factor, variation_factor)
        return max(0.0, min(1.0, base_prob + delta * base_prob))

    def _sample_velocity(self, profile: GenreProfile, instrument: str) -> int:
        mean = profile.velocity_mean.get(instrument, 80.0)
        std  = profile.velocity_std.get(instrument, 10.0)
        raw  = self.rng.gauss(mean, std)
        return max(1, min(127, int(round(raw))))

    def _apply_fill_logic(
        self,
        instrument: str,
        step_in_bar: int,
        base_prob: float,
        steps_per_bar: int = 16,
    ) -> float:
        """Modify hit probabilities in the fill zone (last 4 steps of a fill bar)."""
        if instrument in ("kick", "hihat_closed"):
            return base_prob * 0.3   # Suppress normal elements
        elif instrument in ("tom_low", "tom_mid", "tom_high"):
            return min(1.0, base_prob + 0.6)  # Boost toms
        elif instrument == "snare":
            return min(1.0, base_prob + 0.4)  # More snare hits
        elif instrument == "crash" and (step_in_bar == steps_per_bar - 1):
            return 0.8   # Crash on fill resolution
        return base_prob
