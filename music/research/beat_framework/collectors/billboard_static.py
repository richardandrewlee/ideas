"""
Billboard Static Collector
---------------------------
Uses the curated Billboard Hot 100 All-Time dataset (304 songs, 1942-2021)
scraped from Dave's Music Database.

This collector works OFFLINE — no API keys or scraping needed.
Songs are pre-tagged with genres and can be filtered by year range.

Data file: data/billboard_hot100_enriched.json
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# BPM estimates for well-known songs (curated for beat generation accuracy)
# These are approximate BPMs based on widely known musical characteristics
KNOWN_BPMS = {
    "Blinding Lights": 171,
    "The Twist": 125,
    "Smooth": 116,
    "Uptown Funk!": 115,
    "Party Rock Anthem": 130,
    "I Gotta Feeling": 128,
    "Macarena (Bayside Boys Mix)": 103,
    "Shape of You": 96,
    "Physical": 124,
    "Hey Jude": 74,
    "Closer": 95,
    "Yeah!": 105,
    "Billie Jean": 117,
    "Every Breath You Take": 118,
    "Rolling in the Deep": 105,
    "Despacito": 89,
    "Old Town Road": 136,
    "Another One Bites the Dust": 110,
    "Gold Digger": 92,
    "Call Me Maybe": 120,
    "Happy": 160,
    "Royals": 85,
    "I Love Rock and Roll": 96,
    "Moves Like Jagger": 128,
    "Boom Boom Pow": 130,
    "Tik Tok": 120,
    "Hot Stuff": 120,
    "Le Freak": 120,
    "Night Fever": 110,
    "Stayin' Alive": 104,
    "Eye of the Tiger": 109,
    "We Found Love": 128,
    "Low": 128,
    "Levitating": 103,
    "God's Plan": 77,
    "Rockstar": 80,
    "Lose Yourself": 87,
    "Hotel California": 74,
    "When Doves Cry": 120,
    "I Will Survive": 117,
    "Like a Virgin": 116,
    "Beat It": 139,
    "Rock with You": 112,
    "Jump": 129,
    "Vogue": 116,
    "U Can't Touch This": 133,
    "Gangsta's Paradise": 80,
    "Hey Ya!": 160,
    "Umbrella": 87,
    "Hotline Bling": 100,
    "Stronger": 104,
    "September": 126,
    "Play That Funky Music": 108,
    "Funkytown": 127,
    "Africa": 93,
    "Radioactive": 68,
    "Shake It Off": 160,
    "All of Me": 63,
    "drivers license": 72,
    "Dynamite": 114,
    "Savage": 90,
    "good 4 u": 167,
    "Watermelon Sugar": 95,
    "Truth Hurts": 124,
    "Kiss Me More": 111,
    "I'm a Believer": 160,
    "Boogie Oogie Oogie": 126,
    "Da Ya Think I'm Sexy?": 116,
    "Upside Down": 118,
    "Sugar, Sugar": 120,
    "Bridge Over Troubled Water": 82,
    "Faith": 96,
    "Crazy for You": 95,
    "Locked Out of Heaven": 144,
    "Jack and Diane": 104,
    "Thrift Shop": 95,
    "California Gurls": 125,
    "Sorry": 100,
    "Thinking Out Loud": 79,
}


class BillboardStaticCollector:
    """
    Provides pre-curated Billboard Hot 100 All-Time data.
    No API keys or internet access needed.
    """

    def __init__(self, data_dir: Optional[str] = None):
        if data_dir:
            self.data_path = Path(data_dir) / "billboard_hot100_enriched.json"
        else:
            self.data_path = Path(__file__).parent.parent / "data" / "billboard_hot100_enriched.json"

        self.songs = []
        if self.data_path.exists():
            with open(self.data_path) as f:
                self.songs = json.load(f)
            logger.info(f"Loaded {len(self.songs)} songs from Billboard static dataset")
        else:
            logger.warning(f"Billboard static data not found at {self.data_path}")

    @property
    def available(self) -> bool:
        return len(self.songs) > 0

    def get_top_tracks(
        self,
        genre: str,
        year: int,
        limit: int = 100,
        year_range: int = 10,
    ) -> list[dict]:
        """
        Returns songs matching the genre, within ±year_range of the target year.

        Since this is an all-time list (not per-year), we filter by:
            1. Genre tag match
            2. Year proximity (weighted closer = better)
            3. Overall Billboard rank (lower = more iconic)

        Args:
            genre:      Target genre.
            year:       Target year.
            limit:      Max results.
            year_range: How many years ± to include.
        """
        if not self.available:
            return []

        genre_norm = genre.lower().replace(" ", "-")

        # Genre alias mapping
        genre_aliases = {
            "edm":           ["house", "disco"],
            "house":         ["house", "disco"],
            "techno":        ["house", "disco"],
            "dance":         ["house", "disco"],
            "r&b":           ["rnb"],
            "soul":          ["rnb", "funk"],
            "hip hop":       ["hip-hop"],
            "rap":           ["hip-hop"],
        }
        match_genres = set([genre_norm] + genre_aliases.get(genre_norm, []))

        results = []
        for song in self.songs:
            song_genres = set(g.lower() for g in song.get("genres", []))
            if not song_genres.intersection(match_genres):
                continue

            year_diff = abs(song["year"] - year)
            if year_diff > year_range:
                continue

            # Proximity score: closer year + lower rank = better
            proximity_score = (year_range - year_diff) / year_range
            rank_score = 1.0 - (song["rank"] / 310.0)
            combined_score = proximity_score * 0.6 + rank_score * 0.4

            bpm = KNOWN_BPMS.get(song["title"])

            results.append({
                "title":    song["title"],
                "artist":   song["artist"],
                "year":     song["year"],
                "genre":    genre,
                "source":   "billboard_static",
                "rank":     song["rank"],
                "bpm":      bpm,
                "score":    round(combined_score, 3),
            })

        results.sort(key=lambda x: -x["score"])
        return results[:limit]

    def get_genre_bpm_stats(self, genre: str) -> dict:
        """Returns BPM statistics for a genre from known BPMs."""
        tracks = self.get_top_tracks(genre, year=2000, year_range=50)
        bpms = [t["bpm"] for t in tracks if t.get("bpm")]
        if not bpms:
            return {}
        bpms.sort()
        n = len(bpms)
        return {
            "count": n,
            "min": bpms[0],
            "max": bpms[-1],
            "mean": round(sum(bpms) / n, 1),
            "median": bpms[n // 2],
        }

    def get_all_genres(self) -> dict[str, int]:
        """Returns all genres and their song counts."""
        from collections import Counter
        counts = Counter()
        for song in self.songs:
            for g in song.get("genres", []):
                counts[g] += 1
        return dict(counts.most_common())

    def get_decade_summary(self) -> dict:
        """Returns genre distribution by decade."""
        from collections import Counter, defaultdict
        decades: dict[int, Counter] = defaultdict(Counter)
        for song in self.songs:
            decade = (song["year"] // 10) * 10
            for g in song.get("genres", []):
                decades[decade][g] += 1
        return {
            decade: dict(counter.most_common())
            for decade, counter in sorted(decades.items())
        }
