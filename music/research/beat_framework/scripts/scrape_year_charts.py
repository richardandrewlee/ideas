#!/usr/bin/env python3
"""
Scrape Billboard Year-End Hot 100 charts for all years in our dataset.
Saves results to data/year_end_charts.json.

Usage:
    python scripts/scrape_year_charts.py
"""

import json
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# Years that have songs in our all-time dataset
ALL_YEARS = [
    1942, 1951, 1957, 1958, 1959, 1960, 1961, 1962, 1963, 1964,
    1966, 1967, 1968, 1969, 1970, 1971, 1972, 1973, 1975, 1976,
    1977, 1978, 1979, 1980, 1981, 1982, 1983, 1984, 1985, 1986,
    1987, 1988, 1989, 1990, 1991, 1992, 1993, 1994, 1995, 1996,
    1997, 1998, 1999, 2000, 2001, 2002, 2003, 2004, 2005, 2007,
    2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017,
    2018, 2019, 2020, 2021,
]

# Billboard year-end charts start from 1959
# Before that, they used different chart systems
BILLBOARD_YEAR_END_START = 1959

BASE_URL = "https://www.billboard.com/charts/year-end/{year}/hot-100-songs"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
DELAY = 2.0  # seconds between requests


def clean_artist(raw: str) -> str:
    """Clean up Billboard's artist formatting."""
    # Remove 'Featuring', 'With', 'X' collaboration markers
    text = re.sub(r'Featuring', ' ft. ', raw)
    text = re.sub(r'With(?=[A-Z])', ' with ', text)
    text = re.sub(r'X(?=[A-Z])', ' x ', text)
    # Fix '&' without spaces
    text = re.sub(r'&(?=\S)', ' & ', text)
    # Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def scrape_year(year: int) -> list[dict]:
    """Scrape the Billboard Year-End Hot 100 for a given year."""
    url = BASE_URL.format(year=year)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"  HTTP {resp.status_code} for {year}")
            return []
    except Exception as e:
        print(f"  Error for {year}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    rows = soup.select("div.o-chart-results-list-row-container")

    if not rows:
        print(f"  No chart entries found for {year}")
        return []

    tracks = []
    for i, row in enumerate(rows):
        title_el = row.select_one("h3#title-of-a-story")
        artist_el = row.select_one("h3#title-of-a-story + span")
        if not artist_el:
            artist_el = row.select_one("span.c-label.a-no-trucate")

        title = title_el.get_text(strip=True) if title_el else ""
        artist = clean_artist(artist_el.get_text(strip=True)) if artist_el else ""

        if title:
            tracks.append({
                "rank": i + 1,
                "title": title,
                "artist": artist,
                "year": year,
            })

    return tracks


def main():
    output_path = Path(__file__).parent.parent / "data" / "year_end_charts.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing data if resuming
    all_data = {}
    if output_path.exists():
        with open(output_path) as f:
            all_data = json.load(f)
        print(f"Loaded existing data: {len(all_data)} years")

    years_to_scrape = [
        y for y in ALL_YEARS
        if y >= BILLBOARD_YEAR_END_START and str(y) not in all_data
    ]

    print(f"Years to scrape: {len(years_to_scrape)}")
    print(f"(Skipping {len([y for y in ALL_YEARS if y < BILLBOARD_YEAR_END_START])} pre-{BILLBOARD_YEAR_END_START} years)")

    for i, year in enumerate(years_to_scrape):
        print(f"[{i+1}/{len(years_to_scrape)}] Scraping {year}...", end=" ")
        tracks = scrape_year(year)
        print(f"{len(tracks)} songs")

        if tracks:
            all_data[str(year)] = tracks

        # Save after each year (resume-friendly)
        with open(output_path, "w") as f:
            json.dump(all_data, f, indent=2)

        if i < len(years_to_scrape) - 1:
            time.sleep(DELAY)

    print(f"\nDone! Saved {len(all_data)} years to {output_path}")

    # Summary
    total_songs = sum(len(tracks) for tracks in all_data.values())
    print(f"Total songs: {total_songs}")


if __name__ == "__main__":
    main()
