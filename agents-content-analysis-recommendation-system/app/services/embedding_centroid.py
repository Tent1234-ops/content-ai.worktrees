"""Compare a new video's transcript with text centroids of KPI-labelled reference groups.

K-Means and its centroids remain in scaled log(Views, Likes) space.
The centroids defined here are a separate embedding space; they do NOT
predict future KPIs or assign the user video to a KPI cluster.
"""
from __future__ import annotations

from functools import lru_cache
from contextlib import nullcontext
from hashlib import sha256
import json
from pathlib import Path
from threading import RLock
from uuid import uuid4

import numpy as np

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MODEL_REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
METHOD = "sentence_embedding_text_centroid_cosine"
POLICY = {
    "version": "text-centroid-v2",
    "model_name": MODEL_NAME, "model_revision": MODEL_REVISION,
    "chunking": "token_budget_contiguous_full_text",
    "document_pooling": "token_weighted_mean_then_l2",
    "centroid_pooling": "equal_clip_mean_then_l2",
    "distance": "1_minus_signed_cosine",
    "minimum_distance_margin": 0.01,
    "minimum_centroid_distance": 0.001,
    "threshold_basis": "descriptive_heuristics_not_validated_prediction",
}
ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "runtime_artifacts" / "text-centroids"
_ENCODER_LOCK = RLock()


@lru_cache(maxsize=1)
def _load_encoder():
    # Resolve the pinned, already-installed snapshot; never download in an API request.
    from huggingface_hub import snapshot_download
    from sentence_transformers import SentenceTransformer
    snapshot = snapshot_download(
        MODEL_NAME, revision=MODEL_REVISION,
        cache_dir=str(ROOT / "models_cache" / "sentence_transformers"),
        local_files_only=True,
    )
    return SentenceTransformer(snapshot, device="cpu", local_files_only=True)


def _chunks(text: str, encoder) -> tuple[list[str], list[int]]:
    """Partition all text using the encoder's actual token budget, without sampling."""
    text = " ".join((text or "").split())
    if not text:
        return [], []
    tokenizer = encoder.tokenizer
    budget = encoder.max_seq_length - tokenizer.num_special_tokens_to_add(pair=False)
    if budget < 1 or not tokenizer.is_fast:
        raise ValueError("An offset-capable tokenizer and positive token budget are required")
    encoded = tokenizer(text, add_special_tokens=False, truncation=False,
                        return_offsets_mapping=True, verbose=False)
    offsets = encoded["offset_mapping"]
    if not offsets or len(offsets) > 100_000:
        raise ValueError("Transcript outside supported token budget")
    chunks, weights = [], []
    start, token_start = 0, 0
    while start < len(text):
        token_end = min(token_start + budget, len(offsets))
        end = len(text) if token_end == len(offsets) else offsets[token_end][0]
        # Re-tokenising a new boundary can change token count. Verify before encode.
        while True:
            piece = text[start:end]
            size = len(tokenizer(piece, add_special_tokens=False,
                                 truncation=False, verbose=False)["input_ids"])
            if 0 < size <= budget:
                break
            token_end -= 1
            if token_end <= token_start:
                raise ValueError("Cannot create a complete non-truncated text chunk")
            end = offsets[token_end][0]
        chunks.append(piece)
        weights.append(size)
        start, token_start = end, token_end
    return chunks, weights


def _normalise(matrix):
    matrix = np.asarray(matrix, dtype=np.float64)
    if matrix.ndim != 2 or not np.isfinite(matrix).all():
        raise ValueError("Invalid embedding matrix")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if np.any(norms <= 1e-12):
        raise ValueError("Zero-length embedding")
    return matrix / norms


def _cache_path(text):
    key = sha256((json.dumps(POLICY, sort_keys=True) + "\0" + text).encode()).hexdigest()
    return CACHE / f"{key}.json"


def _document_vectors(texts, encoder, *, cache_references=False):
    """All chunks contribute to each clip; long clips do not outweigh short clips."""
    pieces, weights, pending, vectors, coverage = [], [], [], [], []
    for text in texts:
        vectors.append(None)
        coverage.append(None)
        index = len(vectors) - 1
        path = _cache_path(text) if cache_references and index < len(texts) - 1 else None
        if path is not None:
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
                vector = np.asarray(cached["vector"], dtype=float)
                if (cached["policy"] == POLICY and vector.shape == (384,)
                        and cached["chunk_count"] > 0 and cached["token_count"] > 0
                        and np.isfinite(vector).all()
                        and abs(np.linalg.norm(vector) - 1) < 1e-6):
                    vectors[index] = vector
                    coverage[index] = {key: cached[key] for key in ("chunk_count", "token_count")}
                    continue
            except (OSError, ValueError, KeyError, TypeError):
                pass
        chunk_list, sizes = _chunks(text, encoder)
        if not chunk_list:
            raise ValueError("Empty transcript")
        start = len(pieces)
        pieces.extend(chunk_list)
        weights.extend(sizes)
        coverage[index] = {"chunk_count": len(sizes), "token_count": sum(sizes)}
        pending.append((index, start, len(pieces), path))
    if pieces:
        encoded = _normalise(encoder.encode(
            pieces, batch_size=32, show_progress_bar=False,
            convert_to_numpy=True, normalize_embeddings=True))
        if encoded.shape[0] != len(pieces):
            raise ValueError("Unexpected number of embeddings")
        for index, start, end, path in pending:
            vector = _normalise([np.average(encoded[start:end], axis=0,
                                            weights=weights[start:end])])[0]
            vectors[index] = vector
            if path is not None:
                try:
                    CACHE.mkdir(parents=True, exist_ok=True)
                    temporary = path.with_suffix(f".{uuid4().hex}.tmp")
                    temporary.write_text(json.dumps({
                        "policy": POLICY, "vector": vector.tolist(), **coverage[index]
                    }), encoding="utf-8")
                    temporary.replace(path)
                except OSError:
                    pass  # A read-only cache must not prevent comparison.
    return _normalise(np.stack(vectors)), coverage


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
        "model_revision": MODEL_REVISION,
        "embedding_policy": dict(POLICY),
        "margin": None,
        "low_distance": None, "high_distance": None, "centroid_distance": None,
        "evidence_strength": "descriptive_not_prediction",
        "reference_scores": [],
    }
    if not (user_transcript or "").strip():
        result["reason"] = "insufficient_user_transcript"
        return result
    try:
        with _ENCODER_LOCK if encoder is None else nullcontext():
            model = encoder if encoder is not None else _load_encoder()
            vectors, coverage = _document_vectors(
                [row["transcript"] for row in records] + [user_transcript], model,
                cache_references=encoder is None and
                getattr(model, "get_sentence_embedding_dimension", lambda: None)() == 384)
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
        # Preserve negative cosine values; distance ranges from 0 to 2, not 0 to 1.
        low = float(np.clip(np.dot(user, centroids["low"]), -1, 1))
        high = float(np.clip(np.dot(user, centroids["high"]), -1, 1))
        separation = 1 - float(np.clip(np.dot(centroids["low"], centroids["high"]), -1, 1))
        margin = abs(high - low)
        result.update(
            low_score=low, high_score=high, margin=margin,
            low_distance=1-low, high_distance=1-high, centroid_distance=separation,
            coverage={"reference_chunks": sum(c["chunk_count"] for c in coverage[:-1]),
                      "user_chunks": coverage[-1]["chunk_count"],
                      "user_tokens": coverage[-1]["token_count"],
                      "all_text_processed": True},
            feature_count=int(vectors.shape[1]),
            reference_scores=[float(np.clip(np.dot(user, ref), -1, 1))
                              for ref in references],
        )
        if max(low, high) <= 1e-12:
            result.update(status="inconclusive", reason="no_semantic_similarity")
        elif margin <= 1e-6:
            result.update(status="inconclusive", reason="text_centroid_tie")
        elif separation < POLICY["minimum_centroid_distance"]:
            result.update(status="inconclusive", reason="overlapping_text_centroids")
        elif margin < POLICY["minimum_distance_margin"]:
            result.update(status="inconclusive", reason="similar_text_distances")
        else:
            result.update(status="ready", reason=None,
                          closest_group="high" if high > low else "low")
        return result
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        # Keep KPI clustering visible even when embeddings are unavailable.
        result["reason"] = "embedding_unavailable"
        result["detail"] = type(exc).__name__
        return result
