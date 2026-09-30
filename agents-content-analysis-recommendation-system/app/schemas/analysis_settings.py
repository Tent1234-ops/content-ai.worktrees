from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


WhisperSize = Literal["tiny", "base", "small", "medium", "large-v2", "large-v3", "turbo"]
WHISPER_SIZES = ("tiny", "base", "small", "medium", "large-v2", "large-v3", "turbo")


class AnalysisParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upload_max_duration_seconds: int = Field(default=300, ge=30, le=1800, strict=True)
    asr_model: WhisperSize = "small"
    hook_duration_seconds: int = Field(default=60, ge=5, le=300, strict=True)

    @model_validator(mode="after")
    def hook_within_upload_limit(self):
        if self.hook_duration_seconds > self.upload_max_duration_seconds:
            raise ValueError("Hook duration cannot exceed the maximum upload duration")
        return self
