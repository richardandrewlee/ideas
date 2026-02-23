# TrackAll — UX & App Flow

## Overview

The app has four primary surfaces and one overlay. Navigation lives at the bottom.

```
┌─────────────────────────────────┐
│                                 │
│          [ screen ]             │
│                                 │
│                                 │
├─────────────────────────────────┤
│  [ Log ]  [ Capture ]  [ Day ]  │
└─────────────────────────────────┘
```

| Tab | Screen | Purpose |
|---|---|---|
| Log | Moment Feed | Scrollable list of all entries |
| Capture | Capture Screen | Quick-add a new moment |
| Day | Daily Summary | Rolled-up view of today (or any day) |

Tapping a moment in any list opens the **Moment Detail** overlay.

---

## Screen 1 — Capture

The primary action. Fast, low-friction. Opens by default when the app launches.

```
┌─────────────────────────────────┐
│                                 │
│   What's happening?             │
│  ┌───────────────────────────┐  │
│  │                           │  │
│  │                           │  │
│  │                           │  │
│  └───────────────────────────┘  │
│                                 │
│   Category                      │
│  ┌──────────┐                   │
│  │ general ▾│                   │
│  └──────────┘                   │
│                                 │
│  ┌───┐                          │
│  │ 🎙│  Hold to record          │
│  └───┘                          │
│                                 │
│  ┌─────────────────────────┐    │
│  │         Log it          │    │
│  └─────────────────────────┘    │
│                                 │
└─────────────────────────────────┘
```

### Behavior

- **Text field** — multiline, autofocused. Optional if audio is recorded.
- **Category picker** — dropdown seeded from previously used categories + "general". No limit on custom values.
- **Hold to record** — records audio while held, releases to stop. A waveform animation plays during recording. Transcription runs in the background after saving.
- **Log it** — posts to `POST /entries`. Button is active as soon as either text or audio exists.
- After logging, the field clears and a brief toast confirms: _"Logged."_

### API Call

```
POST /entries
Content-Type: multipart/form-data

text:     "Went for a run, legs felt heavy"
category: "fitness"
file:     <audio blob, if recorded>
```

---

## Screen 2 — Moment Feed (Log)

The running list of everything logged, newest first.

```
┌─────────────────────────────────┐
│  Log                     [🔍]   │
├─────────────────────────────────┤
│  Today                          │
│ ┌─────────────────────────────┐ │
│ │ 🏷 fitness          9:14 AM │ │
│ │ Went for a run, legs felt   │ │
│ │ heavy                       │ │
│ └─────────────────────────────┘ │
│ ┌─────────────────────────────┐ │
│ │ 🏷 reading          8:02 AM │ │
│ │ Finished chapter 3          │ │
│ └─────────────────────────────┘ │
│                                 │
│  Yesterday                      │
│ ┌─────────────────────────────┐ │
│ │ 🏷 food            11:45 PM │ │
│ │ 🎙 [transcript available]   │ │
│ └─────────────────────────────┘ │
│ ┌─────────────────────────────┐ │
│ │ 🏷 general          3:22 PM │ │
│ │ Called mom                  │ │
│ └─────────────────────────────┘ │
│                                 │
└─────────────────────────────────┘
```

### Behavior

- Entries grouped by calendar day, newest group on top.
- Each card shows: category tag, time, first ~2 lines of text (or transcript if no text).
- A 🎙 icon appears on cards that have an audio file.
- **Search** (🔍) filters by text across all entries client-side (no API call needed — all entries are already loaded).
- **Tap any card** → opens Moment Detail.
- **Swipe left on a card** → reveals a Delete action. Confirmation prompt before `DELETE /entries/{id}`.

### API Call

```
GET /entries
→ returns array, client groups by date
```

---

## Screen 3 — Moment Detail

Opens as a bottom sheet or full-screen push when a card is tapped.

```
┌─────────────────────────────────┐
│  ←  Moment          [Edit] [🗑] │
├─────────────────────────────────┤
│                                 │
│  Feb 23, 2026 · 9:14 AM        │
│  🏷 fitness                     │
│                                 │
│  Went for a run, legs felt      │
│  heavy today. Took the long     │
│  route through the park.        │
│                                 │
│  ─────────────────────────────  │
│  🎙 Audio                       │
│  ┌─────────────────────────┐    │
│  │  ▶  00:00 ─────── 1:24  │    │
│  └─────────────────────────┘    │
│                                 │
│  Transcript                     │
│  "Went for a run, legs felt     │
│  heavy today. Took the long     │
│  route through the park."       │
│                                 │
└─────────────────────────────────┘
```

### Behavior

- **Edit** — tapping puts text and category into edit mode inline. Save sends `PATCH /entries/{id}`. Cancel reverts.
- **Delete** (🗑) — confirmation dialog, then `DELETE /entries/{id}`, then navigate back to the Feed.
- **Audio player** — shown only if `audio_filename` is set. Streams the file directly from the server or from local storage.
- **Transcript** — shown only if `transcript` is set. If audio exists but no transcript yet (Whisper still running or not installed), show: _"Transcript not available."_
- If no audio at all, the audio section is hidden entirely.

### API Calls

```
GET  /entries/{id}         → load detail
PATCH /entries/{id}        → save edits
DELETE /entries/{id}       → delete
```

---

## Screen 4 — Daily Summary (Day)

A digest of one day's activity. Defaults to today. Swipe or tap arrows to navigate days.

```
┌─────────────────────────────────┐
│  ◀  Sunday, Feb 23  ▶           │
├─────────────────────────────────┤
│                                 │
│  4 moments logged               │
│                                 │
│  By category                    │
│  ████████████ fitness    2      │
│  ██████       reading    1      │
│  ████         food       1      │
│                                 │
│  ─────────────────────────────  │
│  Timeline                       │
│                                 │
│  9:14 AM  fitness                │
│           Went for a run...     │
│                                 │
│  8:02 AM  reading                │
│           Finished chapter 3    │
│                                 │
│  ─────────────────────────────  │
│  ✦ Daily note                   │
│  ┌───────────────────────────┐  │
│  │ Add a note about your day │  │
│  └───────────────────────────┘  │
│                                 │
└─────────────────────────────────┘
```

### Behavior

- **Day navigation** — `◀ ▶` arrows (or swipe) move one day. Defaults to today.
- **Count + category bars** — computed client-side from the entries already fetched. No extra API call.
- **Timeline** — same entries from the Feed, but filtered to the selected day and ordered chronologically (oldest first — you're reviewing the day in order).
- **Tapping a timeline row** → opens Moment Detail.
- **Daily note** — a free-text field that logs a single summary entry with `category: "daily-note"`. Sends `POST /entries`. If a `daily-note` entry already exists for that day, the field is pre-filled and saving sends `PATCH /entries/{id}`.

### API Calls

```
GET /entries                           → filter client-side by date
POST /entries  (category: daily-note)  → save daily note (new)
PATCH /entries/{id}                    → save daily note (edit)
```

---

## Navigation Flow

```
                    ┌──────────────┐
              ┌────▶│   Capture    │
              │     └──────────────┘
              │             │ "Log it"
              │             ▼
┌─────────────┴──┐   ┌──────────────┐
│  Daily Summary │   │ Moment Feed  │
│    (Day tab)   │   │  (Log tab)   │
└────────────────┘   └──────────────┘
         │                  │
         │   tap a moment   │
         └────────┬─────────┘
                  ▼
         ┌────────────────┐
         │ Moment Detail  │
         │  (overlay)     │
         └────────────────┘
                  │
            edit / delete
                  │
         returns to origin screen
```

---

## State Summary

| Data needed | Loaded from | When |
|---|---|---|
| All entries | `GET /entries` | App open / tab focus |
| Single entry | `GET /entries/{id}` | Tap to detail |
| New entry | `POST /entries` | Capture submit |
| Edit entry | `PATCH /entries/{id}` | Save in detail |
| Delete entry | `DELETE /entries/{id}` | Swipe or detail delete |

The Feed and Day views share the same `GET /entries` response — no duplicate fetching. Filter and grouping happen in the client.
