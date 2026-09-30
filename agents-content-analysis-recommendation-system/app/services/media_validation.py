from __future__ import annotations

import math
import subprocess
from pathlib import Path

from app.services.dataset_contract import USER_UPLOAD_MAX_DURATION_SECONDS


class MediaValidationError(ValueError):
    pass


def probe_media_duration_seconds(
    media_path: str | Path,
    *,
    timeout_seconds: float = 15.0,
) -> float:
    path = Path(media_path)
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise MediaValidationError(
            "ffprobe is required to verify the uploaded video duration"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaValidationError("Timed out while checking video duration") from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown ffprobe error").strip()
        raise MediaValidationError(f"Could not read video duration: {detail[:300]}")
    try:
        duration = float(result.stdout.strip())
    except (TypeError, ValueError) as exc:
        raise MediaValidationError("The uploaded file has no readable duration") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise MediaValidationError("The uploaded file has an invalid duration")
    return duration


def validate_user_upload_duration(
    media_path: str | Path,
    *,
    max_duration_seconds: int = USER_UPLOAD_MAX_DURATION_SECONDS,
) -> float:
    duration = probe_media_duration_seconds(media_path)
    if duration > max_duration_seconds + 0.05:
        raise MediaValidationError(
            "Video duration exceeds the maximum video duration "
            f"({duration:.1f}s > {max_duration_seconds}s)"
        )
    return duration
