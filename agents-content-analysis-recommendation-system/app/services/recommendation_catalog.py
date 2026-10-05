"""Shared, versioned vocabulary and templates for evidence-backed advice."""
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def template_catalog() -> dict:
    return json.loads(Path(__file__).with_name("recommendation_templates.json").read_text(encoding="utf-8"))
