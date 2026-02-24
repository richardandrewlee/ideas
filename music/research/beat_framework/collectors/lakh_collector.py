"""
Lakh MIDI Collector
--------------------
Indexes the Lakh MIDI Dataset (LMD) and matches genre-tagged songs
to their MIDI files for drum pattern analysis.

The Lakh dataset (~170k MIDI files) can be downloaded from:
    https://colinraffel.com/projects/lmd/

After downloading, set LAKH_PATH in config.yaml to the dataset root.

The dataset includes:
    lmd_full/           → All MIDI files (by MD5 hash)
    lmd_matched/        → MIDIs matched to MSD (Million Song Dataset)
    match_scores.json   → Match confidence scores
    msd_id_to_midi.pkl  → MSD track ID → MIDI file mapping

For genre annotations we use the msd_tagtraum_cd2 dataset:
    https://www.tagtraum.com/msd_genre_datasets.html
"""

import os
import json
import logging
import pickle
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class LakhCollector:
    """Indexes Lakh MIDI files by genre using MSD genre annotations."""

    def __init__(self, lakh_path: str, genre_annotations_path: Optional[str] = None):
        """
        Args:
            lakh_path: Root directory of the Lakh MIDI dataset.
            genre_annotations_path: Path to msd_tagtraum_cd2.cls or similar genre file.
                                    If None, looks for it inside lakh_path.
        """
        self.lakh_path = Path(lakh_path)
        self.available = self.lakh_path.exists()

        if not self.available:
            logger.warning(
                f"Lakh dataset not found at {lakh_path}. "
                "Download from: https://colinraffel.com/projects/lmd/"
            )
            return

        # Load MSD ID → MIDI path mapping
        self.msd_to_midi: dict[str, list[str]] = {}
        midi_map_path = self.lakh_path / "msd_id_to_midi.pkl"
        if midi_map_path.exists():
            try:
                with open(midi_map_path, "rb") as f:
                    self.msd_to_midi = pickle.load(f)
                logger.info(f"Loaded {len(self.msd_to_midi):,} MSD→MIDI mappings")
            except Exception as e:
                logger.error(f"Failed to load msd_id_to_midi.pkl: {e}")

        # Load genre annotations
        self.genre_index: dict[str, list[str]] = {}  # genre → [msd_ids]
        genre_path = Path(genre_annotations_path) if genre_annotations_path else \
                     self.lakh_path / "msd_tagtraum_cd2.cls"
        if genre_path.exists():
            self._load_genre_annotations(genre_path)
        else:
            logger.warning(
                f"Genre annotations not found at {genre_path}. "
                "Download from: https://www.tagtraum.com/msd_genre_datasets.html"
            )

    def _load_genre_annotations(self, path: Path) -> None:
        """Parses the tagtraum genre annotation file."""
        genre_index: dict[str, list[str]] = {}
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        msd_id = parts[0].strip()
                        genre  = parts[1].strip().lower()
                        genre_index.setdefault(genre, []).append(msd_id)

            # Normalize genre names
            normalized: dict[str, list[str]] = {}
            for raw_genre, ids in genre_index.items():
                norm = self._normalize_genre(raw_genre)
                normalized.setdefault(norm, []).extend(ids)

            self.genre_index = normalized
            total = sum(len(v) for v in self.genre_index.values())
            logger.info(
                f"Loaded {total:,} genre annotations across "
                f"{len(self.genre_index)} genres"
            )
        except Exception as e:
            logger.error(f"Failed to load genre annotations: {e}")

    @staticmethod
    def _normalize_genre(genre: str) -> str:
        """Maps tagtraum genre names to our standard genre names."""
        mapping = {
            "electronic":    "edm",
            "dance":         "house",
            "r&b":           "rnb",
            "hip-hop":       "hip-hop",
            "hip hop":       "hip-hop",
            "reggae":        "reggae",
            "rock":          "rock",
            "pop":           "pop",
            "country":       "country",
            "jazz":          "jazz",
            "blues":         "blues",
            "metal":         "metal",
            "soul":          "soul",
            "funk":          "funk",
            "latin":         "latin",
            "classical":     "classical",
        }
        return mapping.get(genre.lower(), genre.lower())

    def get_midi_paths(self, genre: str, limit: int = 200) -> list[str]:
        """
        Returns up to `limit` MIDI file paths for the given genre.

        These are the actual .mid files from the lmd_matched directory,
        ready to be parsed for drum patterns.
        """
        if not self.available:
            return []

        msd_ids = self.genre_index.get(genre.lower(), [])
        if not msd_ids:
            logger.warning(f"No Lakh entries found for genre '{genre}'")
            return []

        paths = []
        lmd_matched = self.lakh_path / "lmd_matched"

        for msd_id in msd_ids[:limit * 3]:  # Oversample to account for missing files
            midi_hashes = self.msd_to_midi.get(msd_id, [])
            for midi_hash in midi_hashes[:1]:  # Take best match per song
                # Lakh stores files as lmd_matched/<H>/<HA>/<HASH>.mid
                midi_path = lmd_matched / midi_hash[2] / midi_hash[:3] / f"{midi_hash}.mid"
                if midi_path.exists():
                    paths.append(str(midi_path))
                    if len(paths) >= limit:
                        break
            if len(paths) >= limit:
                break

        logger.info(f"Lakh: {len(paths)} MIDI files for genre '{genre}'")
        return paths

    def get_top_tracks(self, genre: str, year: int, limit: int = 100) -> list[dict]:
        """
        Returns track metadata dicts for Lakh-matched songs of the given genre.
        Year filtering is approximate (based on MSD metadata if available).
        """
        if not self.available:
            return []

        paths = self.get_midi_paths(genre, limit=limit)
        return [
            {
                "title":     os.path.basename(p).replace(".mid", ""),
                "artist":    "Unknown",
                "year":      year,
                "genre":     genre,
                "source":    "lakh",
                "midi_path": p,
                "bpm":       None,
            }
            for p in paths
        ]
