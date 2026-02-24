"""
JSON Exporter
-------------
Exports a RawBeat and/or GenreProfile to structured JSON.

The JSON format is designed to be:
    1. Human-readable for inspection
    2. Machine-readable for further processing
    3. Compatible with web-based drum sequencers (e.g. Tone.js, WebAudioAPI)

Output schema (beat):
{
  "meta": {
    "genre": "house",
    "year": 2019,
    "bpm": 124.0,
    "grid_steps": 32,
    "steps_per_bar": 16,
    "ticks_per_beat": 480,
    "generated_at": "2025-01-01T00:00:00"
  },
  "grid": {
    "kick":         [100, null, null, null, 100, null, ...],
    "snare":        [null, null, null, null, null, null, ...],
    "hihat_closed": [80, 70, 75, 68, ...],
    ...
  },
  "hits": [
    {"instrument": "kick", "step": 0, "midi_note": 36, "velocity": 100, "tick_offset": -2},
    ...
  ]
}
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..generators.statistical_generator import RawBeat
from ..analysis.pattern_analyzer import GenreProfile
from ..analysis.drum_extractor import PRIMARY_INSTRUMENTS

logger = logging.getLogger(__name__)


class JsonExporter:
    """Exports beats and genre profiles to JSON."""

    def export_beat(
        self,
        beat: RawBeat,
        output_path: str,
        pretty: bool = True,
    ) -> str:
        """
        Export a RawBeat to JSON.

        Args:
            beat:        The beat to export.
            output_path: Destination .json path.
            pretty:      If True, write indented JSON (human-readable).

        Returns:
            The output path.
        """
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Build grid: instrument → [velocity or null per step]
        grid: dict[str, list] = {inst: [None] * beat.grid_steps for inst in PRIMARY_INSTRUMENTS}
        for hit in beat.hits:
            if hit.instrument in grid and 0 <= hit.step < beat.grid_steps:
                current = grid[hit.instrument][hit.step]
                if current is None or hit.velocity > current:
                    grid[hit.instrument][hit.step] = hit.velocity

        data = {
            "meta": {
                "genre":          beat.genre,
                "year":           beat.year,
                "bpm":            beat.bpm,
                "grid_steps":     beat.grid_steps,
                "steps_per_bar":  beat.steps_per_bar,
                "ticks_per_beat": beat.ticks_per_beat,
                "generated_at":   datetime.now().isoformat(),
            },
            "grid": grid,
            "hits": [
                {
                    "instrument":  h.instrument,
                    "step":        h.step,
                    "midi_note":   h.midi_note,
                    "velocity":    h.velocity,
                    "tick_offset": h.tick_offset,
                }
                for h in sorted(beat.hits, key=lambda x: (x.step, x.instrument))
            ],
        }

        with open(output_path, "w") as f:
            json.dump(data, f, indent=2 if pretty else None)

        logger.info(f"Beat JSON exported → {output_path}")
        return output_path

    def export_profile(
        self,
        profile: GenreProfile,
        output_path: str,
    ) -> str:
        """Export a GenreProfile to JSON."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        profile.save(output_path)
        logger.info(f"Profile JSON exported → {output_path}")
        return output_path

    def export_collection(
        self,
        beats: list[RawBeat],
        profiles: list[GenreProfile],
        output_path: str,
    ) -> str:
        """
        Export a collection of beats and profiles in a single JSON file.
        Useful for seeding a web-based drum sequencer UI.
        """
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        data = {
            "profiles": [p.to_dict() for p in profiles],
            "beats": [],
        }

        for beat in beats:
            grid = {inst: [None] * beat.grid_steps for inst in PRIMARY_INSTRUMENTS}
            for hit in beat.hits:
                if hit.instrument in grid and 0 <= hit.step < beat.grid_steps:
                    if grid[hit.instrument][hit.step] is None:
                        grid[hit.instrument][hit.step] = hit.velocity

            data["beats"].append({
                "meta": {
                    "genre":    beat.genre,
                    "year":     beat.year,
                    "bpm":      beat.bpm,
                },
                "grid": grid,
            })

        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Collection JSON exported → {output_path} ({len(beats)} beats)")
        return output_path
