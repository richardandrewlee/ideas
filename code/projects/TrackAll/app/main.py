from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from . import audio, storage
from .models import Entry, EntryCreate, EntryUpdate

app = FastAPI(title="TrackAll", description="Log things you do.")


@app.get("/entries", response_model=List[Entry])
def list_entries():
    return storage.get_all()


@app.post("/entries", response_model=Entry, status_code=201)
async def create_entry(
    text: Optional[str] = Form(None),
    category: str = Form("uncategorized"),
    file: Optional[UploadFile] = File(None),
):
    entry_in = EntryCreate(text=text, category=category)
    audio_filename: Optional[str] = None

    if file and file.filename:
        suffix = "." + file.filename.rsplit(".", 1)[-1] if "." in file.filename else ".bin"
        data = await file.read()
        audio_filename = audio.save_audio(data, suffix)

    entry = storage.create(entry_in, audio_filename=audio_filename)

    if audio_filename:
        transcript = audio.transcribe(audio_filename)
        if transcript:
            entry = storage.update_transcript(entry.id, transcript) or entry

    return entry


@app.get("/entries/{entry_id}", response_model=Entry)
def get_entry(entry_id: str):
    entry = storage.get_by_id(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    return entry


@app.patch("/entries/{entry_id}", response_model=Entry)
def update_entry(entry_id: str, patch: EntryUpdate):
    entry = storage.update(entry_id, patch)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    return entry


@app.delete("/entries/{entry_id}", status_code=204)
def delete_entry(entry_id: str):
    if not storage.delete(entry_id):
        raise HTTPException(status_code=404, detail="Entry not found")
