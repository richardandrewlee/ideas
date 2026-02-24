# Beat Framework — Status & Context

> **Purpose:** Read this first. Re-centers you (and Claude) in 60 seconds.
> **Last updated:** 2026-02-23

---

## What This Is

A Python framework that generates genre-authentic drum beats by pulling data from
music sources (Spotify, Billboard, Last.fm, Lakh MIDI), analyzing real drum patterns
statistically, and outputting MIDI/WAV/JSON files ready for a DAW.

**The pipeline:** Collect songs → Extract drum patterns → Build genre profile → Generate beats → Export

---

## Where Things Stand

### Done & Working

- [x] Full 5-layer pipeline: collectors → analysis → generators → exporters → CLI
- [x] 4 data collectors: Spotify, Last.fm, Billboard scraper, Lakh MIDI
- [x] Billboard Static collector: 304 all-time hits, genre-classified, ~110 with BPM
- [x] Statistical beat generator with probability grids per instrument per step
- [x] Humanizer: swing, micro-timing, velocity accenting
- [x] Optional Magenta DrumsRNN continuation + GrooVAE humanization
- [x] Export: MIDI (Format 1, multi-track), WAV (FluidSynth), JSON (for web UIs)
- [x] CLI with all the knobs: `--genre`, `--year`, `--bpm`, `--swing`, `--bars`, etc.
- [x] Offline mode works (Billboard static + built-in profiles, no API keys)
- [x] 10 test outputs validated: house/techno/reggae/rock/hip-hop (2 each)
- [x] Profile caching to disk
- [x] 6 built-in genre profiles: house, techno, reggae, rock, hip-hop, jazz

### Known Bugs

- [ ] **Humanizer fill bug** — `_apply_fill_logic()` in `humanizer.py` references
      `self.steps_per_bar_ref` incorrectly. Drum fills may not apply right.

### Not Yet Wired Up

- [ ] Billboard Static collector exists but **not connected to the aggregator**
      (aggregator.py doesn't import or call it)
- [ ] Magenta checkpoints need manual download — no setup script or clear error msgs

### Data Gaps

- [ ] **~220/304 Billboard songs missing BPM** — defaults to 120 BPM (bad for genre accuracy)
- [ ] Only 6 genres have real built-in profiles — other 9 genres fall back to generic
- [ ] Lakh MIDI dataset not tested yet (requires local download of 170k files)

---

## Active Priorities

What to work on next, in order of impact:

| #  | Task | Effort | Impact | Status |
|----|------|--------|--------|--------|
| 1  | Wire Billboard static into aggregator | Small | High — unlocks offline data | Not started |
| 2  | Fix humanizer fill bug | Small | Medium — output quality | Not started |
| 3  | Add genre profiles: jazz, blues, metal, d&b, funk, soul | Medium | High — doubles genre coverage | Not started |
| 4  | Enrich missing BPMs (Spotify API or bulk lookup) | Medium | High — 220 songs stuck at 120 | Not started |
| 5  | Pattern visualizer (ASCII grid or terminal UI) | Medium | Medium — debugging + showcase | Not started |
| 6  | Test with Lakh MIDI dataset | Large | Very high — real drum data | Not started |

---

## Backlog (Future)

- Real-time MIDI playback in CLI
- Drum kit customization (808, acoustic, electronic kits)
- Pattern quality filtering for extracted MIDI data
- Batch genre generation from file list
- A/B comparison tool for profiles across years
- Progress bars during profile building
- Web UI for pattern editing (Tone.js + JSON export)
- Pre-computed genre profiles shipped with the framework

---

## Quick Commands

```bash
# Generate beats (no API keys)
python generate.py --genre house --year 2019

# Generate with more options
python generate.py --genre hip-hop --year 2020 --count 8 --bars 8 --swing 0.15

# Force a BPM
python generate.py --genre techno --year 2022 --bpm 138

# Rebuild profile from scratch
python generate.py --genre rock --year 2015 --rebuild-profile

# With full config (API keys, soundfont, etc.)
python generate.py --genre house --year 2019 --config config.yaml
```

---

## Key Decisions Made

1. **Hybrid approach**: Statistical generation first, Magenta optional — keeps it accessible
2. **32-step grid**: 2 bars at 16th-note resolution — standard for most genres
3. **Built-in fallback profiles**: Hardcoded patterns for when MIDI data is sparse (<5 patterns)
4. **Profile blending**: When real data exists, 80% real / 20% built-in template
5. **Offline-first**: Billboard static + built-in profiles = full generation without internet
6. **Format 1 MIDI**: Separate tracks per instrument group (kick, snare, hats, etc.)

---

## Session Notes

_Use this section for quick notes during a work session. Clear between sessions._

- (empty — add notes as you go)
