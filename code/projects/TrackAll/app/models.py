from pydantic import BaseModel
from typing import Optional

class EntryBase(BaseModel):
    text: Optional[str] = None
    category: Optional[str] = "uncategorized"

class EntryCreate(EntryBase):
    pass

class Entry(EntryBase):
    id: str
    timestamp: str
    audio_filename: Optional[str] = None
    transcript: Optional[str] = None
