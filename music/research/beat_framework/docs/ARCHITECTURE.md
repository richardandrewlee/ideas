# Beat Framework — Architecture Reference

> **Purpose:** Deep technical reference. Come here when you need to understand
> how a specific layer works or where to make changes.

---

## Pipeline Overview

```
 COLLECT              ANALYZE              GENERATE             EXPORT
 ───────              ───────              ────────             ──────
 Spotify API    ─┐
 Last.fm API    ─┤    MIDI Parser          Statistical     ─┐
 Billboard web  ─┼─→  Drum Extractor  ─→   Generator       ─┼─→  MIDI (.mid)
 Billboard JSON ─┤    Pattern Analyzer     Humanizer       ─┤    WAV  (.wav)
 Lakh MIDI      ─┘         │               Magenta (opt)   ─┘    JSON (.json)
                           ▼
                      GenreProfile
                      (cached to disk)
```

---

## File Map

```
beat_framework/
│
├── framework.py                  # Orchestrator — ties all layers together
├── generate.py                   # CLI entry point (argparse)
├── config.yaml                   # Credentials + paths template
├── requirements.txt
│
├── collectors/
│   ├── aggregator.py             # Merges all collectors, deduplicates
│   ├── billboard_static.py       # 304 offline songs (NO API key)
│   ├── billboard_collector.py    # Live Billboard scraper
│   ├── spotify_collector.py      # Spotify API (BPM, energy, danceability)
│   ├── lastfm_collector.py       # Last.fm API (genre-tagged tracks)
│   └── lakh_collector.py         # Lakh MIDI dataset indexer
│
├── analysis/
│   ├── midi_parser.py            # MIDI reader (mido + pure-Python fallback)
│   ├── drum_extractor.py         # Drum track detection → 32-step grid
│   └── pattern_analyzer.py       # GenreProfile builder + 6 built-in profiles
│
├── generators/
│   ├── statistical_generator.py  # Probability-based beat generation
│   ├── humanizer.py              # Swing, micro-timing, velocity variation
│   └── magenta_generator.py      # DrumsRNN continuation (optional)
│
├── exporters/
│   ├── midi_exporter.py          # Format 1 MIDI, multi-track
│   ├── wav_renderer.py           # FluidSynth rendering
│   └── json_exporter.py          # JSON for web UIs
│
├── data/
│   ├── billboard_hot100_enriched.json   # 304 songs (curated)
│   └── billboard_hot100_alltime.json    # Raw source
│
├── docs/                         # You are here
│   ├── STATUS.md                 # Living status doc (read first)
│   └── ARCHITECTURE.md           # This file
│
└── test_output/                  # 10 generated test files
    └── {genre}_{year}_v{nn}_{bpm}bpm.{mid,json}
```

---

## Layer 1: Collectors

Each collector returns a list of song dicts with this shape:

```python
{
    "title": str,
    "artist": str,
    "year": int,
    "genres": list[str],
    "bpm": float | None,        # Only Spotify + Billboard static
    "danceability": float | None,  # Only Spotify
    "energy": float | None,        # Only Spotify
    "midi_path": str | None,       # Only Lakh
    "source": str,                 # "spotify" | "lastfm" | "billboard" | "billboard_static" | "lakh"
    "rank": int | None,
}
```

### Aggregator (aggregator.py)

- Priority order: Spotify → Billboard → Last.fm → Lakh
- Deduplication: SequenceMatcher on title+artist (threshold 0.85)
- Enrichment: merges metadata from richer sources into sparse records
- Returns unified list sorted by: has BPM → rank → popularity

### Billboard Static (billboard_static.py)

- 304 songs from Billboard Hot 100 All-Time (1942-2021)
- Genre filtering uses proximity score: genre match + year distance + rank
- `KNOWN_BPMS` dict has ~110 manually curated BPMs
- **NOT YET CONNECTED to aggregator** — needs import + call added

### Collector Comparison

| Collector | API Key | BPM | Offline | Speed | Year Filter |
|-----------|---------|-----|---------|-------|-------------|
| Spotify | Required | Yes | No | Fast | Yes |
| Last.fm | Required | No | No | Medium | No |
| Billboard web | None | No | No | Slow | Yes |
| Billboard static | None | Partial | Yes | Instant | Approximate |
| Lakh MIDI | None | From MIDI | Yes (local) | Fast | Approximate |

---

## Layer 2: Analysis

### MIDI Parser (midi_parser.py)

- Primary: `mido` library
- Fallback: pure-Python MIDI reader (no dependencies)
- Returns parsed MIDI with tracks, events, tempo map

### Drum Extractor (drum_extractor.py)

- Identifies drum tracks: MIDI channel 9 or GM drum note range (35-81)
- Quantizes hits to 32-step grid (2 bars of 16th notes)
- Extracts up to 4 patterns per MIDI file
- Output: list of pattern dicts with hits per instrument per step

### Pattern Analyzer (pattern_analyzer.py)

- Aggregates extracted patterns into a GenreProfile
- Falls back to built-in profiles when data is sparse (<5 patterns)
- Blends 80% real data / 20% built-in when both available

### GenreProfile (dataclass)

```python
@dataclass
class GenreProfile:
    genre: str
    year: int
    num_patterns: int

    # Core: probability of a hit at each of 32 steps, per instrument
    hit_probability: dict[str, list[float]]   # {"kick": [0.95, 0.05, ...]}

    # Velocity distribution per instrument
    velocity_mean: dict[str, float]           # {"kick": 85}
    velocity_std: dict[str, float]            # {"kick": 10}

    # Humanization parameters
    timing_std: dict[str, float]              # Timing noise in ticks
    density: dict[str, float]                 # Hit density 0-1

    # BPM
    bpm_mean: float = 120.0
    bpm_std: float = 5.0
```

### Built-in Profiles

6 hardcoded: `house`, `techno`, `reggae`, `rock`, `hip-hop`, `jazz`

Each defines typical patterns:
- **House**: 4-on-the-floor kick, off-beat hi-hat, snare on 2 & 4
- **Techno**: Driving kick, sparse snare, heavy closed hi-hat
- **Reggae**: One-drop kick (beat 3), cross-stick snare, shuffle hat
- **Rock**: Kick on 1 & 3, snare on 2 & 4, steady 8th-note hat
- **Hip-hop**: Syncopated kick, snare on 2 & 4, varied hat patterns
- **Jazz**: Ride cymbal driven, kick feathering, ghost notes on snare

**Missing**: blues, metal, drum-and-bass, funk, soul, pop, country, rnb, edm

---

## Layer 3: Generators

### Statistical Generator (statistical_generator.py)

Input: GenreProfile → Output: RawBeat

1. Sample BPM from N(bpm_mean, bpm_std)
2. For each bar, for each step, for each instrument:
   - Roll against `hit_probability[instrument][step]`
   - If hit: sample velocity from N(velocity_mean, velocity_std)
   - Apply `variation_factor` for inter-beat differences
3. Last bar: optional drum fill logic (suppress kick/hat, boost toms/snare)

### Humanizer (humanizer.py)

Input: RawBeat + GenreProfile → Output: HumanizedBeat

1. **Swing**: Delay odd 16th-note steps by `swing_amount * tick_width`
2. **Micro-timing**: Gaussian noise per instrument (`timing_std`)
3. **Velocity accenting**: Beat 1 > 2 > 3 > 4 weighting
4. **Optional GrooVAE**: Magenta-learned humanization

Genre swing defaults:
- Jazz: 0.28 | Blues: 0.20 | Hip-hop: 0.15 | Funk: 0.12 | Reggae: 0.08
- Rock/Pop/House/Techno: 0.00-0.03

**Known bug**: `_apply_fill_logic()` has incorrect `self.steps_per_bar_ref` reference

### Magenta Generator (magenta_generator.py)

- DrumsRNN for creative continuation
- Requires: `magenta`, `note-seq`, checkpoint files
- Optional — framework works fully without it

---

## Layer 4: Exporters

### MIDI Exporter (midi_exporter.py)

- Format 1 MIDI (separate track per instrument group)
- Groups: Kick, Snare, Hi-Hats, Cymbals, Toms, Percussion
- Channel 10 (GM drum standard)
- Applies humanized tick offsets
- Loop support (repeats pattern N times)
- Fallback: pure-Python MIDI writer

### WAV Renderer (wav_renderer.py)

- FluidSynth (CLI or pyfluidsynth bindings)
- Auto-detects soundfont paths
- Requires system install + soundfont file
- Graceful skip if unavailable

### JSON Exporter (json_exporter.py)

Three export modes:
- **Beat JSON**: metadata + velocity grid + hit list
- **Profile JSON**: full GenreProfile for web seeding
- **Collection JSON**: multiple beats + profiles bundled

---

## Layer 5: CLI (generate.py)

Argparse-based. Key flags:

```
--genre / -g      Genre (repeatable for multi-genre)
--year / -y       Year
--count / -n      Variations to generate [4]
--bars / -b       Bars per beat [4]
--swing / -s      Swing override [genre default]
--bpm             BPM override
--seed            Random seed
--variation       Inter-beat variation 0-1 [0.15]
--config          Path to config.yaml
--rebuild-profile Force profile rebuild
```

---

## Data Flow Example

```
User runs: python generate.py --genre house --year 2019

1. CLI parses args → calls framework.quick_generate("house", 2019)

2. framework.build_profile("house", 2019):
   a. aggregator.get_songs("house", 2019, limit=100)
      → Spotify returns 80 songs with BPM
      → Billboard returns 40 songs (some overlap)
      → Dedup → 95 unique songs
   b. Find MIDI paths from Lakh-matched songs
   c. midi_parser.parse() each MIDI
   d. drum_extractor.extract() → patterns
   e. pattern_analyzer.analyze(patterns) → GenreProfile
      (if <5 patterns: blend with built-in house profile)
   f. Cache profile to disk

3. framework.generate("house", 2019, count=4):
   a. statistical_generator.generate_variations(profile, count=4)
      → 4 RawBeats with different random seeds
   b. humanizer.humanize(beat, profile) for each
      → swing=0.02, micro-timing, velocity accents

4. framework.export_all(beats, "./output/house_2019"):
   a. midi_exporter.export(beat) → .mid files
   b. wav_renderer.render(midi_path) → .wav files (if FluidSynth)
   c. json_exporter.export(beat) → .json files
```

---

## Instrument Mapping (GM Drum)

| Instrument | MIDI Note | Common Name |
|------------|-----------|-------------|
| kick | 36 | Bass Drum 1 |
| snare | 38 | Acoustic Snare |
| snare_rim | 37 | Side Stick |
| hihat_closed | 42 | Closed Hi-Hat |
| hihat_open | 46 | Open Hi-Hat |
| hihat_pedal | 44 | Pedal Hi-Hat |
| ride | 51 | Ride Cymbal 1 |
| crash | 49 | Crash Cymbal 1 |
| tom_high | 50 | High Tom |
| tom_mid | 47 | Low-Mid Tom |
| tom_low | 45 | Low Tom |
| clap | 39 | Hand Clap |

---

## Dependencies

**Required**: Python 3.9+
**Core** (no external deps needed): statistical generation, MIDI export, JSON export, Billboard static
**Optional**:
- `mido` — MIDI parsing (has pure-Python fallback)
- `spotipy` — Spotify API
- `pylast` — Last.fm API
- `requests` + `beautifulsoup4` — Billboard scraping
- `pyfluidsynth` — WAV rendering
- `magenta` + `note-seq` — ML generation/humanization
