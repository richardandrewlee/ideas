"""
Spotify Collector
-----------------
Pulls top-100 tracks per genre/year using the Spotify Web API via spotipy.

Setup:
    pip install spotipy
    Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in config.yaml
    (Get credentials at https://developer.spotify.com/dashboard)
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Genre → Spotify seed genre mapping
SPOTIFY_GENRE_MAP = {
    "house":    "house",
    "techno":   "techno",
    "reggae":   "reggae",
    "rock":     "rock",
    "hip-hop":  "hip-hop",
    "jazz":     "jazz",
    "pop":      "pop",
    "metal":    "metal",
    "soul":     "soul",
    "funk":     "funk",
    "rnb":      "r-n-b",
    "country":  "country",
    "blues":    "blues",
    "edm":      "edm",
    "drum-and-bass": "drum-and-bass",
}


class SpotifyCollector:
    """Fetches top tracks from Spotify for a given genre and year."""

    def __init__(self, client_id: str, client_secret: str):
        try:
            import spotipy
            from spotipy.oauth2 import SpotifyClientCredentials
            self.sp = spotipy.Spotify(
                auth_manager=SpotifyClientCredentials(
                    client_id=client_id,
                    client_secret=client_secret,
                )
            )
            self.available = True
        except ImportError:
            logger.warning("spotipy not installed. Run: pip install spotipy")
            self.available = False

    def get_top_tracks(self, genre: str, year: int, limit: int = 100) -> list[dict]:
        """
        Returns up to `limit` tracks for the given genre and year.

        Each track dict contains:
            title, artist, year, genre, source, spotify_id, bpm (if available)
        """
        if not self.available:
            return []

        genre_tag = SPOTIFY_GENRE_MAP.get(genre.lower(), genre.lower())
        results = []
        offset = 0
        batch = 50  # Spotify max per request

        while len(results) < limit:
            query = f"genre:{genre_tag} year:{year}"
            try:
                resp = self.sp.search(
                    q=query,
                    type="track",
                    limit=min(batch, limit - len(results)),
                    offset=offset,
                )
            except Exception as e:
                logger.error(f"Spotify search failed: {e}")
                break

            items = resp.get("tracks", {}).get("items", [])
            if not items:
                break

            for item in items:
                results.append({
                    "title":      item["name"],
                    "artist":     item["artists"][0]["name"],
                    "year":       year,
                    "genre":      genre,
                    "source":     "spotify",
                    "spotify_id": item["id"],
                    "popularity": item.get("popularity", 0),
                    "bpm":        None,  # Enriched separately via audio features
                })

            offset += batch
            if len(items) < batch:
                break

        # Sort by popularity and cap at limit
        results.sort(key=lambda x: x["popularity"], reverse=True)
        results = results[:limit]

        # Enrich with audio features (BPM, key, etc.) in batches of 100
        self._enrich_audio_features(results)

        logger.info(f"Spotify: {len(results)} tracks for {genre}/{year}")
        return results

    def _enrich_audio_features(self, tracks: list[dict]) -> None:
        """Adds BPM and other audio features in-place."""
        if not self.available:
            return

        ids = [t["spotify_id"] for t in tracks if t.get("spotify_id")]
        for i in range(0, len(ids), 100):
            batch_ids = ids[i : i + 100]
            try:
                features = self.sp.audio_features(batch_ids)
                id_to_features = {f["id"]: f for f in features if f}
                for track in tracks:
                    sid = track.get("spotify_id")
                    if sid and sid in id_to_features:
                        f = id_to_features[sid]
                        track["bpm"]        = round(f.get("tempo", 0))
                        track["time_sig"]   = f.get("time_signature", 4)
                        track["danceability"] = f.get("danceability", 0)
                        track["energy"]     = f.get("energy", 0)
            except Exception as e:
                logger.warning(f"Audio features fetch failed: {e}")
