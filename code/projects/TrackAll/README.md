# TrackAll

Minimal TrackAll scaffold: a small FastAPI app to track things you do.

Quick start

1. Create a virtual env and install deps:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Run the server:

```bash
uvicorn app.main:app --reload --port 8000
```

3. Open the interactive docs: http://127.0.0.1:8000/docs

Files

- code/projects/TrackAll/app/main.py - API entrypoint
- code/projects/TrackAll/app/models.py - Pydantic models
- code/projects/TrackAll/app/storage.py - simple JSON storage
- code/projects/TrackAll/app/audio.py - audio helpers (save + optional transcription)

Notes

- This is intentionally minimal: JSON file persistence, no external DB yet.
- Audio transcription is optional and will attempt to use `whisper` if installed; otherwise the audio file is saved and can be transcribed later.
