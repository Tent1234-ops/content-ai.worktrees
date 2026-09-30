from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Dict, List

from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.models import ClassificationModel, DatasetContent
from app.services.classification_training import (
    ClassificationTrainingError,
    classify_with_artifact,
    classification_artifact_sha256,
)
from app.services.dataset_eligibility import production_transcript_query
from app.services.nlp import filter_tokens
from app.services.pipeline.core import normalize_space
from app.services.pipeline.domain_rules import (
    DOMAIN_BASE,
    detect_domain,
)
from app.services.taxonomy import (
    ACTIVE_LEAF_KEYS,
    MIN_VERIFIED_SAMPLES,
    UNKNOWN_LEAF_KEY,
    normalize_taxonomy_leaf,
    ready_leaf_keys,
    taxonomy_coverage,
    taxonomy_path,
    taxonomy_profile_terms,
)


MIN_TAXONOMY_CONFIDENCE = 0.35
MIN_TAXONOMY_SIMILARITY = 0.05


RULE_DOMAIN_LEAVES = {
    "smartphone": {"phone"},
    "food_drink": {"general_food", "drink"},
    "audio": {"audio", "headphone"},
    "fashion": {"shirt", "shoes"},
    "skincare": {"makeup", "grooming"},
}


def _weighted_dataset_rows(db: Session, source_prefix: str, limit: int) -> List[DatasetContent]:
    leaves = sorted(ready_leaf_keys(db))
    if not leaves:
        return []
    per_leaf_limit = max(MIN_VERIFIED_SAMPLES, math.ceil(limit / len(leaves)))
    rows: List[DatasetContent] = []
    seen_ids: set[int] = set()
    for leaf_key in leaves:
        leaf_rows = (
            production_transcript_query(db, train_only=True)
            .filter(DatasetContent.source_platform.like(f"{source_prefix}%"))
            .filter(DatasetContent.taxonomy_leaf_key == leaf_key)
            .order_by(DatasetContent.dataset_id.asc())
            .limit(per_leaf_limit)
            .all()
        )
        for row in leaf_rows:
            if row.dataset_id in seen_ids:
                continue
            seen_ids.add(row.dataset_id)
            rows.append(row)
    return rows


def _token_counter(text: str) -> Counter[str]:
    normalized = normalize_space(text or "").lower()
    tokens = re.findall(r"[\u0E00-\u0E7Fa-z0-9][\u0E00-\u0E7Fa-z0-9\-]*", normalized)
    return Counter(filter_tokens(tokens))


def _cosine(left: Counter[str] | Dict[str, float], right: Counter[str] | Dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    shared = set(left) & set(right)
    numerator = sum(float(left[key]) * float(right[key]) for key in shared)
    left_norm = math.sqrt(sum(float(value) ** 2 for value in left.values()))
    right_norm = math.sqrt(sum(float(value) ** 2 for value in right.values()))
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def build_domain_classifier_profiles(
    db: Session,
    *,
    source_prefix: str = "youtube",
    limit: int = 200,
) -> List[Dict[str, object]]:
    rows = _weighted_dataset_rows(db, source_prefix, limit)
    term_profiles: Dict[str, Counter[str]] = defaultdict(Counter)
    sample_counts: Counter[str] = Counter()

    for row in rows:
        text = " ".join(part for part in [row.title or "", row.transcript or "", row.category or ""] if part).strip()
        if not text:
            continue
        domain = normalize_taxonomy_leaf(row.taxonomy_leaf_key)
        if domain == UNKNOWN_LEAF_KEY:
            continue
        # Popularity must not make one creator define the category centroid.
        # Every human-reviewed training transcript contributes equally.
        weight = 1.0
        for term, count in _token_counter(text).items():
            term_profiles[domain][term] += count * weight
        sample_counts[domain] += 1

    for domain in ready_leaf_keys(db):
        term_profiles.setdefault(domain, Counter())

    profiles: List[Dict[str, object]] = []
    for domain, terms in term_profiles.items():
        seed_terms = taxonomy_profile_terms(domain)
        for seed in seed_terms:
            terms[seed] += 0.15
            for token in _token_counter(seed):
                terms[token] += 0.75
        profiles.append(
            {
                "domain": domain,
                "sample_size": int(sample_counts[domain]),
                "top_terms": [
                    {"term": term, "weight": round(float(weight), 3)}
                    for term, weight in terms.most_common(12)
                ],
                "term_weights": dict(terms),
            }
        )

    profiles.sort(key=lambda item: (-int(item["sample_size"]), str(item["domain"])))
    return profiles


def _apply_taxonomy_contract(db: Session, result: Dict[str, object]) -> Dict[str, object]:
    coverage = taxonomy_coverage(db)
    coverage_by_leaf = {
        str(item["leaf_key"]): item for item in coverage["leaves"]
    }
    ready_leaves = {
        leaf_key for leaf_key, item in coverage_by_leaf.items() if item["ready"]
    }

    legacy_domain = str(result.get("domain") or "general")
    leaf_key = normalize_taxonomy_leaf(legacy_domain)
    raw_candidates = list(result.get("candidates") or [])
    top_similarity = (
        float(raw_candidates[0].get("similarity", 0.0)) if raw_candidates else 0.0
    )
    candidates = []
    for raw_candidate in raw_candidates:
        candidate_leaf = normalize_taxonomy_leaf(raw_candidate.get("domain"))
        if candidate_leaf == UNKNOWN_LEAF_KEY:
            continue
        candidate = dict(raw_candidate)
        candidate["domain"] = candidate_leaf
        candidate["taxonomy_leaf_key"] = candidate_leaf
        candidates.append(candidate)
    confidence = float(result.get("confidence", 0.0))
    warning: str | None = None

    if leaf_key == UNKNOWN_LEAF_KEY or leaf_key not in ACTIVE_LEAF_KEYS:
        warning = (
            f"'{legacy_domain}' is outside the active taxonomy; returning Unknown/Other."
        )
    elif leaf_key not in ready_leaves:
        sample_count = int(
            coverage_by_leaf.get(leaf_key, {}).get("verified_sample_count", 0)
        )
        warning = (
            f"Category '{leaf_key}' has {sample_count}/{MIN_VERIFIED_SAMPLES} human-reviewed "
            "human-reviewed public YouTube samples; returning Unknown/Other until the coverage gate passes."
        )
    elif confidence < MIN_TAXONOMY_CONFIDENCE or top_similarity < MIN_TAXONOMY_SIMILARITY:
        warning = (
            "The transcript does not match an active category strongly enough; "
            "returning Unknown/Other."
        )

    if warning:
        path = taxonomy_path(UNKNOWN_LEAF_KEY)
        result["domain"] = UNKNOWN_LEAF_KEY
        result["confidence"] = 0.0
        result["method"] = f"{result.get('method', 'unknown')}+taxonomy_gate"
        result["warning"] = warning
    else:
        path = taxonomy_path(leaf_key)
        result["domain"] = leaf_key
        result["warning"] = None

    result["legacy_domain"] = legacy_domain
    result["candidates"] = candidates
    result.update(path)
    result["taxonomy_ready"] = bool(coverage["ready"])
    return result


def get_active_classification_model(db: Session) -> ClassificationModel | None:
    return (
        db.query(ClassificationModel)
        .filter(
            ClassificationModel.is_active.is_(True),
            ClassificationModel.status == "qualified",
        )
        .order_by(
            ClassificationModel.trained_at.desc(),
            ClassificationModel.model_id.desc(),
        )
        .first()
    )


def _classify_with_active_model(
    db: Session,
    *,
    text: str,
    title: str | None,
    model_snapshot: dict | None = None,
) -> Dict[str, object] | None:
    if model_snapshot is None:
        model = get_active_classification_model(db)
    else:
        model_id = model_snapshot.get("model_id")
        if model_id is None:
            return None
        model = db.get(ClassificationModel, model_id)
        if model is None or model.status != "qualified":
            raise ClassificationTrainingError("The queued classification model is no longer available")
        if classification_artifact_sha256(model.artifact_path) != model_snapshot["artifact_sha256"]:
            raise ClassificationTrainingError("The classification artifact changed after this job was queued")
    if model is None or not str(model.artifact_path or "").strip():
        return None

    try:
        prediction = classify_with_artifact(
            str(model.artifact_path),
            title=title,
            text=text,
            require_scope_validation=(
                model_snapshot.get("scope_validation_required", settings.classification_require_scope_validation)
                if model_snapshot else settings.classification_require_scope_validation
            ),
        )
    except (ClassificationTrainingError, OSError, ValueError):
        if model_snapshot is not None:
            raise
        return None

    raw_leaf_key = normalize_taxonomy_leaf(
        str(prediction.get("raw_taxonomy_leaf_key") or "")
    )
    predicted_leaf_key = normalize_taxonomy_leaf(
        str(prediction.get("taxonomy_leaf_key") or "")
    )
    ready_leaves = ready_leaf_keys(db)
    warning: str | None = None
    acceptance = prediction.get("acceptance") or {}
    if predicted_leaf_key == UNKNOWN_LEAF_KEY:
        warning = {
            "scope_validation_unavailable": "โมเดลยังไม่มีเกณฑ์ปฏิเสธคลิปนอกขอบเขตที่ผ่าน Validation จึงงดคำแนะนำเฉพาะหมวดชั่วคราว",
            "outside_training_support": "ข้อความยังไม่สอดคล้องกับข้อมูลฝึกของหมวดที่โมเดลทายเพียงพอ จึงงดคำแนะนำเฉพาะหมวด",
            "scope_policy_invalid": "ไม่สามารถตรวจรับผลจำแนกหมวดได้ จึงงดคำแนะนำเฉพาะหมวด",
        }.get(acceptance.get("reason"), "โมเดลยังไม่ผ่านเกณฑ์ยืนยันหมวดหมู่ จึงงดคำแนะนำเฉพาะหมวด")
    elif predicted_leaf_key not in ready_leaves:
        predicted_leaf_key = UNKNOWN_LEAF_KEY
        warning = "The predicted category no longer meets the dataset coverage gate."
    elif acceptance.get("accepted") is False:
        warning = "คำเตือน: ยังไม่ได้ยืนยันความสามารถในการปฏิเสธคลิปนอกขอบเขต ผลหมวดและคำแนะนำนี้อาจผิดหมวด"

    path = taxonomy_path(predicted_leaf_key)
    probabilities = dict(prediction.get("probabilities") or {})
    candidates = []
    for leaf_key, probability in sorted(
        probabilities.items(),
        key=lambda item: (-float(item[1]), str(item[0])),
    ):
        normalized_leaf = normalize_taxonomy_leaf(leaf_key)
        if normalized_leaf == UNKNOWN_LEAF_KEY:
            continue
        candidates.append(
            {
                "domain": normalized_leaf,
                "taxonomy_leaf_key": normalized_leaf,
                "score": float(probability),
                "similarity": float(probability),
                "sample_size": int(model.training_sample_count or 0),
                "matched_terms": [],
            }
        )

    model_type = str(prediction.get("model_type") or model.model_type or "")
    return {
        "domain": predicted_leaf_key,
        "legacy_domain": raw_leaf_key,
        "confidence": float(prediction["confidence"]),
        "method": (
            "trained_sentence_embedding_classifier"
            if model_type.startswith("multilingual_sentence_embeddings")
            else "trained_tfidf_classifier"
        ),
        "rule_domain": detect_domain(str(text or "").strip()),
        "source": str(model.training_dataset_source or "reviewed_dataset"),
        "profile_limit": int(model.training_sample_count or 0),
        "candidates": candidates,
        **path,
        "taxonomy_ready": bool(taxonomy_coverage(db)["ready"]),
        "warning": warning,
        "model_id": int(model.model_id),
        "model_key": str(model.model_key),
        "model_version": str(model.model_version),
        "unknown_threshold": prediction.get("unknown_threshold"),
        "raw_taxonomy_leaf_key": raw_leaf_key,
        "acceptance": acceptance,
    }


def classify_text_domain(
    db: Session,
    *,
    text: str,
    title: str | None = None,
    source_prefix: str = "youtube",
    profile_limit: int = 200,
    top_k: int = 5,
    require_active_model: bool = False,
    model_snapshot: dict | None = None,
) -> Dict[str, object]:
    transcript_text = str(text or "").strip()
    if not transcript_text:
        return {
            "domain": UNKNOWN_LEAF_KEY,
            "legacy_domain": UNKNOWN_LEAF_KEY,
            "confidence": 0.0,
            "method": "no_transcript",
            "rule_domain": "general",
            "source": source_prefix,
            "profile_limit": profile_limit,
            "candidates": [],
            **taxonomy_path(UNKNOWN_LEAF_KEY),
            "taxonomy_ready": bool(taxonomy_coverage(db)["ready"]),
            "warning": "No speech transcript is available for classification.",
        }

    trained_result = _classify_with_active_model(
        db,
        title=None,
        text=transcript_text,
        model_snapshot=model_snapshot,
    )
    if trained_result is not None:
        return trained_result

    if require_active_model:
        return {
            "domain": UNKNOWN_LEAF_KEY,
            "legacy_domain": UNKNOWN_LEAF_KEY,
            "confidence": 0.0,
            "method": "active_model_unavailable",
            "rule_domain": "general",
            "source": source_prefix,
            "profile_limit": profile_limit,
            "candidates": [],
            **taxonomy_path(UNKNOWN_LEAF_KEY),
            "taxonomy_ready": bool(taxonomy_coverage(db)["ready"]),
            "warning": (
                "No qualified Active Model is available; returning "
                "Unknown/Other instead of using a legacy classifier."
            ),
        }

    merged_text = transcript_text
    rule_domain = detect_domain(merged_text)
    input_terms = _token_counter(merged_text)
    profiles = build_domain_classifier_profiles(db, source_prefix=source_prefix, limit=profile_limit)

    candidates: List[Dict[str, object]] = []
    for profile in profiles:
        domain = str(profile["domain"])
        term_weights = profile["term_weights"]
        similarity = _cosine(input_terms, term_weights)
        rule_bonus = (
            0.08
            if domain in RULE_DOMAIN_LEAVES.get(rule_domain, set())
            else 0.0
        )
        score = similarity + rule_bonus
        matched_terms = [
            term
            for term, _weight in Counter(term_weights).most_common(20)
            if term in input_terms
        ][:8]
        candidates.append(
            {
                "domain": domain,
                "score": round(score, 4),
                "similarity": round(similarity, 4),
                "sample_size": int(profile["sample_size"]),
                "matched_terms": matched_terms,
            }
        )

    if not candidates:
        fallback_terms = DOMAIN_BASE.get(rule_domain, [])[:8]
        return _apply_taxonomy_contract(db, {
            "domain": rule_domain,
            "confidence": 0.55 if rule_domain != "general" else 0.25,
            "method": "rule_fallback",
            "rule_domain": rule_domain,
            "source": source_prefix,
            "profile_limit": profile_limit,
            "candidates": [
                {
                    "domain": rule_domain,
                    "score": 0.0,
                    "similarity": 0.0,
                    "sample_size": 0,
                    "matched_terms": fallback_terms,
                }
            ],
        })

    candidates.sort(key=lambda item: (-float(item["score"]), -int(item["sample_size"]), str(item["domain"])))
    top_score = float(candidates[0]["score"])
    score_total = sum(max(float(item["score"]), 0.0) for item in candidates[:top_k])
    confidence = top_score / score_total if score_total > 0 else 0.0
    if candidates[0]["domain"] in RULE_DOMAIN_LEAVES.get(rule_domain, set()):
        confidence = min(1.0, confidence + 0.08)

    return _apply_taxonomy_contract(db, {
        "domain": candidates[0]["domain"],
        "confidence": round(confidence, 4),
        "method": "dataset_centroid_cosine",
        "rule_domain": rule_domain,
        "source": source_prefix,
        "profile_limit": profile_limit,
        "candidates": candidates[:top_k],
    })
