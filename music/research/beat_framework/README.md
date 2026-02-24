# Beat Framework

Generate genre-authentic drum beats informed by the **top 100 songs** of any genre and year.

Pulls data from **Spotify**, **Last.fm**, **Billboard**, and the **Lakh MIDI Dataset**, analyzes their drum patterns statistically, then generates new beats using a **hybrid statistical + Magenta ML** pipeline.

## Output formats
- `.mid` — Multi-track MIDI, drop directly into your DAW
- `.wav` — Rendered audio via FluidSynth
- `.json` — Machine-readable pattern data for custom UIs / Tone.js

---

## Quick Start (no API keys needed)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Generate 4 house beats from 2019 (uses built-in genre profiles)
python generate.py --genre house --year 2019

# 3. Output lands in ./output/house_2019/
```

---

## Setup with API keys (recommended for best results)

### 1. Spotify API
Get free credentials at https://developer.spotify.com/dashboard

Enables: BPM data, danceability/energy per song, year-accurate top-100.

### 2. Last.fm API
Get free key at https://www.last.fm/api/account/create

Enables: Genre-tagged top tracks with deep historical coverage.

### 3. Billboard (no key needed)
Automatic. Scrapes Billboard chart archives for year-end charts.

### 4. Lakh MIDI Dataset
Download from https://colinraffel.com/projects/lmd/

Genre annotations from https://www.tagtraum.com/msd_genre_datasets.html

Enables: Real drum pattern analysis from 170k songs.

### 5. WAV rendering (FluidSynth + soundfont)
```bash
# macOS
brew install fluid-synth
# Ubuntu
sudo apt install fluidsynth libfluidsynth-dev
pip install pyfluidsynth

# Download a free GM soundfont:
# https://musical-artifacts.com/artifacts/728  (GeneralUser GS — recommended)
```

### 6. Fill in config.yaml
```yaml
spotify:
  client_id:     "your_id"
  client_secret: "your_secret"
lastfm:
  api_key: "your_key"
lakh:
  path: "/path/to/lmd_full"
  genre_annotations: "/path/to/msd_tagtraum_cd2.cls"
paths:
  soundfont: "/path/to/GeneralUser_GS.sf2"
```

### 7. Magenta (optional, for ML generation)
```bash
pip install magenta note-seq
# Download DrumsRNN checkpoint to ~/.magenta/drums_rnn/
```

---

## CLI Usage

```bash
# Basic
python generate.py --genre house --year 2019

# Multiple genres
python generate.py --genre house --genre techno --genre reggae --year 2020

# More variations, 8 bars each
python generate.py --genre rock --year 2015 --count 8 --bars 8

# With swing (jazz-feel)
python generate.py --genre jazz --year 2010 --swing 0.25

# Force BPM
python generate.py --genre techno --year 2022 --bpm 138

# Full quality (with config)
python generate.py --genre house --year 2019 --config config.yaml --magenta-continuation

# Rebuild cached profile (re-analyze from scratch)
python generate.py --genre pop --year 2023 --rebuild-profile
```

### All options
```
--genre / -g      Genre name (repeatable)           [required]
--year  / -y      Year                               [required]
--count / -n      Beat variations to generate        [default: 4]
--bars  / -b      Bars per beat                      [default: 4]
--swing / -s      Swing amount 0.0–0.33              [default: genre-specific]
--bpm             Override BPM
--loop            MIDI loop count                    [default: 2]
--seed            Random seed for reproducibility
--variation       Variation between beats 0–1        [default: 0.15]
--no-magenta      Disable Magenta (faster)
--magenta-continuation  Add a DrumsRNN bonus beat
--output / -o     Output directory                   [default: ./output]
--no-wav          Skip WAV rendering
--no-json         Skip JSON export
--config          Path to config.yaml
--rebuild-profile Ignore cache, rebuild profile
--verbose / -v    Verbose logging
```

---

## Python API

```python
from beat_framework import BeatFramework

# Load with config
fw = BeatFramework.from_config("config.yaml")

# Or minimal setup
fw = BeatFramework(
    spotify_client_id="...",
    spotify_client_secret="...",
    soundfont_path="~/soundfonts/GeneralUser_GS.sf2",
)

# Build a genre profile (cached after first run)
profile = fw.build_profile("house", 2019)

# Generate beats
beats = fw.generate("house", 2019, count=4, num_bars=4)

# Export everything
fw.export_all(beats, output_dir="./output/house_2019")

# One-shot shortcut
fw.quick_generate("house", 2019, "./output/house_2019")
```

---

## Architecture

```
beat_framework/
├── collectors/          Data gathering from all sources
│   ├── spotify_collector.py      Top tracks + BPM via Spotify API
│   ├── lastfm_collector.py       Top tracks by genre tag
│   ├── billboard_collector.py    Year-end chart scraper
│   ├── lakh_collector.py         MIDI file index from Lakh dataset
│   └── aggregator.py             Merge + deduplicate all sources
│
├── analysis/            Pattern extraction and modeling
│   ├── midi_parser.py            MIDI file parser (mido + pure-Python fallback)
│   ├── drum_extractor.py         Drum track detection + quantization
│   └── pattern_analyzer.py      Statistical profile builder + built-in profiles
│
├── generators/          Beat generation
│   ├── statistical_generator.py  Probability-based pattern generation
│   ├── humanizer.py              Micro-timing + velocity variation
│   └── magenta_generator.py      DrumsRNN continuation (optional)
│
├── exporters/           Output formats
│   ├── midi_exporter.py          Multi-track MIDI writer
│   ├── wav_renderer.py           FluidSynth WAV rendering
│   └── json_exporter.py          Beat + profile JSON export
│
├── framework.py         Main BeatFramework orchestrator
├── generate.py          CLI entry point
├── config.yaml          Configuration template
└── requirements.txt     Python dependencies
```

## Supported Genres

`house` · `techno` · `reggae` · `rock` · `hip-hop` · `jazz` · `pop` · `metal` · `soul` · `funk` · `rnb` · `country` · `blues` · `edm` · `drum-and-bass`

---

Built with ❤️ for beat makers.
