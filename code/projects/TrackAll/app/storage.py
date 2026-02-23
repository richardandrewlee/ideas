import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .models import Entry, EntryCreate, EntryUpdate

DATA_FILE = Path(__file__).parent.parent / "data" / "entries.json"


def _load() -> List[dict]:
    if not DATA_FILE.exists():
        return []
    return json.loads(DATA_FILE.read_text())


def _save(entries: List[dict]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(entries, indent=2, default=str))


def get_all() -> List[Entry]:
    return [Entry(**e) for e in _load()]


def get_by_id(entry_id: str) -> Optional[Entry]:
    for e in _load():
        if e["id"] == entry_id:
            return Entry(**e)
    return None


def create(entry_in: EntryCreate, audio_filename: Optional[str] = None) -> Entry:
    entries = _load()
    entry = Entry(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        text=entry_in.text,
        category=entry_in.category,
        audio_filename=audio_filename,
    )
    entries.append(entry.model_dump())
    _save(entries)
    return entry


def update(entry_id: str, patch: EntryUpdate) -> Optional[Entry]:
    entries = _load()
    for i, e in enumerate(entries):
        if e["id"] == entry_id:
            if patch.text is not None:
                e["text"] = patch.text
            if patch.category is not None:
                e["category"] = patch.category
            entries[i] = e
            _save(entries)
            return Entry(**e)
    return None


def update_transcript(entry_id: str, transcript: str) -> Optional[Entry]:
    entries = _load()
    for i, e in enumerate(entries):
        if e["id"] == entry_id:
            e["transcript"] = transcript
            entries[i] = e
            _save(entries)
            return Entry(**e)
    return None


def delete(entry_id: str) -> bool:
    entries = _load()
    filtered = [e for e in entries if e["id"] != entry_id]
    if len(filtered) == len(entries):
        return False
    _save(filtered)
    return True
