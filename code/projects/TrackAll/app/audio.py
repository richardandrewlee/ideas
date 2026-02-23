import uuid
from pathlib import Path
from typing import Optional

AUDIO_DIR = Path(__file__).parent.parent / "data" / "audio"


def save_audio(data: bytes, suffix: str = ".webm") -> str:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4()}{suffix}"
    (AUDIO_DIR / filename).write_bytes(data)
    return filename


def transcribe(filename: str) -> Optional[str]:
    try:
        import whisper  # type: ignore
    except ImportError:
        return None

    audio_path = AUDIO_DIR / filename
    if not audio_path.exists():
        return None

    model = whisper.load_model("base")
    result = model.transcribe(str(audio_path))
    return result.get("text", "").strip() or None
