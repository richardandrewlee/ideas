#!/usr/bin/env python3
"""
Regenerate all 11 genre MD files with YouTube search links on song titles.

Reads existing genre files, finds song title patterns, and wraps each title
in a YouTube search link using the primary artist + title.

Pattern before:
  1. **"I'm a Believer"** — The Monkees *(#69)* [160 BPM]

Pattern after:
  1. **["I'm a Believer"](https://www.youtube.com/results?search_query=The+Monkees+I%27m+a+Believer)** — The Monkees *(#69)* [160 BPM]
"""

import re
import sys
from pathlib import Path
from urllib.parse import quote_plus

# Project root
ROOT = Path(__file__).resolve().parent.parent
GENRES_DIR = ROOT / "docs" / "genres"

GENRE_FILES = [
    "pop.md", "rnb.md", "hip-hop.md", "rock.md", "classic-pop.md",
    "disco.md", "country.md", "funk.md", "house.md", "reggaeton.md", "k-pop.md",
]

# Regex to match a song line in the MD files
# Captures: (prefix with number)(title)(suffix with artist etc.)
# Two variants: with and without existing YouTube link (in case of re-runs)
#
# Format: 1. **"Title"** — Artist *(#rank)* [BPM]
# Or already linked: 1. **["Title"](url)** — Artist *(#rank)* [BPM]
SONG_LINE_RE = re.compile(
    r'^(\d+\.\s+\*\*)'           # group 1: "1. **"
    r'(?:\[)?'                    # optional opening bracket (if already linked)
    r'"([^"]+)"'                  # group 2: the title text (inside quotes)
    r'(?:\]\([^)]*\))?'          # optional existing link (if already linked)
    r'(\*\*\s*—\s*)'             # group 3: "** — "
    r'(.+)$'                     # group 4: rest of line (artist + rank + bpm)
)

# Stats line pattern for "Highest ranked" which also has a song title + artist
# Format: - **Highest ranked**: #3 "Smooth" — Santana with Rob Thomas (1999)
STATS_SONG_RE = re.compile(
    r'^(- \*\*Highest ranked\*\*:\s*#\d+\s+)'   # group 1: prefix
    r'(?:\[)?'                                     # optional bracket
    r'"([^"]+)"'                                   # group 2: title
    r'(?:\]\([^)]*\))?'                            # optional existing link
    r'(\s*—\s*)'                                   # group 3: " — "
    r'(.+)$'                                       # group 4: artist (year)
)


def strip_collaborators(artist: str) -> str:
    """
    Strip featured/collaborative artists, keeping only the primary artist.
    
    Examples:
        "Santana with Rob Thomas" -> "Santana"
        "Katy Perry with Snoop Dogg" -> "Katy Perry"
        "Nelly with Kelly Rowland" -> "Nelly"
        "Cardi B with Bad Bunny & J Balvin" -> "Cardi B"
        "R. Kelly & Jay-Z" -> "R. Kelly"
        "Maroon 5 with Cardi B" -> "Maroon 5"
        "Dan + Shay with Justin Bieber" -> "Dan + Shay"
        "Eminem with Rihanna" -> "Eminem"
        "Robin Thicke with T.I. & Pharrell" -> "Robin Thicke"
        "LMFAO with Lauren Bennett & GoonRock" -> "LMFAO"
        "Coolio with L.V." -> "Coolio"
        "Dua Lipa with DaBaby" -> "Dua Lipa"
        "Usher with Lil' Jon & Ludacris" -> "Usher"
        "Doja Cat with SZA" -> "Doja Cat"
        "Post Malone with 21 Savage" -> "Post Malone"
        "Megan Thee Stallion with Beyonce" -> "Megan Thee Stallion"
    
    But keep:
        "Simon & Garfunkel" -> "Simon & Garfunkel" (this is a duo name)
        "Daryl Hall & John Oates" -> "Daryl Hall & John Oates" (duo)
        "KC & the Sunshine Band" -> "KC & the Sunshine Band" (band name)
        "Earth, Wind & Fire" -> "Earth, Wind & Fire" (band name)
    
    Strategy: split on " with ", " ft.", " ft ", " featuring ", " x " first (these
    always indicate collaboration). For " & ", only split if it appears to be
    a collaboration (not a band name). We use a heuristic: known band names
    are preserved.
    """
    # First, handle "with" — this always indicates collaboration
    for sep in [" with ", " ft. ", " ft ", " featuring "]:
        idx = artist.lower().find(sep.lower())
        if idx != -1:
            return artist[:idx].strip()
    
    # For " & " — we need to be more careful. Some are bands/duos.
    # Known band/duo names that use "&" should NOT be split:
    known_ampersand_acts = {
        "simon & garfunkel",
        "daryl hall & john oates",
        "kc & the sunshine band",
        "earth, wind & fire",
        "c + c music factory",
        "dan + shay",
        "rick dees & his cast of idiots",
        "walter murphy & the big apple band",
        "joan jett & the blackhearts",
        "jay sean & lil wayne",
        "puff daddy & mase",
        "r. kelly & jay-z",
        "rihanna & calvin harris",
        "flo rida & t-pain",
        "brandy & monica",
        "zager & evans",
    }
    
    if artist.lower() in known_ampersand_acts:
        return artist
    
    # For " x " collaborations (rare in this dataset but handle it)
    if " x " in artist.lower():
        # Check if it's at a word boundary
        parts = re.split(r'\s+x\s+', artist, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) > 1:
            return parts[0].strip()
    
    return artist


def build_youtube_url(artist: str, title: str) -> str:
    """Build a YouTube search URL for an artist + title."""
    primary_artist = strip_collaborators(artist)
    query = f"{primary_artist} {title}"
    encoded = quote_plus(query)
    return f"https://www.youtube.com/results?search_query={encoded}"


def process_song_line(line: str) -> str:
    """Process a single song line, adding YouTube link to the title."""
    m = SONG_LINE_RE.match(line)
    if not m:
        return line
    
    prefix = m.group(1)   # "1. **"
    title = m.group(2)    # the song title
    mid = m.group(3)      # "** — "
    rest = m.group(4)     # "Artist *(#rank)* [BPM]"
    
    # Extract the artist from rest: everything before " *(" 
    artist_match = re.match(r'^(.+?)\s*\*\(#\d+\)\*', rest)
    if artist_match:
        artist = artist_match.group(1).strip()
    else:
        # Fallback: take everything before the first "*"
        artist = rest.split('*')[0].strip()
        if artist.endswith('—'):
            artist = artist[:-1].strip()
    
    url = build_youtube_url(artist, title)
    
    return f'{prefix}["{title}"]({url}){mid}{rest}'


def process_stats_line(line: str) -> str:
    """Process a stats line with 'Highest ranked' that mentions a song."""
    m = STATS_SONG_RE.match(line)
    if not m:
        return line
    
    prefix = m.group(1)   # "- **Highest ranked**: #3 "
    title = m.group(2)    # the song title
    mid = m.group(3)      # " — "
    rest = m.group(4)     # "Artist (year)"
    
    # Extract artist: everything before the (year) at the end
    artist_match = re.match(r'^(.+?)\s*\(\d{4}\)$', rest)
    if artist_match:
        artist = artist_match.group(1).strip()
    else:
        artist = rest.strip()
    
    url = build_youtube_url(artist, title)
    
    return f'{prefix}["{title}"]({url}){mid}{rest}'


def process_file(filepath: Path) -> tuple[int, int]:
    """Process a single genre MD file. Returns (songs_linked, stats_linked)."""
    content = filepath.read_text(encoding="utf-8")
    lines = content.split("\n")
    
    songs_linked = 0
    stats_linked = 0
    new_lines = []
    
    for line in lines:
        if SONG_LINE_RE.match(line):
            new_line = process_song_line(line)
            if new_line != line:
                songs_linked += 1
            new_lines.append(new_line)
        elif STATS_SONG_RE.match(line):
            new_line = process_stats_line(line)
            if new_line != line:
                stats_linked += 1
            new_lines.append(new_line)
        else:
            new_lines.append(line)
    
    new_content = "\n".join(new_lines)
    filepath.write_text(new_content, encoding="utf-8")
    
    return songs_linked, stats_linked


def process_readme(filepath: Path) -> int:
    """Process the README.md index — no song titles to link there, but check."""
    content = filepath.read_text(encoding="utf-8")
    # The README only has a table with genre info, no song titles with the pattern
    # But let's check just in case
    lines = content.split("\n")
    changed = 0
    new_lines = []
    
    for line in lines:
        if SONG_LINE_RE.match(line):
            new_line = process_song_line(line)
            if new_line != line:
                changed += 1
            new_lines.append(new_line)
        else:
            new_lines.append(line)
    
    if changed > 0:
        new_content = "\n".join(new_lines)
        filepath.write_text(new_content, encoding="utf-8")
    
    return changed


def main():
    total_songs = 0
    total_stats = 0
    
    print("Adding YouTube search links to genre MD files...\n")
    
    for fname in GENRE_FILES:
        fpath = GENRES_DIR / fname
        if not fpath.exists():
            print(f"  WARNING: {fname} not found, skipping")
            continue
        
        songs, stats = process_file(fpath)
        total_songs += songs
        total_stats += stats
        print(f"  {fname:<20s}  {songs:3d} songs linked, {stats} stats linked")
    
    # Process README.md
    readme_path = GENRES_DIR / "README.md"
    if readme_path.exists():
        readme_changed = process_readme(readme_path)
        print(f"\n  README.md            {readme_changed:3d} links added")
    
    print(f"\nDone! {total_songs} song links + {total_stats} stats links added across {len(GENRE_FILES)} genre files.")


if __name__ == "__main__":
    main()
