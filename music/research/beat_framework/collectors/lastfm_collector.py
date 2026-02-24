"""
Last.fm Collector
-----------------
Pulls top tracks per genre (tag) using the Last.fm API via pylast.

Setup:
    pip install pylast
    Set LASTFM_API_KEY in config.yaml
    (Get a free key at https://www.last.fm/api/account/create)
"""

import logging

logger = logging.getLogger(__name__)

# Genre → Last.fm tag mapping (Last.fm uses freeform tags)
LASTFM_GENRE_MAP = {
    "house":          "house",
    "techno":         "techno",
    "reggae":         "reggae",
    "rock":           "rock",
    "hip-hop":        "hip hop",
    "jazz":           "jazz",
    "pop":            "pop",
    "metal":          "metal",
    "soul":           "soul",
    "funk":           "funk",
    "rnb":            "rnb",
    "country":        "country",
    "blues":          "blues",
    "edm":            "electronic",
    "drum-and-bass":  "drum and bass",
}


class LastFMCollector:
    """Fetches top-tagged tracks from Last.fm for a given genre."""

    def __init__(self, api_key: str, api_secret: str = ""):
        try:
            import pylast
            self.network = pylast.LastFMNetwork(
                api_key=api_key,
                api_secret=api_secret,
            )
            self.pylast = pylast
            self.available = True
        except ImportError:
            logger.warning("pylast not installed. Run: pip install pylast")
            self.available = False

    def get_top_tracks(self, genre: str, year: int, limit: int = 100) -> list[dict]:
        """
        Returns up to `limit` top tracks for the given genre tag.

        Note: Last.fm doesn't filter by year natively; year is stored as metadata.
        For year-specific results, combine with Spotify/Billboard.
        """
        if not self.available:
            return []

        tag_name = LASTFM_GENRE_MAP.get(genre.lower(), genre.lower())
        results = []

        try:
            tag = self.network.get_tag(tag_name)
            top_tracks = tag.get_top_tracks(limit=limit)

            for i, item in enumerate(top_tracks):
                track = item.item
                try:
                    title  = track.get_title()
                    artist = track.get_artist().get_name()
                except Exception:
                    continue

                results.append({
                    "title":      title,
                    "artist":     artist,
                    "year":       year,  # Approximate; Last.fm doesn't filter by year
                    "genre":      genre,
                    "source":     "lastfm",
                    "rank":       i + 1,
                    "bpm":        None,
                })

        except Exception as e:
            logger.error(f"Last.fm fetch failed for tag '{tag_name}': {e}")

        logger.info(f"Last.fm: {len(results)} tracks for {genre}/{year}")
        return results
