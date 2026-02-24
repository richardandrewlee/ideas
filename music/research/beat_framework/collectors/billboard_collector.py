"""
Billboard Collector
-------------------
Scrapes Billboard chart archives for historical top-100 data.
No API key required. Uses requests + BeautifulSoup.

Setup:
    pip install requests beautifulsoup4

Supported charts:
    hot-100              → Overall top 100 (all genres, any year)
    hot-country-songs    → Country
    hot-r-b-hip-hop-songs → R&B / Hip-Hop
    hot-rock-songs       → Rock
    dance-club-songs     → Dance / Electronic
    reggae-albums        → Reggae (album-level; track chart unavailable)
    hot-latin-songs      → Latin
"""

import logging
import time
from datetime import date

logger = logging.getLogger(__name__)

BILLBOARD_CHART_MAP = {
    "pop":      "hot-100",
    "country":  "hot-country-songs",
    "hip-hop":  "hot-r-b-hip-hop-songs",
    "rnb":      "hot-r-b-hip-hop-songs",
    "rock":     "hot-rock-songs",
    "house":    "dance-club-songs",
    "edm":      "dance-club-songs",
    "techno":   "dance-club-songs",
    "latin":    "hot-latin-songs",
    "reggae":   "hot-100",   # No dedicated track chart; fall back to Hot 100
    "jazz":     "hot-100",
    "metal":    "hot-rock-songs",
    "soul":     "hot-100",
    "funk":     "hot-100",
}

BILLBOARD_BASE = "https://www.billboard.com/charts"


class BillboardCollector:
    """Scrapes Billboard chart archives for a given genre and year."""

    def __init__(self, delay: float = 1.5):
        """
        Args:
            delay: Seconds between requests to be polite to Billboard servers.
        """
        try:
            import requests
            from bs4 import BeautifulSoup
            self.requests = requests
            self.BeautifulSoup = BeautifulSoup
            self.available = True
        except ImportError:
            logger.warning(
                "requests/beautifulsoup4 not installed. "
                "Run: pip install requests beautifulsoup4"
            )
            self.available = False

        self.delay = delay
        self.session = None

    def _get_session(self):
        if self.session is None:
            self.session = self.requests.Session()
            self.session.headers.update({
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            })
        return self.session

    def get_top_tracks(self, genre: str, year: int, limit: int = 100) -> list[dict]:
        """
        Scrapes end-of-year chart for the given genre from Billboard archives.

        Uses year-end charts when available (more stable than weekly snapshots).
        """
        if not self.available:
            return []

        chart = BILLBOARD_CHART_MAP.get(genre.lower(), "hot-100")
        results = []

        # Try year-end chart first (most accurate for top-100 of a year)
        results = self._fetch_year_end_chart(chart, year, genre, limit)

        # Fall back to sampling 4 weekly charts across the year
        if not results:
            logger.info(f"Year-end chart unavailable for {chart}/{year}, sampling weekly charts")
            results = self._fetch_weekly_samples(chart, year, genre, limit)

        logger.info(f"Billboard: {len(results)} tracks for {genre}/{year} (chart: {chart})")
        return results

    def _fetch_year_end_chart(self, chart: str, year: int, genre: str, limit: int) -> list[dict]:
        url = f"{BILLBOARD_BASE}/{chart}/{year}"
        return self._parse_chart_page(url, genre, year, limit)

    def _fetch_weekly_samples(self, chart: str, year: int, genre: str, limit: int) -> list[dict]:
        """Sample weekly charts at 4 points during the year and deduplicate."""
        sample_dates = [
            date(year, 3, 15),
            date(year, 6, 15),
            date(year, 9, 15),
            date(year, 12, 15),
        ]
        seen = set()
        results = []
        for d in sample_dates:
            url = f"{BILLBOARD_BASE}/{chart}/{d.strftime('%Y-%m-%d')}"
            tracks = self._parse_chart_page(url, genre, year, limit=50)
            for t in tracks:
                key = (t["title"].lower(), t["artist"].lower())
                if key not in seen:
                    seen.add(key)
                    results.append(t)
            time.sleep(self.delay)
            if len(results) >= limit:
                break
        return results[:limit]

    def _parse_chart_page(self, url: str, genre: str, year: int, limit: int) -> list[dict]:
        try:
            session = self._get_session()
            resp = session.get(url, timeout=10)
            if resp.status_code != 200:
                logger.warning(f"Billboard HTTP {resp.status_code} for {url}")
                return []
            time.sleep(self.delay)
        except Exception as e:
            logger.error(f"Billboard request failed: {e}")
            return []

        soup = self.BeautifulSoup(resp.text, "html.parser")
        results = []

        # Billboard uses a few different markup patterns across years
        # Pattern 1: li tags with class containing "chart-list__element"
        entries = soup.select("li.chart-list__element")

        # Pattern 2: div with data-rank attributes (newer layout)
        if not entries:
            entries = soup.select("div[data-rank]")

        for i, entry in enumerate(entries[:limit]):
            try:
                # Extract title
                title_el = (
                    entry.select_one(".chart-element__information__song")
                    or entry.select_one("h3#title-of-a-story")
                    or entry.select_one(".c-title")
                )
                # Extract artist
                artist_el = (
                    entry.select_one(".chart-element__information__artist")
                    or entry.select_one("span#title-of-a-story")
                    or entry.select_one(".c-label")
                )

                if not title_el or not artist_el:
                    continue

                title  = title_el.get_text(strip=True)
                artist = artist_el.get_text(strip=True)

                results.append({
                    "title":  title,
                    "artist": artist,
                    "year":   year,
                    "genre":  genre,
                    "source": "billboard",
                    "rank":   i + 1,
                    "bpm":    None,
                })
            except Exception:
                continue

        return results
