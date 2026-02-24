"""
SongDNA — Complete musical fingerprint of a song.

The central data model for the beat framework's analysis pipeline.
Captures everything: key, chords, structure, instruments, energy,
tempo, Spotify audio features, and drum patterns.
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SongKey(Enum):
    """Pitch classes 0-11 (C through B)."""
    C = 0
    Cs = 1
    D = 2
    Ds = 3
    E = 4
    F = 5
    Fs = 6
    G = 7
    Gs = 8
    A = 9
    As = 10
    B = 11

    @property
    def label(self) -> str:
        _labels = {
            0: "C", 1: "C#", 2: "D", 3: "D#", 4: "E", 5: "F",
            6: "F#", 7: "G", 8: "G#", 9: "A", 10: "A#", 11: "B",
        }
        return _labels[self.value]


class Mode(Enum):
    MAJOR = "major"
    MINOR = "minor"
    DORIAN = "dorian"
    MIXOLYDIAN = "mixolydian"


class SectionType(Enum):
    INTRO = "intro"
    VERSE = "verse"
    PRECHORUS = "prechorus"
    CHORUS = "chorus"
    BRIDGE = "bridge"
    BREAKDOWN = "breakdown"
    DROP = "drop"
    OUTRO = "outro"
    FILL = "fill"


# ---------------------------------------------------------------------------
# Component dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ChordEvent:
    """A single chord occurrence in the progression."""
    root: int                          # 0-11 pitch class
    quality: str                       # "major", "minor", "dom7", "min7", "maj7", "dim", "aug", "sus2", "sus4"
    bass_note: Optional[int] = None    # For slash chords (pitch class)
    start_tick: int = 0
    duration_ticks: int = 0
    start_bar: Optional[int] = None
    confidence: float = 1.0

    @property
    def name(self) -> str:
        root_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        suffix = {"major": "", "minor": "m", "dom7": "7", "min7": "m7",
                  "maj7": "maj7", "dim": "dim", "aug": "aug", "sus2": "sus2", "sus4": "sus4"}
        base = root_names[self.root % 12] + suffix.get(self.quality, self.quality)
        if self.bass_note is not None and self.bass_note != self.root:
            base += "/" + root_names[self.bass_note % 12]
        return base

    def to_dict(self) -> dict:
        return {
            "root": self.root, "quality": self.quality,
            "bass_note": self.bass_note, "name": self.name,
            "start_tick": self.start_tick, "duration_ticks": self.duration_ticks,
            "start_bar": self.start_bar, "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ChordEvent":
        return cls(
            root=d["root"], quality=d["quality"],
            bass_note=d.get("bass_note"), start_tick=d.get("start_tick", 0),
            duration_ticks=d.get("duration_ticks", 0),
            start_bar=d.get("start_bar"), confidence=d.get("confidence", 1.0),
        )


@dataclass
class SongSection:
    """A structural section of a song."""
    section_type: SectionType
    start_bar: int
    end_bar: int                       # Exclusive
    energy_level: float = 0.5          # 0.0 - 1.0
    chord_progression: list[ChordEvent] = field(default_factory=list)
    drum_density: float = 0.0
    has_drums: bool = True
    label: str = ""                    # e.g. "verse_1", "chorus_2"

    @property
    def bars(self) -> int:
        return self.end_bar - self.start_bar

    def to_dict(self) -> dict:
        return {
            "section_type": self.section_type.value,
            "start_bar": self.start_bar, "end_bar": self.end_bar,
            "bars": self.bars, "energy_level": self.energy_level,
            "chord_progression": [c.to_dict() for c in self.chord_progression],
            "drum_density": self.drum_density,
            "has_drums": self.has_drums, "label": self.label,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SongSection":
        return cls(
            section_type=SectionType(d["section_type"]),
            start_bar=d["start_bar"], end_bar=d["end_bar"],
            energy_level=d.get("energy_level", 0.5),
            chord_progression=[ChordEvent.from_dict(c) for c in d.get("chord_progression", [])],
            drum_density=d.get("drum_density", 0.0),
            has_drums=d.get("has_drums", True),
            label=d.get("label", ""),
        )


@dataclass
class InstrumentTrack:
    """A musical role identified in a song."""
    name: str                          # "bass", "piano", "synth_lead", "guitar", "drums", etc.
    midi_program: int = 0              # GM program number 0-127
    channel: int = 0                   # MIDI channel
    note_count: int = 0
    lowest_note: int = 0
    highest_note: int = 127
    avg_velocity: float = 80.0
    is_drum: bool = False
    pitch_classes_used: list[int] = field(default_factory=list)  # 0-11

    def to_dict(self) -> dict:
        return {
            "name": self.name, "midi_program": self.midi_program,
            "channel": self.channel, "note_count": self.note_count,
            "lowest_note": self.lowest_note, "highest_note": self.highest_note,
            "avg_velocity": round(self.avg_velocity, 1),
            "is_drum": self.is_drum,
            "pitch_classes_used": self.pitch_classes_used,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "InstrumentTrack":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# SongDNA — the main data model
# ---------------------------------------------------------------------------

@dataclass
class SongDNA:
    """Complete musical fingerprint of a song."""

    # Identity
    title: str = ""
    artist: str = ""
    year: int = 0
    genre: str = ""
    source: str = ""                   # "midi", "spotify", "hybrid"

    # Tempo & Meter
    bpm: float = 120.0
    time_signature_numerator: int = 4
    time_signature_denominator: int = 4
    tempo_changes: list[tuple[int, float]] = field(default_factory=list)  # (tick, bpm)

    # Key & Harmony
    key: Optional[SongKey] = None
    mode: Optional[Mode] = None
    key_confidence: float = 0.0
    chord_progression: list[ChordEvent] = field(default_factory=list)

    # Structure
    sections: list[SongSection] = field(default_factory=list)
    total_bars: int = 0
    total_ticks: int = 0

    # Instruments
    instruments: list[InstrumentTrack] = field(default_factory=list)
    has_bass: bool = False
    has_melody: bool = False
    has_chords: bool = False
    has_drums: bool = False

    # Energy profile (per-bar, 0.0–1.0)
    energy_curve: list[float] = field(default_factory=list)

    # Spotify audio features (when available)
    danceability: Optional[float] = None
    energy: Optional[float] = None
    valence: Optional[float] = None
    acousticness: Optional[float] = None
    instrumentalness: Optional[float] = None
    loudness: Optional[float] = None
    speechiness: Optional[float] = None
    liveness: Optional[float] = None

    # Drum patterns (preserves existing pipeline output)
    drum_patterns: list = field(default_factory=list)

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @property
    def key_name(self) -> str:
        if self.key is None:
            return "unknown"
        mode_str = f" {self.mode.value}" if self.mode else ""
        return f"{self.key.label}{mode_str}"

    @property
    def time_signature(self) -> str:
        return f"{self.time_signature_numerator}/{self.time_signature_denominator}"

    @property
    def section_summary(self) -> str:
        return " → ".join(s.section_type.value for s in self.sections) if self.sections else "unknown"

    @property
    def instrument_names(self) -> list[str]:
        return [i.name for i in self.instruments]

    def get_sections_by_type(self, section_type: SectionType) -> list[SongSection]:
        return [s for s in self.sections if s.section_type == section_type]

    # -----------------------------------------------------------------------
    # Serialization
    # -----------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "title": self.title, "artist": self.artist,
            "year": self.year, "genre": self.genre, "source": self.source,
            "bpm": round(self.bpm, 2),
            "time_signature_numerator": self.time_signature_numerator,
            "time_signature_denominator": self.time_signature_denominator,
            "tempo_changes": self.tempo_changes,
            "key": self.key.value if self.key else None,
            "key_name": self.key_name,
            "mode": self.mode.value if self.mode else None,
            "key_confidence": round(self.key_confidence, 3),
            "chord_progression": [c.to_dict() for c in self.chord_progression],
            "sections": [s.to_dict() for s in self.sections],
            "total_bars": self.total_bars,
            "total_ticks": self.total_ticks,
            "instruments": [i.to_dict() for i in self.instruments],
            "has_bass": self.has_bass, "has_melody": self.has_melody,
            "has_chords": self.has_chords, "has_drums": self.has_drums,
            "energy_curve": [round(e, 3) for e in self.energy_curve],
            "danceability": self.danceability, "energy": self.energy,
            "valence": self.valence, "acousticness": self.acousticness,
            "instrumentalness": self.instrumentalness,
            "loudness": self.loudness, "speechiness": self.speechiness,
            "liveness": self.liveness,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SongDNA":
        dna = cls()
        dna.title = d.get("title", "")
        dna.artist = d.get("artist", "")
        dna.year = d.get("year", 0)
        dna.genre = d.get("genre", "")
        dna.source = d.get("source", "")
        dna.bpm = d.get("bpm", 120.0)
        dna.time_signature_numerator = d.get("time_signature_numerator", 4)
        dna.time_signature_denominator = d.get("time_signature_denominator", 4)
        dna.tempo_changes = [tuple(tc) for tc in d.get("tempo_changes", [])]
        key_val = d.get("key")
        dna.key = SongKey(key_val) if key_val is not None else None
        mode_val = d.get("mode")
        dna.mode = Mode(mode_val) if mode_val is not None else None
        dna.key_confidence = d.get("key_confidence", 0.0)
        dna.chord_progression = [ChordEvent.from_dict(c) for c in d.get("chord_progression", [])]
        dna.sections = [SongSection.from_dict(s) for s in d.get("sections", [])]
        dna.total_bars = d.get("total_bars", 0)
        dna.total_ticks = d.get("total_ticks", 0)
        dna.instruments = [InstrumentTrack.from_dict(i) for i in d.get("instruments", [])]
        dna.has_bass = d.get("has_bass", False)
        dna.has_melody = d.get("has_melody", False)
        dna.has_chords = d.get("has_chords", False)
        dna.has_drums = d.get("has_drums", False)
        dna.energy_curve = d.get("energy_curve", [])
        dna.danceability = d.get("danceability")
        dna.energy = d.get("energy")
        dna.valence = d.get("valence")
        dna.acousticness = d.get("acousticness")
        dna.instrumentalness = d.get("instrumentalness")
        dna.loudness = d.get("loudness")
        dna.speechiness = d.get("speechiness")
        dna.liveness = d.get("liveness")
        return dna

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str) -> "SongDNA":
        with open(path) as f:
            return cls.from_dict(json.load(f))

    def __repr__(self) -> str:
        parts = [f"SongDNA('{self.title}' by {self.artist}"]
        if self.key:
            parts.append(f"key={self.key_name}")
        parts.append(f"bpm={self.bpm:.0f}")
        parts.append(f"time_sig={self.time_signature}")
        if self.sections:
            parts.append(f"structure=[{self.section_summary}]")
        if self.instruments:
            parts.append(f"instruments={self.instrument_names}")
        parts.append(f"bars={self.total_bars}")
        return ", ".join(parts) + ")"
