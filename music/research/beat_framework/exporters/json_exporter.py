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

    def export_song_beat(
        self,
        song_beat,
        output_path: str,
        pretty: bool = True,
    ) -> str:
        """Export a SongBeat (full song) to JSON with section data."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        raw = song_beat.to_raw_beat()

        sections_data = []
        for s in song_beat.sections:
            sections_data.append({
                "section_type": s.section_type.value,
                "start_bar": s.start_bar,
                "bars": s.bars,
                "energy": s.energy,
                "hits": len(s.hits),
                "transitions": len(s.transition_hits),
            })

        data = {
            "meta": {
                "genre": song_beat.genre,
                "year": song_beat.year,
                "bpm": song_beat.bpm,
                "total_bars": song_beat.total_bars,
                "total_steps": song_beat.total_steps,
                "steps_per_bar": song_beat.steps_per_bar,
                "arrangement": song_beat.arrangement.name,
                "generated_at": datetime.now().isoformat(),
            },
            "sections": sections_data,
            "hits": [
                {
                    "instrument": h.instrument,
                    "step": h.step,
                    "midi_note": h.midi_note,
                    "velocity": h.velocity,
                    "tick_offset": h.tick_offset,
                }
                for h in sorted(raw.hits, key=lambda x: (x.step, x.instrument))
            ],
        }

        with open(output_path, "w") as f:
            json.dump(data, f, indent=2 if pretty else None)

        logger.info(f"Song JSON exported → {output_path}")
        return output_path

    def export_full_arrangement(
        self,
        full_arrangement,
        output_path: str,
        pretty: bool = True,
    ) -> str:
        """Export a FullArrangement (drums + bass + harmony) to JSON."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Drum hits
        drum_hits = []
        if full_arrangement.drums:
            raw = full_arrangement.drums.to_raw_beat()
            drum_hits = [
                {
                    "instrument": h.instrument,
                    "step": h.step,
                    "midi_note": h.midi_note,
                    "velocity": h.velocity,
                    "tick_offset": h.tick_offset,
                }
                for h in sorted(raw.hits, key=lambda x: x.step)
            ]

        # Bass hits
        bass_hits = []
        if full_arrangement.bass:
            bass_hits = [
                {
                    "pitch": h.pitch,
                    "velocity": h.velocity,
                    "step": h.step,
                    "duration_steps": h.duration_steps,
                }
                for h in sorted(full_arrangement.bass.hits, key=lambda x: x.step)
            ]

        # Harmony hits
        harmony_hits = []
        if full_arrangement.harmony:
            harmony_hits = [
                {
                    "pitches": h.pitches,
                    "velocity": h.velocity,
                    "step": h.step,
                    "duration_steps": h.duration_steps,
                }
                for h in sorted(full_arrangement.harmony.hits, key=lambda x: x.step)
            ]

        # Sections
        sections_data = []
        if full_arrangement.arrangement:
            for s in full_arrangement.arrangement.sections:
                sections_data.append({
                    "section_type": s.section_type.value,
                    "bars": s.bars,
                    "energy": s.energy,
                    "drum_density": s.drum_density,
                })

        # Chord progression
        chords_data = [
            {
                "root": c.root,
                "quality": c.quality,
                "name": c.name,
                "start_bar": c.start_bar,
            }
            for c in full_arrangement.chord_progression
        ]

        data = {
            "meta": {
                "genre": full_arrangement.genre,
                "year": full_arrangement.year,
                "bpm": full_arrangement.bpm,
                "key": full_arrangement.key.label if full_arrangement.key else None,
                "mode": full_arrangement.mode.value if full_arrangement.mode else None,
                "total_bars": full_arrangement.total_bars,
                "generated_at": datetime.now().isoformat(),
            },
            "arrangement": sections_data,
            "chord_progression": chords_data,
            "drums": {
                "hit_count": len(drum_hits),
                "hits": drum_hits,
            },
            "bass": {
                "program": full_arrangement.bass.midi_program if full_arrangement.bass else None,
                "hit_count": len(bass_hits),
                "hits": bass_hits,
            },
            "harmony": {
                "program": full_arrangement.harmony.midi_program if full_arrangement.harmony else None,
                "instrument": full_arrangement.harmony.instrument_name if full_arrangement.harmony else None,
                "hit_count": len(harmony_hits),
                "hits": harmony_hits,
            },
        }

        with open(output_path, "w") as f:
            json.dump(data, f, indent=2 if pretty else None)

        logger.info(f"Full arrangement JSON exported → {output_path}")
        return output_path
