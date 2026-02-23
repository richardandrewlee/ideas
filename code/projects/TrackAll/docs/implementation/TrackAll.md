# TrackAll — Implementation Guide

## What It Does

TrackAll is a minimal REST API for logging entries — things you did, thought, or recorded. Each entry can have:

- A **text** note
- A **category** label (e.g. `"workout"`, `"food"`, `"reading"`)
- An optional **audio file** upload
- An optional **transcript** (auto-generated via Whisper if installed)

Everything is stored in a single JSON file on disk. No database, no migrations, no setup beyond `pip install`.

---

## Project Layout

```
TrackAll/
├── requirements.txt        # Python dependencies
├── data/
│   ├── entries.json        # All entries (auto-created on first write)
│   └── audio/             # Uploaded audio files (auto-created)
└── app/
    ├── __init__.py
    ├── main.py             # FastAPI app + route handlers
    ├── models.py           # Pydantic data shapes
    ├── storage.py          # Read/write entries.json
    └── audio.py            # Save audio + optional Whisper transcription
```

---

## 1. Setup & Running

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) Install Whisper for audio transcription
pip install openai-whisper

# 4. Start the server from the TrackAll/ directory
uvicorn app.main:app --reload --port 8000
```

The `--reload` flag restarts the server automatically when you edit a file.
Visit **http://127.0.0.1:8000/docs** for the interactive Swagger UI.

---

## 2. How Each File Works

### `models.py` — Data Shapes

Pydantic models define what an entry looks like at each stage of its life.

```
EntryBase          (shared fields — text and category)
    │
    ├── EntryCreate    (what the client sends when creating)
    └── EntryInDB      (adds id + timestamp once stored)
            │
            └── Entry  (full representation — adds audio + transcript)
```

`EntryUpdate` is separate because every field is optional when patching — you
shouldn't have to send fields you're not changing.

---

### `storage.py` — JSON Persistence

The storage layer keeps entries as a plain JSON array in `data/entries.json`.
It exposes six functions:

| Function | What it does |
|---|---|
| `get_all()` | Load and return every entry |
| `get_by_id(id)` | Find one entry by UUID, or `None` |
| `create(entry_in, audio_filename)` | Append a new entry and save |
| `update(id, patch)` | Apply a partial update (text / category) |
| `update_transcript(id, transcript)` | Write the Whisper result back |
| `delete(id)` | Remove an entry, return `False` if not found |

The private helpers `_load()` and `_save()` handle the raw JSON read/write so
every public function works at the model level.

---

### `audio.py` — File Handling + Transcription

```
save_audio(data, suffix) → filename
```
Writes raw bytes to `data/audio/<uuid>.<ext>` and returns just the filename
(not the full path — the path is always reconstructed from the same constant).

```
transcribe(filename) → str | None
```
Tries to `import whisper`. If the package isn't installed it returns `None`
immediately — no error, the entry just won't have a transcript. If Whisper is
available it runs the `"base"` model and returns the text.

---

### `main.py` — API Routes

| Method | Path | Body / Form | Returns |
|---|---|---|---|
| `GET` | `/entries` | — | Array of all entries |
| `POST` | `/entries` | `text`, `category`, optional `file` | Created entry |
| `GET` | `/entries/{id}` | — | One entry |
| `PATCH` | `/entries/{id}` | JSON `{ text?, category? }` | Updated entry |
| `DELETE` | `/entries/{id}` | — | 204 No Content |

`POST /entries` uses `multipart/form-data` so text and a file can be sent
together in one request. All other write endpoints use JSON.

The `create_entry` handler flow:

```
1. Parse text + category from form fields
2. If a file was uploaded → save it to disk → get filename
3. Create the entry in storage (with or without audio_filename)
4. If audio was saved → attempt transcription → write transcript back
5. Return the final entry
```

---

## 3. Data Model — JSON Reference

Below is a fully annotated example of a single entry as it appears in
`data/entries.json`.

```jsonc
{
  // Unique identifier — UUID v4 generated on creation, never changes.
  "id": "a3f1c2d4-88b0-4e2a-91cc-000d3a7f1e09",

  // Free-form note. null if the entry was audio-only.
  "text": "30 min run, felt good",

  // User-defined label for filtering. Defaults to "uncategorized".
  "category": "workout",

  // UTC timestamp of when the entry was created (ISO 8601).
  // Set automatically by the server — clients never send this.
  "timestamp": "2026-02-23T09:14:05.123456+00:00",

  // Filename (not full path) of the uploaded audio file.
  // null if no audio was attached.
  "audio_filename": "7b2e1a00-fc3d-4d91-bf88-1234abcd5678.webm",

  // Text transcribed from the audio file by Whisper.
  // null if no audio was uploaded, or Whisper is not installed.
  "transcript": "Thirty minute run. Felt really good today."
}
```

The full file is an array of these objects:

```jsonc
[
  { /* entry 1 */ },
  { /* entry 2 */ },
  ...
]
```

### Field Rules

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `id` | `string` (UUID) | server-set | auto | Never sent by client |
| `text` | `string \| null` | no | `null` | At least one of `text` or audio is useful |
| `category` | `string` | no | `"uncategorized"` | Free-form label |
| `timestamp` | `string` (ISO 8601) | server-set | auto | UTC, set on creation |
| `audio_filename` | `string \| null` | no | `null` | Set if file was uploaded |
| `transcript` | `string \| null` | no | `null` | Set after Whisper runs |

---

## 4. Example Requests

### Create a text entry

```bash
curl -X POST http://localhost:8000/entries \
  -F "text=Finished chapter 3" \
  -F "category=reading"
```

### Create an audio entry

```bash
curl -X POST http://localhost:8000/entries \
  -F "category=voice" \
  -F "file=@recording.webm"
```

### Update an entry's category

```bash
curl -X PATCH http://localhost:8000/entries/<id> \
  -H "Content-Type: application/json" \
  -d '{"category": "fitness"}'
```

### Delete an entry

```bash
curl -X DELETE http://localhost:8000/entries/<id>
```

---

## 5. Extending the App

**Add a new field** — three places to touch:
1. `models.py` — add the field to `EntryBase` or `Entry`
2. `storage.py` — update `create()` and/or `update()` to handle it
3. `main.py` — expose it as a `Form()` parameter if clients need to set it

**Switch from JSON to a real database** — only `storage.py` changes. The
models and routes stay exactly the same because the rest of the app only
deals with `Entry` objects, not raw dicts.

**Use a different Whisper model** — change `"base"` in `audio.py:25` to
`"small"`, `"medium"`, or `"large"` for higher accuracy at the cost of speed.
