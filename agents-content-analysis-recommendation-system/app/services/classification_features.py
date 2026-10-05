"""Versioned transcript-only features; no category keywords or title overrides."""
from __future__ import annotations

import re
import unicodedata

import numpy as np
from pythainlp.tokenize import word_tokenize
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import FeatureUnion


FEATURE_VERSION = "thai-transcript-v1"


def normalize_classification_text(text: str) -> str:
    value = unicodedata.normalize("NFKC", str(text or "")).casefold()
    # Imports and ASR disagree about spaces inside Thai phrases. Preserve Latin
    # word boundaries and Thai tone marks, then tokenize both sources identically.
    value = re.sub(r"(?<=[\u0e00-\u0e7f])\s+(?=[\u0e00-\u0e7f])", "", value)
    return " ".join(value.split())


def classification_tokens(text: str) -> list[str]:
    return [token for token in word_tokenize(
        normalize_classification_text(text), engine="newmm", keep_whitespace=False
    ) if re.search(r"[\w]", token)]


def thai_transcript_features(*, words: bool = True) -> FeatureUnion:
    features = [("char", TfidfVectorizer(
        preprocessor=normalize_classification_text, analyzer="char",
        ngram_range=(3, 5), sublinear_tf=True, max_features=40_000,
        dtype=np.float32,
    ))]
    if words:
        features.insert(0, ("word", TfidfVectorizer(
            tokenizer=classification_tokens, token_pattern=None, lowercase=False,
            ngram_range=(1, 2), sublinear_tf=True, max_features=40_000,
            dtype=np.float32,
        )))
    return FeatureUnion(features)
