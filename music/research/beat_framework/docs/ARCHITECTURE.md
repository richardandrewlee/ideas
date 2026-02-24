# Beat Framework — Architecture Reference

> **Purpose:** Deep technical reference. Come here when you need to understand
> how a specific layer works or where to make changes.

---

## Pipeline Overview

```
 COLLECT              ANALYZE              GENERATE              EXPORT
 ───────              ───────              ────────              ──────
 Spotify API    ─┐    MIDI Parser          Statistical Gen  ─┐
 Last.fm API    ─┤    Drum Extractor       Humanizer        ─┤
 Billboard web  ─┼─→  Pattern Analyzer     Song Generator   ─┼─→  MIDI (.mid)
 Billboard JSON ─┤    Key Detector         Bass Generator   ─┤    WAV  (.wav)
 Lakh MIDI      ─┘    Chord Extractor      Harmony Gen      ─┘    JSON (.json)
                       Structure Detector   Multi-Instrument
                       Instrument ID        Arrangement Engine
                       Song Analyzer
                            │
                            ▼
                    SongDNA + GenreProfile
                    (cached to disk)
```

**Three generation paths:**
1. `generate()` → beat loops (RawBeat) → `export_all()`
2. `generate_song()` → full percussion (SongBeat) → `export_song()`
3. `generate_full_production()` → drums+bass+harmony (FullArrangement) → `export_full_arrangement()`

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
│   ├── spotify_collector.py      # Spotify API (BPM, energy, key, mode, valence, etc.)
│   ├── lastfm_collector.py       # Last.fm API (genre-tagged tracks)
│   └── lakh_collector.py         # Lakh MIDI dataset indexer
│
├── analysis/
│   ├── midi_parser.py            # MIDI reader — all events (mido + pure-Python fallback)
│   ├── drum_extractor.py         # Drum track detection → 32-step grid
│   ├── pattern_analyzer.py       # GenreProfile builder + 6 built-in profiles
│   ├── song_dna.py               # SongDNA data model (key, chords, structure, instruments)
│   ├── key_detector.py           # Krumhansl-Schmuckler key detection
│   ├── chord_extractor.py        # Chord progression extraction (template matching)
│   ├── structure_detector.py     # Section detection (self-similarity matrix)
│   ├── instrument_identifier.py  # MIDI track classification by role
│   ├── song_analyzer.py          # Orchestrator for all analysis modules
│   └── section_profile_builder.py # Per-section drum profile scaling
│
├── generators/
│   ├── statistical_generator.py  # Probability-based beat generation
│   ├── humanizer.py              # Swing, micro-timing, velocity, section-aware
│   ├── magenta_generator.py      # DrumsRNN continuation (optional)
│   ├── arrangement.py            # 12 genre arrangement templates
│   ├── song_generator.py         # Full song percussion with transitions
│   ├── bass_generator.py         # Bass line following chord progressions
│   ├── harmony_generator.py      # Chord voicings (pad, stab, power chord, etc.)
│   └── multi_instrument_generator.py  # Orchestrates drums + bass + harmony
│
├── exporters/
│   ├── midi_exporter.py          # Format 1 MIDI, multi-track, multi-instrument
│   ├── wav_renderer.py           # FluidSynth rendering
│   └── json_exporter.py          # JSON for web UIs + full arrangements
│
├── data/
│   ├── billboard_hot100_enriched.json   # 304 songs (curated)
│   └── billboard_hot100_alltime.json    # Raw source
│
├── docs/
│   ├── STATUS.md                 # Living status doc (read first)
│   └── ARCHITECTURE.md           # This file
│
└── test_output/
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
    "bpm": float | None,
    "danceability": float | None,   # Spotify
    "energy": float | None,         # Spotify
    "key": int | None,              # Spotify (0-11)
    "mode": int | None,             # Spotify (0=minor, 1=major)
    "valence": float | None,        # Spotify
    "loudness": float | None,       # Spotify
    "acousticness": float | None,   # Spotify
    "instrumentalness": float | None, # Spotify
    "speechiness": float | None,    # Spotify
    "liveness": float | None,       # Spotify
    "duration_ms": int | None,      # Spotify
    "midi_path": str | None,        # Lakh
    "source": str,
    "rank": int | None,
}
```

### Aggregator (aggregator.py)

- Priority order: Spotify → Billboard Static → Billboard → Last.fm → Lakh
- Deduplication: SequenceMatcher on title+artist (threshold 0.85)
- Enrichment: merges metadata from richer sources into sparse records
- Returns unified list sorted by: has BPM → rank → popularity

### Collector Comparison

| Collector | API Key | BPM | Key | Offline | Speed |
|-----------|---------|-----|-----|---------|-------|
| Spotify | Required | Yes | Yes | No | Fast |
| Last.fm | Required | No | No | No | Medium |
| Billboard web | None | No | No | No | Slow |
| Billboard static | None | Partial | No | Yes | Instant |
| Lakh MIDI | None | From MIDI | From MIDI | Yes (local) | Fast |

---

## Layer 2: Analysis

### SongDNA (song_dna.py) — Central Data Model

```python
@dataclass
class SongDNA:
    # Identity
    title, artist, year, genre, source

    # Tempo & Meter
    bpm: float
    time_signature: str  # "4/4"
    tempo_changes: list

    # Key & Harmony
    key: SongKey          # Enum: C, C_SHARP, D, ... B
    mode: Mode            # Enum: MAJOR, MINOR, DORIAN, MIXOLYDIAN
    key_confidence: float
    chord_progression: list[ChordEvent]  # (root, quality, start_bar, confidence)

    # Structure
    sections: list[SongSection]      # (type, start_bar, end_bar, energy, chords)
    energy_curve: list[float]        # Per-bar energy 0.0-1.0

    # Instruments
    instruments: list[InstrumentTrack]  # (name, program, channel, role, note_range)

    # Spotify features (optional)
    spotify_features: dict

    # Serialization
    save() / load() / to_dict() / from_dict()
```

### MIDI Parser (midi_parser.py) — Extended

Now captures ALL MIDI events:
- `MidiNote`: pitch, velocity, start_tick, duration_ticks, channel
- `MidiEvent`: key_signature, time_signature, program_change, control_change, marker, set_tempo
- `MidiTrack`: notes, events, program, channel, name
- `ParsedMidi`: tracks, key_signature, time_signatures, tempo_map, markers
- Helpers: `get_all_notes()`, `get_non_drum_notes()`, `tick_to_bar()`

### Key Detector (key_detector.py)

- Krumhansl-Kessler major/minor profiles
- Duration × velocity weighted pitch-class histogram from non-drum notes
- Correlates against 24 key profiles (12 major + 12 minor)
- Fuses MIDI detection with Spotify key/mode (boosts confidence when they agree)

### Chord Extractor (chord_extractor.py)

- 13 chord templates: major, minor, dom7, min7, maj7, dim, dim7, aug, sus2, sus4, 5, add9, 6
- Segments non-drum/non-bass notes into beat-aligned windows
- Template matching: compare pitch-class sets against all templates × 12 roots
- Merges consecutive identical chords

### Structure Detector (structure_detector.py)

- Per-bar feature vectors: note density, velocity, instrument count, drum presence
- Self-similarity matrix comparing 4/8-bar blocks
- Greedy clustering with similarity threshold 0.6
- Labels by energy: highest recurring = chorus, lower = verse, unique = bridge
- Falls back to MIDI markers if present

### Instrument Identifier (instrument_identifier.py)

- Two-pass: first by GM program/channel/name, then by heuristics
- Bass: median pitch < 48, mostly monophonic
- Melody: highest varied-pitch track
- Chords/Pads: polyphonic, mid-register

---

## Layer 3: Generators

### Statistical Generator (statistical_generator.py)

Input: GenreProfile → Output: RawBeat

1. Sample BPM from N(bpm_mean, bpm_std)
2. For each bar/step/instrument: roll against hit_probability
3. Last bar: optional fill logic (fixed: `_apply_fill_logic` now takes `steps_per_bar` param)

### Arrangement Engine (arrangement.py)

12 built-in genre templates:

| Genre | Structure | Total Bars |
|-------|-----------|------------|
| house | intro→verse→breakdown→drop→verse→breakdown→drop→outro | ~64 |
| techno | intro→build→drop→breakdown→build→drop→outro | ~64 |
| rock | intro→verse→chorus→verse→chorus→bridge→chorus→outro | ~64 |
| hip-hop | intro→verse→chorus→verse→chorus→bridge→chorus→outro | ~64 |
| jazz | intro→head→solo→solo→head→outro | ~64 |
| reggae | intro→verse→chorus→verse→chorus→verse→chorus→outro | ~64 |
| pop | intro→verse→prechorus→chorus→verse→prechorus→chorus→bridge→chorus→outro | ~72 |

Each section has: type, bars, energy (0.0-1.0), drum_density, transition_type

### Song Generator (song_generator.py)

- `SongBeat` with list of `SectionBeat` (hits + transition_hits)
- Section-aware: scales drum density per section
- Transitions: fills (tom cascade), builds (snare ramp), crash accents
- Phrase-end fills every 4 bars within sections

### Bass Generator (bass_generator.py)

11 genre rhythm templates:

| Genre | Style | Octave | GM Program |
|-------|-------|--------|------------|
| house | root_pump | 2 | 38 (Synth Bass) |
| techno | driving | 2 | 38 |
| rock | root_fifth | 2 | 33 (Electric Bass) |
| hip-hop | syncopated_808 | 1 | 38 |
| jazz | walking | 2 | 32 (Acoustic Bass) |
| funk | syncopated | 2 | 36 (Slap Bass) |
| metal | chugging | 1 | 33 |

Pitch selection: root (75%), fifth (15%), octave (10%). Walking bass uses scale passing tones.

### Harmony Generator (harmony_generator.py)

12 genre voicing styles:

| Genre | Style | Instrument | GM Program |
|-------|-------|------------|------------|
| house | pad | synth_pad | 89 (Pad 2) |
| rock | power_chord | guitar | 29 (Overdriven Guitar) |
| hip-hop | stab | piano | 0 (Grand Piano) |
| jazz | extended | piano | 0 |
| reggae | skank | organ | 16 (Drawbar Organ) |
| funk | stab | electric_piano | 4 (Electric Piano) |
| metal | power_chord | guitar | 30 (Distortion Guitar) |

Rhythm patterns per style: pad=whole note, stab=syncopated, skank=off-beat, block=half notes

### Multi-Instrument Generator (multi_instrument_generator.py)

- `FullArrangement`: drums (SongBeat) + bass (BassLine) + harmony (HarmonyPart) + chord progression
- Orchestrates all generators with shared arrangement template
- `from_song_dna()`: generate informed by analyzed song DNA
- Default progressions: I-V-vi-IV (major), i-VI-III-VII (minor)

### Humanizer (humanizer.py)

- `humanize(beat)` — per-beat: swing, micro-timing, velocity accents
- `humanize_song(song_beat)` — per-section: scales timing/velocity by energy level
- Genre swing defaults: jazz=0.28, blues=0.20, hip-hop=0.15, funk=0.12

---

## Layer 4: Exporters

### MIDI Exporter (midi_exporter.py)

Three export modes:
1. **`export(beat)`** — drum loop, Format 1, per-instrument tracks, channel 9
2. **`export_song(song_beat)`** — full percussion with section markers
3. **`export_full_arrangement(full)`** — multi-instrument:
   - Drums: channel 9 (GM standard), grouped by instrument type
   - Bass: channel 0, with program change
   - Harmony: channel 1, with program change
   - Section markers on tempo track

All modes have mido primary + pure-Python fallback.

### WAV Renderer (wav_renderer.py)

- FluidSynth (CLI or pyfluidsynth bindings)
- Graceful skip if unavailable

### JSON Exporter (json_exporter.py)

Four export modes:
1. **Beat JSON**: metadata + velocity grid + hit list
2. **Song Beat JSON**: sections + drum hits
3. **Full Arrangement JSON**: sections + chords + drums + bass + harmony
4. **Collection JSON**: multiple beats bundled

---

## Layer 5: CLI (generate.py)

```
Generation modes:
  --full-song          Full song percussion (3-5 min, sections + transitions)
  --full-production    Full multi-instrument (drums + bass + harmony)
  (default)            Beat loops (2-8 bars)

Analysis mode:
  --analyze MIDI_FILE  Print SongDNA (key, chords, structure, instruments)
  --analyze-save PATH  Save SongDNA to JSON

Generation options:
  --genre / -g         Genre (repeatable)
  --year / -y          Year
  --count / -n         Variations [4]
  --bars / -b          Bars per beat [4]
  --swing / -s         Swing override
  --bpm                BPM override
  --seed               Random seed
  --variation          Inter-beat variation 0-1 [0.15]

Export:
  --output / -o        Output directory [./output]
  --no-wav             Skip WAV rendering
  --no-json            Skip JSON export
  --multi-track        Format 1 MIDI (default: true)
```

---

## Data Flow: Full Production

```
User runs: python generate.py --genre house --year 2019 --full-production

1. CLI → framework.generate_full_production("house", 2019)

2. build_profile("house", 2019):
   → aggregator.get_songs() → parse MIDIs → extract drums → GenreProfile

3. arrangement_engine.get_template("house"):
   → intro(8) → verse(16) → breakdown(8) → drop(16) → verse(8) → breakdown(8) → drop(16) → outro(8)

4. multi_instrument_generator.generate():
   a. Generate default chord progression: C-G-Am-F (I-V-vi-IV)
   b. song_generator.generate_song(profile, arrangement) → SongBeat (drums)
   c. bass_generator.generate(chords, arrangement, "house") → BassLine
   d. harmony_generator.generate(chords, arrangement, "house") → HarmonyPart
   → FullArrangement with all parts

5. humanizer.humanize_song(drums, profile) → section-aware humanization

6. export_full_arrangement(full, "./output/house_2019"):
   a. midi_exporter.export_full_arrangement() → multi-track .mid
      - Tempo track with section markers
      - Drum tracks (kick, snare, hats, etc.) on ch9
      - Bass track on ch0 with program change (Synth Bass)
      - Harmony track on ch1 with program change (Pad)
   b. json_exporter.export_full_arrangement() → .json
   c. wav_renderer.render() → .wav (if FluidSynth available)
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
- `pyyaml` — Config file loading
