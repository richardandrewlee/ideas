"""
Arrangement Templates
----------------------
Defines typical song structures per genre as templates that the
SongGenerator follows to produce full-length tracks.

Each template is a sequence of sections (intro, verse, chorus, etc.)
with energy levels, drum density, and transition types.
"""

from dataclasses import dataclass, field
from typing import Optional

from ..analysis.song_dna import SectionType, SongDNA


@dataclass
class ArrangementSection:
    """One section of a song arrangement."""
    section_type: SectionType
    bars: int
    energy: float               # 0.0-1.0
    drum_density: float         # 0.0-1.0 (multiplier on hit probabilities)
    has_fill_at_end: bool = True
    transition_type: str = "none"  # "none", "fill", "build", "breakdown", "crash"


@dataclass
class ArrangementTemplate:
    """A full song structure."""
    name: str
    genre: str
    sections: list[ArrangementSection] = field(default_factory=list)

    @property
    def total_bars(self) -> int:
        return sum(s.bars for s in self.sections)

    @property
    def estimated_duration_sec(self) -> float:
        """Rough duration at 120 BPM (4/4)."""
        return self.total_bars * 2.0  # 2 seconds per bar at 120 BPM


# ---------------------------------------------------------------------------
# Built-in templates
# ---------------------------------------------------------------------------

ARRANGEMENT_TEMPLATES: dict[str, list[ArrangementTemplate]] = {
    "house": [
        ArrangementTemplate("house_standard", "house", [
            ArrangementSection(SectionType.INTRO,     bars=8,  energy=0.3, drum_density=0.4, has_fill_at_end=False),
            ArrangementSection(SectionType.VERSE,     bars=16, energy=0.5, drum_density=0.7, transition_type="fill"),
            ArrangementSection(SectionType.BREAKDOWN, bars=8,  energy=0.2, drum_density=0.2, transition_type="build"),
            ArrangementSection(SectionType.DROP,      bars=16, energy=1.0, drum_density=1.0, transition_type="crash"),
            ArrangementSection(SectionType.VERSE,     bars=16, energy=0.5, drum_density=0.7, transition_type="fill"),
            ArrangementSection(SectionType.BREAKDOWN, bars=8,  energy=0.2, drum_density=0.2, transition_type="build"),
            ArrangementSection(SectionType.DROP,      bars=16, energy=1.0, drum_density=1.0, transition_type="crash"),
            ArrangementSection(SectionType.OUTRO,     bars=8,  energy=0.3, drum_density=0.4, has_fill_at_end=False),
        ]),
    ],
    "techno": [
        ArrangementTemplate("techno_standard", "techno", [
            ArrangementSection(SectionType.INTRO,     bars=16, energy=0.3, drum_density=0.4, has_fill_at_end=False),
            ArrangementSection(SectionType.VERSE,     bars=16, energy=0.6, drum_density=0.8, transition_type="fill"),
            ArrangementSection(SectionType.BREAKDOWN, bars=8,  energy=0.1, drum_density=0.1, transition_type="build"),
            ArrangementSection(SectionType.DROP,      bars=16, energy=1.0, drum_density=1.0, transition_type="crash"),
            ArrangementSection(SectionType.VERSE,     bars=16, energy=0.6, drum_density=0.8, transition_type="fill"),
            ArrangementSection(SectionType.BREAKDOWN, bars=8,  energy=0.1, drum_density=0.1, transition_type="build"),
            ArrangementSection(SectionType.DROP,      bars=16, energy=1.0, drum_density=1.0, transition_type="crash"),
            ArrangementSection(SectionType.OUTRO,     bars=16, energy=0.3, drum_density=0.3, has_fill_at_end=False),
        ]),
    ],
    "rock": [
        ArrangementTemplate("rock_standard", "rock", [
            ArrangementSection(SectionType.INTRO,   bars=4,  energy=0.4, drum_density=0.5, has_fill_at_end=False),
            ArrangementSection(SectionType.VERSE,   bars=8,  energy=0.5, drum_density=0.7, transition_type="fill"),
            ArrangementSection(SectionType.CHORUS,  bars=8,  energy=0.9, drum_density=1.0, transition_type="crash"),
            ArrangementSection(SectionType.VERSE,   bars=8,  energy=0.5, drum_density=0.7, transition_type="fill"),
            ArrangementSection(SectionType.CHORUS,  bars=8,  energy=0.9, drum_density=1.0, transition_type="crash"),
            ArrangementSection(SectionType.BRIDGE,  bars=8,  energy=0.6, drum_density=0.5, transition_type="fill"),
            ArrangementSection(SectionType.CHORUS,  bars=8,  energy=1.0, drum_density=1.0, transition_type="crash"),
            ArrangementSection(SectionType.OUTRO,   bars=4,  energy=0.3, drum_density=0.4, has_fill_at_end=False),
        ]),
    ],
    "hip-hop": [
        ArrangementTemplate("hiphop_standard", "hip-hop", [
            ArrangementSection(SectionType.INTRO,   bars=4,  energy=0.3, drum_density=0.3, has_fill_at_end=False),
            ArrangementSection(SectionType.VERSE,   bars=16, energy=0.6, drum_density=0.8, transition_type="fill"),
            ArrangementSection(SectionType.CHORUS,  bars=8,  energy=0.9, drum_density=1.0, transition_type="crash"),
            ArrangementSection(SectionType.VERSE,   bars=16, energy=0.6, drum_density=0.8, transition_type="fill"),
            ArrangementSection(SectionType.CHORUS,  bars=8,  energy=0.9, drum_density=1.0, transition_type="crash"),
            ArrangementSection(SectionType.BRIDGE,  bars=8,  energy=0.4, drum_density=0.5, transition_type="fill"),
            ArrangementSection(SectionType.CHORUS,  bars=8,  energy=1.0, drum_density=1.0, transition_type="crash"),
            ArrangementSection(SectionType.OUTRO,   bars=4,  energy=0.3, drum_density=0.3, has_fill_at_end=False),
        ]),
    ],
    "reggae": [
        ArrangementTemplate("reggae_standard", "reggae", [
            ArrangementSection(SectionType.INTRO,   bars=4,  energy=0.3, drum_density=0.4, has_fill_at_end=False),
            ArrangementSection(SectionType.VERSE,   bars=16, energy=0.5, drum_density=0.7, transition_type="fill"),
            ArrangementSection(SectionType.CHORUS,  bars=8,  energy=0.8, drum_density=0.9, transition_type="fill"),
            ArrangementSection(SectionType.VERSE,   bars=16, energy=0.5, drum_density=0.7, transition_type="fill"),
            ArrangementSection(SectionType.CHORUS,  bars=8,  energy=0.8, drum_density=0.9, transition_type="fill"),
            ArrangementSection(SectionType.BRIDGE,  bars=8,  energy=0.4, drum_density=0.5),
            ArrangementSection(SectionType.CHORUS,  bars=8,  energy=0.9, drum_density=1.0, transition_type="crash"),
            ArrangementSection(SectionType.OUTRO,   bars=8,  energy=0.3, drum_density=0.4, has_fill_at_end=False),
        ]),
    ],
    "jazz": [
        ArrangementTemplate("jazz_standard", "jazz", [
            ArrangementSection(SectionType.INTRO,   bars=4,  energy=0.3, drum_density=0.3, has_fill_at_end=False),
            ArrangementSection(SectionType.VERSE,   bars=8,  energy=0.5, drum_density=0.6, transition_type="fill"),
            ArrangementSection(SectionType.CHORUS,  bars=8,  energy=0.7, drum_density=0.8, transition_type="fill"),
            ArrangementSection(SectionType.VERSE,   bars=8,  energy=0.5, drum_density=0.6, transition_type="fill"),
            ArrangementSection(SectionType.BRIDGE,  bars=8,  energy=0.6, drum_density=0.5, transition_type="fill"),
            ArrangementSection(SectionType.CHORUS,  bars=8,  energy=0.8, drum_density=0.9, transition_type="fill"),
            ArrangementSection(SectionType.OUTRO,   bars=4,  energy=0.3, drum_density=0.3, has_fill_at_end=False),
        ]),
    ],
    "pop": [
        ArrangementTemplate("pop_standard", "pop", [
            ArrangementSection(SectionType.INTRO,     bars=4,  energy=0.3, drum_density=0.3, has_fill_at_end=False),
            ArrangementSection(SectionType.VERSE,     bars=8,  energy=0.5, drum_density=0.7, transition_type="fill"),
            ArrangementSection(SectionType.PRECHORUS, bars=4,  energy=0.7, drum_density=0.8, transition_type="build"),
            ArrangementSection(SectionType.CHORUS,    bars=8,  energy=0.9, drum_density=1.0, transition_type="crash"),
            ArrangementSection(SectionType.VERSE,     bars=8,  energy=0.5, drum_density=0.7, transition_type="fill"),
            ArrangementSection(SectionType.PRECHORUS, bars=4,  energy=0.7, drum_density=0.8, transition_type="build"),
            ArrangementSection(SectionType.CHORUS,    bars=8,  energy=0.9, drum_density=1.0, transition_type="crash"),
            ArrangementSection(SectionType.BRIDGE,    bars=8,  energy=0.4, drum_density=0.4),
            ArrangementSection(SectionType.CHORUS,    bars=8,  energy=1.0, drum_density=1.0, transition_type="crash"),
            ArrangementSection(SectionType.OUTRO,     bars=4,  energy=0.3, drum_density=0.3, has_fill_at_end=False),
        ]),
    ],
    "blues": [
        ArrangementTemplate("blues_12bar", "blues", [
            ArrangementSection(SectionType.INTRO,   bars=4,  energy=0.3, drum_density=0.4, has_fill_at_end=False),
            ArrangementSection(SectionType.VERSE,   bars=12, energy=0.5, drum_density=0.7, transition_type="fill"),
            ArrangementSection(SectionType.VERSE,   bars=12, energy=0.6, drum_density=0.8, transition_type="fill"),
            ArrangementSection(SectionType.CHORUS,  bars=12, energy=0.8, drum_density=0.9, transition_type="fill"),
            ArrangementSection(SectionType.VERSE,   bars=12, energy=0.5, drum_density=0.7, transition_type="fill"),
            ArrangementSection(SectionType.CHORUS,  bars=12, energy=0.9, drum_density=1.0, transition_type="crash"),
            ArrangementSection(SectionType.OUTRO,   bars=4,  energy=0.3, drum_density=0.4, has_fill_at_end=False),
        ]),
    ],
    "metal": [
        ArrangementTemplate("metal_standard", "metal", [
            ArrangementSection(SectionType.INTRO,   bars=4,  energy=0.6, drum_density=0.7, has_fill_at_end=False),
            ArrangementSection(SectionType.VERSE,   bars=8,  energy=0.7, drum_density=0.8, transition_type="fill"),
            ArrangementSection(SectionType.CHORUS,  bars=8,  energy=1.0, drum_density=1.0, transition_type="crash"),
            ArrangementSection(SectionType.VERSE,   bars=8,  energy=0.7, drum_density=0.8, transition_type="fill"),
            ArrangementSection(SectionType.CHORUS,  bars=8,  energy=1.0, drum_density=1.0, transition_type="crash"),
            ArrangementSection(SectionType.BRIDGE,  bars=8,  energy=0.5, drum_density=0.5, transition_type="build"),
            ArrangementSection(SectionType.CHORUS,  bars=8,  energy=1.0, drum_density=1.0, transition_type="crash"),
            ArrangementSection(SectionType.OUTRO,   bars=4,  energy=0.6, drum_density=0.6, has_fill_at_end=False),
        ]),
    ],
    "drum-and-bass": [
        ArrangementTemplate("dnb_standard", "drum-and-bass", [
            ArrangementSection(SectionType.INTRO,     bars=16, energy=0.3, drum_density=0.3, has_fill_at_end=False),
            ArrangementSection(SectionType.VERSE,     bars=16, energy=0.6, drum_density=0.8, transition_type="fill"),
            ArrangementSection(SectionType.DROP,      bars=16, energy=1.0, drum_density=1.0, transition_type="crash"),
            ArrangementSection(SectionType.BREAKDOWN, bars=8,  energy=0.2, drum_density=0.2, transition_type="build"),
            ArrangementSection(SectionType.DROP,      bars=16, energy=1.0, drum_density=1.0, transition_type="crash"),
            ArrangementSection(SectionType.OUTRO,     bars=16, energy=0.3, drum_density=0.3, has_fill_at_end=False),
        ]),
    ],
    "funk": [
        ArrangementTemplate("funk_standard", "funk", [
            ArrangementSection(SectionType.INTRO,   bars=4,  energy=0.4, drum_density=0.5, has_fill_at_end=False),
            ArrangementSection(SectionType.VERSE,   bars=8,  energy=0.6, drum_density=0.8, transition_type="fill"),
            ArrangementSection(SectionType.CHORUS,  bars=8,  energy=0.9, drum_density=1.0, transition_type="fill"),
            ArrangementSection(SectionType.VERSE,   bars=8,  energy=0.6, drum_density=0.8, transition_type="fill"),
            ArrangementSection(SectionType.CHORUS,  bars=8,  energy=0.9, drum_density=1.0, transition_type="fill"),
            ArrangementSection(SectionType.BRIDGE,  bars=8,  energy=0.5, drum_density=0.6),
            ArrangementSection(SectionType.CHORUS,  bars=8,  energy=1.0, drum_density=1.0, transition_type="crash"),
            ArrangementSection(SectionType.OUTRO,   bars=4,  energy=0.4, drum_density=0.5, has_fill_at_end=False),
        ]),
    ],
    "soul": [
        ArrangementTemplate("soul_standard", "soul", [
            ArrangementSection(SectionType.INTRO,   bars=4,  energy=0.3, drum_density=0.4, has_fill_at_end=False),
            ArrangementSection(SectionType.VERSE,   bars=8,  energy=0.5, drum_density=0.7, transition_type="fill"),
            ArrangementSection(SectionType.CHORUS,  bars=8,  energy=0.8, drum_density=0.9, transition_type="fill"),
            ArrangementSection(SectionType.VERSE,   bars=8,  energy=0.5, drum_density=0.7, transition_type="fill"),
            ArrangementSection(SectionType.BRIDGE,  bars=8,  energy=0.4, drum_density=0.5),
            ArrangementSection(SectionType.CHORUS,  bars=8,  energy=0.9, drum_density=1.0, transition_type="crash"),
            ArrangementSection(SectionType.OUTRO,   bars=4,  energy=0.3, drum_density=0.4, has_fill_at_end=False),
        ]),
    ],
}

# Default fallback for genres without a template
DEFAULT_TEMPLATE = ArrangementTemplate("generic_standard", "generic", [
    ArrangementSection(SectionType.INTRO,   bars=4,  energy=0.3, drum_density=0.4, has_fill_at_end=False),
    ArrangementSection(SectionType.VERSE,   bars=8,  energy=0.5, drum_density=0.7, transition_type="fill"),
    ArrangementSection(SectionType.CHORUS,  bars=8,  energy=0.9, drum_density=1.0, transition_type="crash"),
    ArrangementSection(SectionType.VERSE,   bars=8,  energy=0.5, drum_density=0.7, transition_type="fill"),
    ArrangementSection(SectionType.CHORUS,  bars=8,  energy=0.9, drum_density=1.0, transition_type="crash"),
    ArrangementSection(SectionType.BRIDGE,  bars=8,  energy=0.4, drum_density=0.5),
    ArrangementSection(SectionType.CHORUS,  bars=8,  energy=1.0, drum_density=1.0, transition_type="crash"),
    ArrangementSection(SectionType.OUTRO,   bars=4,  energy=0.3, drum_density=0.4, has_fill_at_end=False),
])


class ArrangementEngine:
    """Selects and customizes arrangement templates."""

    def get_template(self, genre: str, template_name: Optional[str] = None) -> ArrangementTemplate:
        """Get an arrangement template for a genre."""
        templates = ARRANGEMENT_TEMPLATES.get(genre.lower(), [])
        if not templates:
            return DEFAULT_TEMPLATE

        if template_name:
            for t in templates:
                if t.name == template_name:
                    return t

        return templates[0]

    def from_song_dna(self, dna: SongDNA) -> ArrangementTemplate:
        """Derive an arrangement template from an analyzed song's structure."""
        if not dna.sections:
            return self.get_template(dna.genre)

        sections = []
        for s in dna.sections:
            sections.append(ArrangementSection(
                section_type=s.section_type,
                bars=s.bars,
                energy=s.energy_level,
                drum_density=s.drum_density if s.drum_density > 0 else s.energy_level,
                has_fill_at_end=(s.section_type not in (SectionType.INTRO, SectionType.OUTRO)),
                transition_type="fill" if s.bars >= 8 else "none",
            ))

        return ArrangementTemplate(
            name=f"from_{dna.title or 'analyzed'}",
            genre=dna.genre,
            sections=sections,
        )
