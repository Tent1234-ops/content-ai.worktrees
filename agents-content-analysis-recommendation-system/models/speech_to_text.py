import importlib
import os
from pathlib import Path
from threading import RLock
from typing import Dict

# Lazy model manager that loads WhisperModel per requested size

try:
    from faster_whisper import WhisperModel
except Exception:
    WhisperModel = None

# runtime config
from app.runtime import get as runtime_get

_MODEL_STORE: Dict[str, Dict] = {}
_MODEL_LOAD_LOCK = RLock()
_REQUIRED_MODEL_FILES = ("config.json", "model.bin", "tokenizer.json")


def _env_enabled(name: str, default: bool) -> bool:
    fallback = "1" if default else "0"
    return os.getenv(name, fallback).strip().lower() not in {"0", "false", "no", "off"}


def configured_model_size() -> str:
    return str(runtime_get("asr_model") or os.getenv("ASR_MODEL_SIZE") or "small").lower()


def configured_model_root() -> Path:
    configured = os.getenv("ASR_MODEL_DIR", "models_cache/faster_whisper")
    return Path(configured).expanduser().resolve()


def configured_model_path(size: str | None = None) -> Path:
    return configured_model_root() / (size or configured_model_size())


def check_model_readiness(size: str | None = None) -> Dict[str, object]:
    model_size = (size or configured_model_size()).lower()
    path = configured_model_path(model_size)
    missing_files = [name for name in _REQUIRED_MODEL_FILES if not (path / name).is_file()]
    return {
        "status": "ready" if WhisperModel is not None and not missing_files else "missing",
        "ready": WhisperModel is not None and not missing_files,
        "model_size": model_size,
        "model_path": str(path),
        "local_files_only": _env_enabled("ASR_LOCAL_FILES_ONLY", True),
        "package_installed": WhisperModel is not None,
        "missing_files": missing_files,
    }


def _detect_device_compute():
    device = "cpu"
    compute_type = "int8"
    if importlib.util.find_spec("torch"):
        try:
            import torch
            if torch.cuda.is_available():
                device = "cuda"
                compute_type = "float16"
        except Exception:
            pass
    return device, compute_type


class ModelManager:
    @staticmethod
    def get_model(size: str):
        """Return a WhisperModel instance for given size; load lazily and cache."""
        with _MODEL_LOAD_LOCK:
            return ModelManager._load_model(size)

    @staticmethod
    def _load_model(size: str):
        size = (size or configured_model_size()).lower()
        if size in _MODEL_STORE:
            return _MODEL_STORE[size]["model"]

        if WhisperModel is None:
            raise RuntimeError("faster_whisper not installed or failed to import")

        readiness = check_model_readiness(size)
        local_files_only = _env_enabled("ASR_LOCAL_FILES_ONLY", True)
        if local_files_only and not readiness["ready"]:
            raise RuntimeError(
                "Faster Whisper model is not ready at "
                f"{readiness['model_path']}. Run: python scripts/setup_faster_whisper.py --model {size}"
            )

        device, compute_type = _detect_device_compute()
        # smaller sizes can use smaller beam and int8 for CPU
        compute = compute_type
        model_kwargs = {
            "device": device,
            "compute_type": compute,
        }
        model_source = str(configured_model_path(size)) if readiness["ready"] else size
        if local_files_only:
            model_kwargs["local_files_only"] = True
        else:
            model_kwargs["download_root"] = str(configured_model_root())

        try:
            model = WhisperModel(model_source, **model_kwargs)
        except TypeError:
            model = WhisperModel(model_source, device=device, compute_type=compute)
        except Exception:
            # fallback to CPU int8
            device, compute = "cpu", "int8"
            fallback_kwargs = {"device": "cpu", "compute_type": "int8"}
            if "local_files_only" in model_kwargs:
                fallback_kwargs["local_files_only"] = True
            model = WhisperModel(model_source, **fallback_kwargs)

        _MODEL_STORE[size] = {
            "model": model,
            "device": device,
            "compute_type": compute,
        }
        return model


def transcribe_with_meta(audio_path, language=None, model_size: str = None):
    # Decide model size from runtime if not provided
    model_size = model_size or configured_model_size()
    model = ModelManager.get_model(model_size)

    transcribe_kwargs = {
        "beam_size": 5 if model_size in {"medium", "large"} else 1,
        "vad_filter": True,
        "temperature": 0.0,
        "condition_on_previous_text": False,
        "repetition_penalty": 1.05,
        "no_repeat_ngram_size": 3,
        "language_detection_segments": 3,
    }
    configured_language = str(os.getenv("ASR_LANGUAGE", "auto") or "auto").lower()
    selected_language = language or (None if configured_language == "auto" else configured_language)
    if selected_language:
        transcribe_kwargs["language"] = selected_language

    segments, info = model.transcribe(audio_path, **transcribe_kwargs)

    text_parts = []
    total_no_speech_prob = 0.0
    segment_count = 0
    segments_out = []

    for seg in segments:
        seg_text = (seg.text or "").strip()
        seg_no_sp = getattr(seg, "no_speech_prob", None)
        seg_start = getattr(seg, "start", None)
        seg_end = getattr(seg, "end", None)
        segments_out.append({
            "text": seg_text,
            "no_speech_prob": float(seg_no_sp) if seg_no_sp is not None else None,
            "start": float(seg_start) if seg_start is not None else None,
            "end": float(seg_end) if seg_end is not None else None,
        })
        if seg_text:
            text_parts.append(seg_text)
        if seg_no_sp is not None:
            total_no_speech_prob += float(seg_no_sp)
            segment_count += 1

    avg_no_speech_prob = (total_no_speech_prob / segment_count) if segment_count else None

    return {
        "text": " ".join(text_parts).strip(),
        "model_size": model_size,
        "device": _MODEL_STORE.get(model_size, {}).get("device"),
        "compute_type": _MODEL_STORE.get(model_size, {}).get("compute_type"),
        "language": getattr(info, "language", None),
        "language_probability": getattr(info, "language_probability", None),
        "segment_count": len(text_parts),
        "avg_no_speech_prob": avg_no_speech_prob,
        "segments": segments_out,
    }


def transcribe(audio_path, model_size: str = None):
    result = transcribe_with_meta(audio_path, language=None, model_size=model_size)
    return result["text"]
