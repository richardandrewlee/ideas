"""
Song Aggregator
---------------
Combines results from all collectors (Spotify, Last.fm, Billboard, Lakh),
deduplicates, and produces a unified song list for a given genre/year.
"""

import logging
from difflib import SequenceMatcher
from typing import Optional

logger = logging.getLogger(__name__)


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _dedup(tracks: list[dict], threshold: float = 0.85) -> list[dict]:
    """Remove near-duplicate entries based on title+artist similarity."""
    seen: list[dict] = []
    for track in tracks:
        title  = track.get("title", "")
        artist = track.get("artist", "")
        is_dup = False
        for existing in seen:
            t_sim = _similarity(title, existing.get("title", ""))
            a_sim = _similarity(artist, existing.get("artist", ""))
            if t_sim > threshold and a_sim > threshold:
                # Keep whichever has more metadata (e.g. BPM from Spotify)
                if track.get("bpm") and not existing.get("bpm"):
                    existing.update(track)
                is_dup = True
                break
        if not is_dup:
            seen.append(track)
    return seen


class SongAggregator:
    """
    Merges and deduplicates track lists from multiple sources.

    Usage:
        agg = SongAggregator(spotify, lastfm, billboard, lakh)
        songs = agg.get_songs(genre="house", year=2019, limit=100)
    """

    def __init__(
        self,
        spotify=None,
        lastfm=None,
        billboard=None,
        billboard_static=None,
        lakh=None,
    ):
        self.spotify          = spotify
        self.lastfm           = lastfm
        self.billboard        = billboard
        self.billboard_static = billboard_static
        self.lakh             = lakh

    def get_songs(
        self,
        genre: str,
        year: int,
        limit: int = 100,
    ) -> list[dict]:
        """
        Collects and merges tracks from all available sources.

        Returns a deduplicated list of up to `limit` tracks, sorted by
        source priority (Spotify > Billboard > Last.fm > Lakh).
        """
        all_tracks: list[dict] = []

        # Priority order: Spotify (has BPM) → Billboard (year-accurate) →
        #                 Last.fm (genre-accurate) → Lakh (MIDI available)
        sources = [
            ("spotify",          self.spotify),
            ("billboard",        self.billboard),
            ("billboard_static", self.billboard_static),
            ("lastfm",           self.lastfm),
            ("lakh",             self.lakh),
        ]

        for source_name, collector in sources:
            if collector is None:
                continue
            try:
                tracks = collector.get_top_tracks(genre=genre, year=year, limit=limit)
                all_tracks.extend(tracks)
                logger.info(f"{source_name}: contributed {len(tracks)} tracks")
            except Exception as e:
                logger.warning(f"{source_name} collector failed: {e}")

        # Deduplicate
        merged = _dedup(all_tracks)

        # Sort: prefer tracks with BPM (from Spotify), then by rank/popularity
        merged.sort(
            key=lambda t: (
                -int(bool(t.get("bpm"))),          # BPM-enriched first
                t.get("rank", 999),                 # Lower rank = higher position
                -t.get("popularity", 0),            # Higher popularity first
            )
        )

        result = merged[:limit]
        logger.info(
            f"Aggregated {len(result)} unique tracks for {genre}/{year} "
            f"from {len(all_tracks)} raw results"
        )
        return result

    def get_bpm_distribution(self, songs: list[dict]) -> dict:
        """Returns BPM stats from a song list (ignores songs without BPM)."""
        bpms = [s["bpm"] for s in songs if s.get("bpm")]
        if not bpms:
            return {}
        bpms_sorted = sorted(bpms)
        n = len(bpms)
        return {
            "count":  n,
            "min":    bpms_sorted[0],
            "max":    bpms_sorted[-1],
            "mean":   round(sum(bpms) / n, 1),
            "median": bpms_sorted[n // 2],
            "p25":    bpms_sorted[n // 4],
            "p75":    bpms_sorted[3 * n // 4],
        }
