"""Compare a new video's transcript with text centroids of KPI-labelled reference groups.

K-Means and its centroids remain in scaled log(Views, Likes) space.
The centroids defined here are a separate embedding space; they do NOT
predict future KPIs or assign the user video to a KPI cluster.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
METHOD = "sentence_embedding_text_centroid_cosine"
CHUNK_SIZE = 220
CHUNK_STRIDE = 190
MAX_CHUNKS = 12


@lru_cache(maxsize=1)
def _load_encoder():
    # Imported lazily so ordinary TF-IDF requests need neither model nor weights.
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME)


def _chunks(text: str) -> list[str]:
    """Sample short pieces across the whole transcript; avoid first-token-only truncation."""
    text = " ".join((text or "").split())
    if not text:
        return []
    chunks = [text[start:start + CHUNK_SIZE] for start in range(0, len(text), CHUNK_STRIDE)]
    if len(chunks) > MAX_CHUNKS:
        positions = np.linspace(0, len(chunks) - 1, MAX_CHUNKS).round().astype(int)
        chunks = [chunks[int(i)] for i in positions]
    return chunks


def _normalise(matrix):
    matrix = np.asarray(matrix, dtype=np.float64)
    if matrix.ndim != 2 or not np.isfinite(matrix).all():
        raise ValueError("Invalid embedding matrix")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if np.any(norms <= 1e-12):
        raise ValueError("Zero-length embedding")
    return matrix / norms


def _document_vectors(texts, encoder):
    """Mean-normalise chunk vectors, then normalise each document vector."""
    pieces, boundaries = [], []
    for text in texts:
        chunk_list = _chunks(text)
        if not chunk_list:
            raise ValueError("Empty transcript")
        start = len(pieces)
        pieces.extend(chunk_list)
        boundaries.append((start, len(pieces)))
    encoded = np.asarray(
        encoder.encode(pieces, batch_size=16, show_progress_bar=False,
                       normalize_embeddings=True),
        dtype=np.float64,
    )
    if encoded.shape[0] != len(pieces):
        raise ValueError("Unexpected number of embeddings")
    encoded = _normalise(encoded)
    docs = np.stack([encoded[start:end].mean(axis=0) for start, end in boundaries])
    return _normalise(docs)


def compare_text_centroids(records, levels, user_transcript, *, encoder=None):
    """Return text-space similarities and descriptive nearest group.

    The records must be the KPI-filtered, K-Means-labelled reference rows.
    Two groups are required; labels are supplied by the separate KPI clustering.
    An exact/nearly exact tie is inconclusive, not arbitrarily High or Low.
    """
    if (len(records) != len(levels) or not records or
            set(levels) != {"low", "high"}):
        raise ValueError("KPI-clustered low/high reference rows required")

    result = {
        "status": "insufficient_evidence", "reason": None,
        "low_score": None, "high_score": None, "closest_group": None,
        "k_used": 0, "method": METHOD, "supporting_dataset_ids": {
            level: [record["dataset_id"] for record, name in zip(records, levels)
                    if name == level] for level in ("low", "high")
        },
        "model_name": MODEL_NAME,
        "margin": None,
        "evidence_strength": "not_validated",
        "reference_scores": [],
    }
    if not _chunks(user_transcript):
        result["reason"] = "insufficient_user_transcript"
        return result
    try:
        model = encoder if encoder is not None else _load_encoder()
        vectors = _document_vectors([row["transcript"] for row in records] +
                                    [user_transcript], model)
        references, user = vectors[:-1], vectors[-1]
        centroids = {}
        for level in ("low", "high"):
            indices = [i for i, label in enumerate(levels) if label == level]
            centroid = references[indices].mean(axis=0)
            norm = np.linalg.norm(centroid)
            if norm <= 1e-12:
                raise ValueError("Degenerate text centroid")
            centroids[level] = centroid / norm

        # Cosine similarity = 1 - cosine distance for unit-length vectors.
        # Clip the displayed values to [0,1], without altering cluster geometry.
        low = float(np.clip(np.dot(user, centroids["low"]), 0, 1))
        high = float(np.clip(np.dot(user, centroids["high"]), 0, 1))
        margin = abs(high - low)
        result.update(
            low_score=low, high_score=high, margin=margin,
            feature_count=int(vectors.shape[1]),
            reference_scores=[float(np.clip(np.dot(user, ref), 0, 1))
                              for ref in references],
        )
        if max(low, high) <= 1e-12:
            result.update(status="inconclusive", reason="no_semantic_similarity")
        elif margin <= 1e-6:
            result.update(status="inconclusive", reason="text_centroid_tie")
        else:
            result.update(status="ready", reason=None,
                          closest_group="high" if high > low else "low")
        return result
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        # Keep KPI clustering visible even when embeddings are unavailable.
        result["reason"] = "embedding_unavailable"
        result["detail"] = type(exc).__name__
        return result
