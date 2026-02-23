from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class EntryBase(BaseModel):
    text: Optional[str] = None
    category: str = "uncategorized"


class EntryCreate(EntryBase):
    pass


class EntryUpdate(BaseModel):
    text: Optional[str] = None
    category: Optional[str] = None


class EntryInDB(EntryBase):
    id: str
    timestamp: datetime


class Entry(EntryInDB):
    audio_filename: Optional[str] = None
    transcript: Optional[str] = None
