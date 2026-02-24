"""
Pattern Analyzer
----------------
Builds statistical models from a collection of DrumPattern objects.

The output is a GenreProfile — a probability distribution over drum hits,
velocities, and timing offsets — used by the statistical beat generator.

A GenreProfile captures:
    - hit_probability[instrument][step]  → float 0–1
    - velocity_mean[instrument]          → float
    - velocity_std[instrument]           → float
    - timing_std[instrument]             → float (ticks)
    - bpm_mean, bpm_std                  → float
    - typical_density[instrument]        → float 0–1
"""

import json
import math
import logging
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from .drum_extractor import DrumPattern, PRIMARY_INSTRUMENTS

logger = logging.getLogger(__name__)


@dataclass
class GenreProfile:
    """
    Statistical fingerprint for a genre, derived from many drum patterns.
    This is the core data structure that the beat generator consumes.
    """
    genre:           str
    year:            int
    num_patterns:    int = 0
    grid_steps:      int = 32
    steps_per_bar:   int = 16
    bpm_mean:        float = 120.0
    bpm_std:         float = 5.0

    # Per-instrument per-step hit probabilities  shape: {instrument: [step_prob, ...]}
    hit_probability: dict[str, list[float]] = field(default_factory=dict)

    # Per-instrument velocity stats
    velocity_mean:   dict[str, float] = field(default_factory=dict)
    velocity_std:    dict[str, float] = field(default_factory=dict)

    # Per-instrument timing humanization (tick deviation std)
    timing_std:      dict[str, float] = field(default_factory=dict)

    # Relative density (fraction of steps with a hit, averaged across patterns)
    density:         dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "GenreProfile":
        return cls(**d)

    def save(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Saved genre profile → {path}")

    @classmethod
    def load(cls, path: str) -> "GenreProfile":
        with open(path) as f:
            return cls.from_dict(json.load(f))


# ---------------------------------------------------------------------------
# Built-in genre profiles (fallback when no MIDI data is available)
# ---------------------------------------------------------------------------

BUILTIN_PROFILES: dict[str, dict] = {
    "house": {
        # Four-on-the-floor kick, off-beat open HH, clap on 2+4 (steps 8,24)
        "kick":          [0.95,0.05,0.05,0.05, 0.95,0.05,0.05,0.05,
                          0.95,0.05,0.05,0.05, 0.95,0.05,0.05,0.05,
                          0.95,0.05,0.05,0.05, 0.95,0.05,0.05,0.05,
                          0.95,0.05,0.05,0.05, 0.95,0.05,0.05,0.05],
        "snare":         [0.05,0.05,0.05,0.05, 0.05,0.05,0.05,0.05,
                          0.90,0.05,0.05,0.05, 0.05,0.05,0.05,0.05,
                          0.05,0.05,0.05,0.05, 0.05,0.05,0.05,0.05,
                          0.90,0.05,0.05,0.05, 0.05,0.05,0.05,0.05],
        "hihat_closed":  [0.80,0.80,0.80,0.80, 0.80,0.80,0.80,0.80,
                          0.80,0.80,0.80,0.80, 0.80,0.80,0.80,0.80,
                          0.80,0.80,0.80,0.80, 0.80,0.80,0.80,0.80,
                          0.80,0.80,0.80,0.80, 0.80,0.80,0.80,0.80],
        "hihat_open":    [0.05,0.05,0.05,0.05, 0.05,0.05,0.05,0.60,
                          0.05,0.05,0.05,0.05, 0.05,0.05,0.05,0.60,
                          0.05,0.05,0.05,0.05, 0.05,0.05,0.05,0.60,
                          0.05,0.05,0.05,0.05, 0.05,0.05,0.05,0.60],
        "clap":          [0.05]*8 + [0.80,0.05]*4 + [0.05]*6 + [0.80,0.05]*3,
    },
    "techno": {
        # Driving kick, harder HH pattern, accent on step 8/24
        "kick":          [0.95,0.05,0.15,0.05, 0.85,0.05,0.20,0.05,
                          0.95,0.05,0.15,0.05, 0.80,0.05,0.30,0.05,
                          0.95,0.05,0.15,0.05, 0.85,0.05,0.20,0.05,
                          0.95,0.05,0.15,0.05, 0.75,0.05,0.35,0.05],
        "snare":         [0.05]*8 + [0.85,0.05,0.05,0.05,0.05,0.05,0.05,0.05]*2,
        "hihat_closed":  [0.90]*32,
        "hihat_open":    [0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.40]*4,
        "crash":         [0.30] + [0.0]*15 + [0.15] + [0.0]*15,
    },
    "reggae": {
        # One-drop: kick on beat 3 (step 8), snare on 2+4, heavy offbeat HH
        "kick":          [0.05,0.05,0.05,0.05, 0.05,0.05,0.05,0.05,
                          0.90,0.05,0.05,0.05, 0.05,0.05,0.05,0.05,
                          0.05,0.05,0.05,0.05, 0.05,0.05,0.05,0.05,
                          0.90,0.05,0.05,0.05, 0.05,0.05,0.05,0.05],
        "snare":         [0.05,0.05,0.05,0.05, 0.85,0.05,0.05,0.05,
                          0.05,0.05,0.05,0.05, 0.85,0.05,0.05,0.05,
                          0.05,0.05,0.05,0.05, 0.85,0.05,0.05,0.05,
                          0.05,0.05,0.05,0.05, 0.85,0.05,0.05,0.05],
        "hihat_closed":  [0.80,0.05,0.80,0.05]*8,
        "hihat_open":    [0.05,0.70,0.05,0.70]*8,
    },
    "rock": {
        # Classic kick/snare backbeat, driving HH
        "kick":          [0.95,0.05,0.05,0.05, 0.30,0.05,0.05,0.05,
                          0.05,0.05,0.05,0.05, 0.80,0.05,0.05,0.05,
                          0.95,0.05,0.05,0.05, 0.30,0.05,0.05,0.05,
                          0.05,0.05,0.05,0.05, 0.80,0.05,0.20,0.05],
        "snare":         [0.05,0.05,0.05,0.05, 0.05,0.05,0.05,0.05,
                          0.95,0.05,0.05,0.05, 0.05,0.05,0.05,0.05,
                          0.05,0.05,0.05,0.05, 0.05,0.05,0.05,0.05,
                          0.95,0.05,0.05,0.05, 0.05,0.05,0.05,0.05],
        "hihat_closed":  [0.90,0.05,0.80,0.05]*8,
        "crash":         [0.40] + [0.0]*15 + [0.10] + [0.0]*15,
        "tom_low":       [0.0]*28 + [0.0,0.50,0.50,0.70],
    },
    "hip-hop": {
        # Boom-bap: kick on 1+3, snare on 2+4, swung hi-hat
        "kick":          [0.90,0.05,0.05,0.05, 0.05,0.05,0.40,0.05,
                          0.05,0.05,0.05,0.05, 0.05,0.05,0.05,0.05,
                          0.90,0.05,0.05,0.05, 0.05,0.05,0.40,0.05,
                          0.05,0.05,0.05,0.05, 0.05,0.05,0.05,0.05],
        "snare":         [0.05]*4 + [0.0,0.05,0.05,0.05,0.90]*1 + [0.05]*3 + [0.05]*4 +
                         [0.05]*4 + [0.90] + [0.05]*3 + [0.05]*3 + [0.90] + [0.05]*3 + [0.05]*4,
        "hihat_closed":  [0.70,0.40,0.60,0.40]*8,
        "hihat_open":    [0.0,0.0,0.0,0.30]*8,
        "clap":          [0.0]*8 + [0.80] + [0.0]*7 + [0.0]*7 + [0.80] + [0.0]*8,
    },
}

# Pad built-in profiles to 32 steps and fill missing instruments
def _pad_profile(p: dict) -> dict:
    out = {}
    for inst in PRIMARY_INSTRUMENTS:
        steps = p.get(inst, [0.05] * 32)
        # Pad or truncate to 32 steps
        if len(steps) < 32:
            steps = steps + [0.05] * (32 - len(steps))
        out[inst] = steps[:32]
    return out

BUILTIN_PROFILES = {k: _pad_profile(v) for k, v in BUILTIN_PROFILES.items()}


class PatternAnalyzer:
    """Builds GenreProfile from a list of DrumPattern objects."""

    def analyze(
        self,
        patterns: list[DrumPattern],
        genre: str,
        year: int,
    ) -> GenreProfile:
        """
        Builds a statistical GenreProfile from a list of patterns.
        Falls back to built-in profiles if insufficient data.
        """
        if len(patterns) < 5:
            logger.info(
                f"Only {len(patterns)} patterns for {genre}/{year}; "
                "merging with built-in profile"
            )
            return self._make_profile(patterns, genre, year, use_builtin=True)

        return self._make_profile(patterns, genre, year, use_builtin=False)

    def _make_profile(
        self,
        patterns: list[DrumPattern],
        genre: str,
        year: int,
        use_builtin: bool,
    ) -> GenreProfile:
        profile = GenreProfile(genre=genre, year=year, num_patterns=len(patterns))

        # BPM stats
        bpms = [p.bpm for p in patterns if p.bpm > 0]
        if bpms:
            profile.bpm_mean = sum(bpms) / len(bpms)
            profile.bpm_std  = self._std(bpms)
        else:
            profile.bpm_mean = 120.0
            profile.bpm_std  = 5.0

        # Per-instrument stats
        for inst in PRIMARY_INSTRUMENTS:
            # Hit probabilities per step (averaged across patterns)
            step_hits  = defaultdict(list)  # step → [1 if hit else 0, ...]
            velocities = []
            timing_offsets = []

            for pat in patterns:
                grid = pat.to_grid()
                inst_steps = grid.get(inst, [None] * pat.grid_steps)

                for step, vel in enumerate(inst_steps):
                    step_mod = step % 32  # normalize to 32-step grid
                    step_hits[step_mod].append(1 if vel is not None else 0)
                    if vel is not None:
                        velocities.append(vel)

                for hit in pat.hits:
                    if hit.instrument == inst:
                        timing_offsets.append(hit.tick_offset)

            # Average hit probability per step
            probs = []
            for step in range(32):
                hits_list = step_hits.get(step, [0])
                probs.append(sum(hits_list) / len(hits_list))

            # If very sparse data, blend with built-in
            if use_builtin and genre in BUILTIN_PROFILES:
                builtin_probs = BUILTIN_PROFILES[genre].get(inst, [0.05] * 32)
                weight = min(len(patterns) / 20.0, 0.8)  # Up to 80% data weight
                probs = [
                    data_p * weight + builtin_p * (1 - weight)
                    for data_p, builtin_p in zip(probs, builtin_probs)
                ]
            elif not any(p > 0.1 for p in probs) and genre in BUILTIN_PROFILES:
                # No data at all for this instrument — use built-in
                probs = BUILTIN_PROFILES[genre].get(inst, [0.05] * 32)

            profile.hit_probability[inst] = probs

            # Velocity stats
            if velocities:
                profile.velocity_mean[inst] = sum(velocities) / len(velocities)
                profile.velocity_std[inst]  = self._std(velocities)
            else:
                profile.velocity_mean[inst] = 80.0
                profile.velocity_std[inst]  = 10.0

            # Timing std
            profile.timing_std[inst] = self._std(timing_offsets) if timing_offsets else 3.0

            # Density
            profile.density[inst] = sum(1 for p in probs if p > 0.3) / 32.0

        return profile

    @staticmethod
    def _std(values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return math.sqrt(variance)

    def get_builtin_profile(self, genre: str, year: int = 2020) -> GenreProfile:
        """Returns a profile built entirely from built-in genre data."""
        profile = GenreProfile(genre=genre, year=year, num_patterns=0)
        norm = genre.lower()

        template = BUILTIN_PROFILES.get(norm, BUILTIN_PROFILES.get("rock", {}))
        profile.hit_probability = dict(template)

        # Default velocity and timing values per genre character
        genre_vel = {
            "house":   (85, 10), "techno": (95, 8), "rock": (90, 12),
            "reggae":  (78, 12), "hip-hop": (82, 14),
        }
        v_mean, v_std = genre_vel.get(norm, (82, 12))
        for inst in PRIMARY_INSTRUMENTS:
            profile.velocity_mean[inst] = v_mean
            profile.velocity_std[inst]  = v_std
            profile.timing_std[inst]    = 4.0
            profile.density[inst]       = (
                sum(1 for p in profile.hit_probability.get(inst, []) if p > 0.3) / 32.0
            )

        # Genre-typical BPMs
        bpm_map = {
            "house": (122, 4), "techno": (135, 6), "rock": (110, 15),
            "reggae": (90, 8), "hip-hop": (90, 12), "jazz": (140, 30),
            "pop": (118, 14), "metal": (165, 25), "rnb": (85, 10),
            "drum-and-bass": (172, 6), "edm": (128, 6), "funk": (105, 10),
        }
        bpm_mean, bpm_std = bpm_map.get(norm, (120, 10))
        profile.bpm_mean = bpm_mean
        profile.bpm_std  = bpm_std

        return profile
