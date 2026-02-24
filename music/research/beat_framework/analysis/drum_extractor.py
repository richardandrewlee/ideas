"""
Drum Extractor
--------------
Identifies drum tracks in a parsed MIDI and extracts drum events
quantized to a rhythmic grid (default: 16th-note steps, 2 bars = 32 steps).

GM Drum Map (Channel 9, notes 35-81):
    36 = Kick (Bass Drum 1)      38 = Snare (Acoustic)
    40 = Snare (Electric)        42 = Closed Hi-Hat
    44 = Pedal Hi-Hat            46 = Open Hi-Hat
    49 = Crash Cymbal 1          51 = Ride Cymbal 1
    45 = Low Tom                 47 = Low-Mid Tom
    48 = Hi-Mid Tom              50 = High Tom
    37 = Side Stick              39 = Hand Clap
    54 = Tambourine              56 = Cowbell
    70 = Maracas                 75 = Claves
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from .midi_parser import ParsedMidi, MidiTrack, MidiNote

logger = logging.getLogger(__name__)

# Canonical GM drum instrument groups
GM_DRUM_MAP = {
    # Kicks
    35: "kick", 36: "kick",
    # Snares
    37: "snare", 38: "snare", 40: "snare",
    # Hi-Hats
    42: "hihat_closed", 44: "hihat_closed",
    46: "hihat_open",
    # Crashes / Cymbals
    49: "crash", 57: "crash", 55: "splash",
    51: "ride", 53: "ride", 59: "ride",
    52: "china",
    # Toms
    41: "tom_low", 43: "tom_low",
    45: "tom_mid", 47: "tom_mid",
    48: "tom_high", 50: "tom_high",
    # Auxiliary percussion
    39: "clap",
    54: "tambourine",
    56: "cowbell",
    70: "maracas",
    69: "cabasa",
    75: "claves",
    60: "bongo_hi", 61: "bongo_lo",
    62: "conga_mute", 63: "conga_hi", 64: "conga_lo",
}

# Instruments we care about for beat-making
PRIMARY_INSTRUMENTS = [
    "kick", "snare", "hihat_closed", "hihat_open",
    "crash", "ride", "tom_low", "tom_mid", "tom_high",
    "clap", "tambourine", "cowbell",
]

DRUM_CHANNEL = 9   # GM standard: channel 10 (0-indexed = 9)


@dataclass
class DrumStep:
    """A single hit on the drum grid."""
    instrument: str
    step:       int    # 0-based step index within the pattern
    pitch:      int    # Original MIDI note number
    velocity:   int    # 1-127
    tick_offset: int   # Tick deviation from the nearest grid point (timing feel)


@dataclass
class DrumPattern:
    """
    A quantized drum pattern extracted from a MIDI file.

    grid_steps: total steps (e.g. 32 = 2 bars at 16th note resolution)
    steps_per_bar: steps in one bar (typically 16)
    hits: all drum hits across all steps
    """
    grid_steps:     int = 32
    steps_per_bar:  int = 16
    bpm:            float = 120.0
    source_file:    str = ""
    genre:          str = ""
    hits:           list[DrumStep] = field(default_factory=list)

    def to_grid(self) -> dict[str, list[Optional[int]]]:
        """
        Returns a dict mapping instrument → velocity list of length grid_steps.
        None means no hit; int velocity means a hit.
        """
        grid: dict[str, list[Optional[int]]] = {
            inst: [None] * self.grid_steps for inst in PRIMARY_INSTRUMENTS
        }
        for hit in self.hits:
            if hit.instrument in grid and 0 <= hit.step < self.grid_steps:
                # If multiple hits on same step, keep loudest
                current = grid[hit.instrument][hit.step]
                if current is None or hit.velocity > current:
                    grid[hit.instrument][hit.step] = hit.velocity
        return grid

    def step_density(self) -> dict[str, float]:
        """Returns hit density (0–1) per instrument."""
        grid = self.to_grid()
        return {
            inst: sum(1 for v in steps if v is not None) / self.grid_steps
            for inst, steps in grid.items()
        }


class DrumExtractor:
    """
    Identifies and extracts drum patterns from ParsedMidi objects.
    """

    def __init__(
        self,
        grid_steps: int = 32,
        steps_per_bar: int = 16,
        quantize_threshold: float = 0.35,
    ):
        """
        Args:
            grid_steps: Total grid steps to extract (32 = 2 bars).
            steps_per_bar: Steps per bar (16 = 16th note resolution).
            quantize_threshold: Fraction of a step within which a note snaps
                                 to the nearest grid point (default: 35%).
        """
        self.grid_steps          = grid_steps
        self.steps_per_bar       = steps_per_bar
        self.quantize_threshold  = quantize_threshold

    def extract(self, midi: ParsedMidi, genre: str = "", source: str = "") -> list[DrumPattern]:
        """
        Extracts all drum patterns from a ParsedMidi.

        Returns a list of DrumPattern objects (one per recognized pattern section).
        If the MIDI is shorter than one bar, returns an empty list.
        """
        drum_tracks = self._find_drum_tracks(midi)
        if not drum_tracks:
            return []

        patterns: list[DrumPattern] = []
        ticks_per_step = midi.ticks_per_beat / (self.steps_per_bar / 4)

        for track in drum_tracks:
            if not track.notes:
                continue

            # Split into non-overlapping pattern windows
            windows = self._split_into_windows(track.notes, midi, ticks_per_step)

            for window_notes in windows:
                pattern = self._quantize_window(
                    notes=window_notes,
                    ticks_per_step=ticks_per_step,
                    bpm=midi.bpm,
                    genre=genre,
                    source=source,
                )
                if pattern and len(pattern.hits) >= 4:  # Minimum viable pattern
                    patterns.append(pattern)

        return patterns

    def _find_drum_tracks(self, midi: ParsedMidi) -> list[MidiTrack]:
        """Identifies tracks that contain drum content."""
        drum_tracks = []
        for track in midi.tracks:
            # Primary signal: channel 9
            if track.channel == DRUM_CHANNEL:
                drum_tracks.append(track)
                continue

            # Fallback: majority of notes are in the GM drum range (35–81)
            if track.notes:
                drum_notes = sum(1 for n in track.notes if 35 <= n.pitch <= 81)
                if drum_notes / len(track.notes) > 0.7:
                    drum_tracks.append(track)

        return drum_tracks

    def _split_into_windows(
        self,
        notes: list[MidiNote],
        midi: ParsedMidi,
        ticks_per_step: float,
    ) -> list[list[MidiNote]]:
        """
        Splits notes into fixed-size windows (self.grid_steps steps each).
        Returns the top 4 most-populated windows.
        """
        window_ticks = ticks_per_step * self.grid_steps

        if not notes:
            return []

        max_tick = max(n.tick for n in notes)
        num_windows = max(1, int(max_tick / window_ticks))

        windows: list[list[MidiNote]] = [[] for _ in range(num_windows)]
        for note in notes:
            idx = min(int(note.tick / window_ticks), num_windows - 1)
            windows[idx].append(note)

        # Return the 4 most populated windows (most representative patterns)
        windows_sorted = sorted(windows, key=len, reverse=True)
        return [w for w in windows_sorted[:4] if w]

    def _quantize_window(
        self,
        notes: list[MidiNote],
        ticks_per_step: float,
        bpm: float,
        genre: str,
        source: str,
    ) -> Optional[DrumPattern]:
        if not notes:
            return None

        # Find window start tick
        start_tick = min(n.tick for n in notes)
        # Snap start to nearest bar boundary
        ticks_per_bar = ticks_per_step * self.steps_per_bar
        bar_start = int(start_tick / ticks_per_bar) * ticks_per_bar

        pattern = DrumPattern(
            grid_steps=self.grid_steps,
            steps_per_bar=self.steps_per_bar,
            bpm=bpm,
            source_file=source,
            genre=genre,
        )

        for note in notes:
            instrument = GM_DRUM_MAP.get(note.pitch)
            if instrument is None:
                continue

            # Tick relative to bar start
            rel_tick = note.tick - bar_start
            # Nearest grid step
            exact_step = rel_tick / ticks_per_step
            step = int(round(exact_step))
            tick_offset = int(rel_tick - step * ticks_per_step)

            # Wrap to grid
            step = step % self.grid_steps

            # Only include hits within quantize threshold
            deviation_fraction = abs(tick_offset) / ticks_per_step
            if deviation_fraction > self.quantize_threshold:
                continue

            pattern.hits.append(DrumStep(
                instrument=instrument,
                step=step,
                pitch=note.pitch,
                velocity=note.velocity,
                tick_offset=tick_offset,
            ))

        return pattern
