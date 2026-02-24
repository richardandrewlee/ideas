# Beat Framework — Status & Context

> **Purpose:** Read this first. Re-centers you (and Claude) in 60 seconds.
> **Last updated:** 2026-02-23

---

## What This Is

A Python framework that generates **full multi-instrument song productions** by analyzing
real music data (Spotify, Billboard, Last.fm, Lakh MIDI), understanding song DNA
(key, chords, structure, instruments, energy), and producing genre-authentic
MIDI/WAV/JSON output ready for a DAW.

**Three generation modes:**
1. **Beat loops** — 2-8 bar drum patterns (`--genre house --year 2019`)
2. **Full song percussion** — 3-5 min drum tracks with sections (`--full-song`)
3. **Full production** — drums + bass + harmony, multi-track (`--full-production`)

---

## Where Things Stand

### Phase 1: Song DNA Analysis — DONE

- [x] `SongDNA` data model — complete musical fingerprint (key, chords, structure, instruments, energy)
- [x] Extended MIDI parser — captures all events (key sig, time sig, program change, markers, tempo map, note durations)
- [x] Key detector — Krumhansl-Schmuckler algorithm, MIDI + Spotify fusion
- [x] Instrument identifier — classifies MIDI tracks by role (drums, bass, melody, chords)
- [x] Chord extractor — template matching across 13 chord types, all 12 roots
- [x] Structure detector — self-similarity matrix, section labeling, energy curves
- [x] Song analyzer — orchestrates all analysis modules
- [x] Spotify collector enriched — extracts all audio features (key, mode, valence, etc.)
- [x] Billboard static wired into aggregator
- [x] CLI `--analyze` flag to inspect any MIDI file's SongDNA

### Phase 2: Full Song Percussion — DONE

- [x] Humanizer fill bug fixed (`_apply_fill_logic` parameter + operator precedence)
- [x] Arrangement engine — 12 genre templates with section types, energy, density
- [x] Section-aware drum profiles — per-section density scaling
- [x] Full song generator — section-aware drums with fills, builds, transitions
- [x] Section-aware humanization — timing/velocity scales per section energy
- [x] MIDI export with section markers
- [x] JSON export with section data
- [x] CLI `--full-song` flag

### Phase 3: Multi-Instrument Production — DONE

- [x] Bass line generator — 11 genre rhythm templates, chord-following, walking bass, 808s
- [x] Harmony generator — 12 genre voicing styles (pad, stab, power chord, skank, extended, block)
- [x] Multi-instrument orchestrator — shared arrangement + chord progression
- [x] Multi-track MIDI export — drums ch9, bass ch0, harmony ch1, program changes
- [x] JSON export for full arrangements
- [x] CLI `--full-production` flag
- [x] Framework API: `generate_full_production()`, `export_full_arrangement()`

### Original System — Still Working

- [x] Full 5-layer pipeline: collectors → analysis → generators → exporters → CLI
- [x] 4 data collectors: Spotify, Last.fm, Billboard scraper, Lakh MIDI
- [x] Billboard Static collector: 304 all-time hits, genre-classified, ~110 with BPM
- [x] Statistical beat generator with probability grids
- [x] Humanizer: swing, micro-timing, velocity accenting
- [x] Optional Magenta DrumsRNN continuation + GrooVAE humanization
- [x] Export: MIDI (Format 1), WAV (FluidSynth), JSON
- [x] Offline mode works (Billboard static + built-in profiles, no API keys)
- [x] Profile caching to disk

### Remaining Gaps

- [ ] Magenta checkpoints need manual download — no setup script
- [ ] ~220/304 Billboard songs missing BPM — defaults to 120
- [ ] Only 6 genres have real built-in drum profiles — others fall back to generic
- [ ] Lakh MIDI dataset not tested yet (requires local download of 170k files)

---

## Quick Commands

```bash
# Generate drum loops (no API keys needed)
python generate.py --genre house --year 2019

# Full song percussion (3-5 min with sections)
python generate.py --genre house --year 2019 --full-song

# Full multi-instrument production (drums + bass + harmony)
python generate.py --genre house --year 2019 --full-production

# Analyze a MIDI file
python generate.py --genre house --year 2019 --analyze path/to/song.mid

# Save analysis
python generate.py --genre house --year 2019 --analyze song.mid --analyze-save dna.json

# Multiple genres
python generate.py --genre house --genre rock --genre hip-hop --year 2020

# All the knobs
python generate.py --genre jazz --year 2010 --count 8 --bars 8 --swing 0.25 --bpm 140 --seed 42
```

---

## Key Decisions Made

1. **Hybrid approach**: Statistical generation first, Magenta optional
2. **32-step grid**: 2 bars at 16th-note resolution (standard)
3. **Built-in fallback profiles**: Hardcoded patterns when MIDI data sparse
4. **Profile blending**: 80% real / 20% built-in when both available
5. **Offline-first**: Billboard static + built-in profiles = no internet needed
6. **Format 1 MIDI**: Separate tracks per instrument group
7. **Krumhansl-Schmuckler for key detection**: duration×velocity weighted, Spotify tiebreaker
8. **Self-similarity for structure**: 4/8-bar blocks, greedy clustering, energy labeling
9. **Chord-following bass**: root (75%), fifth (15%), octave (10%), walking bass for jazz
10. **GM standard**: channel 9 drums, program changes for bass/harmony instruments

---

## Supported Genres (15)

house, techno, reggae, rock, hip-hop, jazz, pop, metal, soul,
funk, blues, drum-and-bass, country, rnb, edm

All have arrangement templates. Bass + harmony templates cover 11-12 genres each
with sensible fallbacks for the rest.

---

## Session Notes

_Use this section for quick notes during a work session. Clear between sessions._

- All 3 phases complete as of 2026-02-23
- Next: test full pipeline end-to-end, expand genre profiles, pattern visualizer
