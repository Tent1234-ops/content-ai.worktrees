import json
import threading
from typing import Dict, List
from pathlib import Path

LEXICON_PATH = Path(__file__).resolve().parents[1] / "data" / "lexicon.json"
_lock = threading.Lock()
_cache: Dict = {"brands": [], "models": []}


def load_lexicon() -> Dict:
    global _cache
    with _lock:
        if LEXICON_PATH.exists():
            try:
                with open(LEXICON_PATH, "r", encoding="utf8") as f:
                    _cache = json.load(f)
            except Exception:
                _cache = {"brands": [], "models": []}
        else:
            _cache = {"brands": [], "models": []}
    return _cache


def save_lexicon(payload: Dict) -> Dict:
    with _lock:
        data = {"brands": sorted(set(payload.get("brands", []))), "models": sorted(set(payload.get("models", [])))}
        with open(LEXICON_PATH, "w", encoding="utf8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        _cache.update(data)
    return _cache


def add_brand(brand: str) -> Dict:
    with _lock:
        load_lexicon()
        b = brand.strip().lower()
        if b and b not in _cache.get("brands", []):
            _cache["brands"].append(b)
            save_lexicon(_cache)
    return _cache


def remove_brand(brand: str) -> Dict:
    with _lock:
        load_lexicon()
        b = brand.strip().lower()
        _cache["brands"] = [x for x in _cache.get("brands", []) if x != b]
        save_lexicon(_cache)
    return _cache


def list_brands() -> List[str]:
    load_lexicon()
    return list(_cache.get("brands", []))
