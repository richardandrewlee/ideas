"""
Section Profile Builder
------------------------
Builds per-section drum profiles from analyzed songs.

When we have SongDNA data with section boundaries, we can build
different drum profiles for verse vs chorus vs bridge — instead of
one flat profile for the entire genre.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from .song_dna import SongDNA, SectionType
from .pattern_analyzer import GenreProfile

logger = logging.getLogger(__name__)


@dataclass
class SectionDrumProfile:
    """GenreProfile-like data for a specific section type."""
    section_type: SectionType
    genre: str
    hit_probability: dict[str, list[float]] = field(default_factory=dict)
    velocity_mean: dict[str, float] = field(default_factory=dict)
    velocity_std: dict[str, float] = field(default_factory=dict)
    timing_std: dict[str, float] = field(default_factory=dict)
    density: dict[str, float] = field(default_factory=dict)


@dataclass
class GenreArrangementProfile:
    """Extended GenreProfile with per-section drum data."""
    genre: str
    year: int
    base_profile: GenreProfile
    section_profiles: dict[str, SectionDrumProfile] = field(default_factory=dict)


class SectionProfileBuilder:
    """Builds section-specific drum profiles from SongDNA analysis."""

    def build(
        self,
        base_profile: GenreProfile,
        genre: str,
        year: int,
    ) -> GenreArrangementProfile:
        """Build section profiles by scaling the base profile.

        Uses genre-specific heuristics to create verse/chorus/bridge
        variations from the base profile. When real SongDNA data is
        available, the from_song_dnas method should be used instead.
        """
        result = GenreArrangementProfile(
            genre=genre, year=year, base_profile=base_profile
        )

        # Section energy scaling — how much to scale the base profile
        section_scales = {
            SectionType.INTRO:     0.4,
            SectionType.VERSE:     0.7,
            SectionType.PRECHORUS: 0.8,
            SectionType.CHORUS:    1.0,
            SectionType.BRIDGE:    0.5,
            SectionType.BREAKDOWN: 0.2,
            SectionType.DROP:      1.0,
            SectionType.OUTRO:     0.4,
        }

        for section_type, scale in section_scales.items():
            profile = self._scale_profile(base_profile, section_type, genre, scale)
            result.section_profiles[section_type.value] = profile

        return result

    def _scale_profile(
        self,
        base: GenreProfile,
        section_type: SectionType,
        genre: str,
        scale: float,
    ) -> SectionDrumProfile:
        """Create a section profile by scaling the base profile's probabilities."""
        section = SectionDrumProfile(
            section_type=section_type,
            genre=genre,
        )

        for inst, probs in base.hit_probability.items():
            scaled = []
            for p in probs:
                # Scale probability toward the section's energy
                if section_type in (SectionType.INTRO, SectionType.OUTRO):
                    # Intros/outros: suppress fills, keep core rhythm
                    if inst in ("tom_low", "tom_mid", "tom_high", "crash"):
                        scaled.append(p * scale * 0.3)
                    else:
                        scaled.append(p * scale)
                elif section_type == SectionType.BREAKDOWN:
                    # Breakdowns: minimal drums
                    if inst in ("kick", "hihat_closed"):
                        scaled.append(p * 0.3)
                    else:
                        scaled.append(p * 0.1)
                elif section_type == SectionType.CHORUS or section_type == SectionType.DROP:
                    # Chorus/drop: full energy, boost crash on beat 1
                    scaled.append(min(1.0, p * scale))
                else:
                    scaled.append(p * scale)

            section.hit_probability[inst] = scaled

        # Velocity: slightly louder in choruses, quieter in verses
        for inst, mean in base.velocity_mean.items():
            vel_offset = (scale - 0.7) * 15  # chorus=+4.5, verse=0, intro=-4.5
            section.velocity_mean[inst] = max(40, min(120, mean + vel_offset))

        section.velocity_std = dict(base.velocity_std)
        section.timing_std = dict(base.timing_std)
        section.density = {inst: d * scale for inst, d in base.density.items()}

        return section
