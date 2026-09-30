from __future__ import annotations

import hashlib
import html
import re


def normalize_training_transcript(value: str | None, *, minimum_length: int = 80) -> str:
    """Normalize reviewed transcript text before hashing or model training."""
    transcript = html.unescape(str(value or ""))
    transcript = re.sub(r"\s+", " ", transcript).strip()
    if len(transcript) < minimum_length:
        raise ValueError(
            f"Transcript is too short; at least {minimum_length} characters are required"
        )
    return transcript


def training_transcript_sha256(transcript: str) -> str:
    return hashlib.sha256(transcript.encode("utf-8")).hexdigest()
