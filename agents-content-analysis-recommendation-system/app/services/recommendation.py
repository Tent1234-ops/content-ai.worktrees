from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from statistics import median
from typing import Any, Dict, Iterable, List

from sqlalchemy.orm import Session

from app.database.models import AnalysisResult, DatasetContent, UserContent
from app.services.admin_settings import get_admin_config
from app.services.classification import classify_text_domain
from app.services.dataset_contract import RECOMMENDATION_DURATION_MAX_SECONDS
from app.services.dataset_eligibility import production_transcript_query, reference_transcript_rows
from app.core.datetime_utils import utc_isoformat
from app.services.recommendation_evidence import attach_evidence, fingerprint, freeze_reference, locate_terms, user_context
from app.services.actionable_recommendations import build_actionable_recommendations
from app.services.topic_comparisons import build_topic_comparisons
from app.services.nlp import (
    extract_comparable_keyword_candidates,
    extract_keyword_candidates,
    filter_tokens,
    normalize_text_for_nlp,
    run_nlp_pipeline,
    tokenize_text,
)
from app.services.pipeline.core import (
    build_comparison_profile,
    build_dimension_status,
    extract_features,
    feature_to_keywords,
    normalize_asr_terms,
    normalize_space,
)
from app.services.pipeline.domain_rules import (
    DOMAIN_BASE,
    DOMAIN_DIMENSIONS_ORDER,
    DOMAIN_HINTS,
    detect_domain,
    infer_domain_from_features,
    normalize_domain,
)
from app.services.taxonomy import (
    UNKNOWN_LEAF_KEY,
    normalize_taxonomy_leaf,
    ready_leaf_keys,
)
from app.services.view_metrics import resolve_view_metric_version

DEFAULT_DURATION_BY_DOMAIN = {
    "audio": 75,
    "smartphone": 90,
    "food_drink": 45,
    "fashion": 60,
    "keyboard": 75,
    "mouse": 60,
    "skincare": 75,
    "general": 60,
    "phone": 90,
    "camera": 75,
    "laptop": 90,
    "headphone": 75,
    "hardware": 90,
    "general_food": 45,
    "drink": 45,
    "makeup": 60,
    "grooming": 60,
    "shirt": 60,
    "shoes": 60,
    "unknown": 60,
}

DURATION_MINIMUM_SAMPLE_SIZE = 10
DURATION_TARGET_SAMPLE_SIZE = 15
DURATION_PERCENTILE_LOW = 25
DURATION_PERCENTILE_HIGH = 75
DURATION_COHORT_UPLOAD_COMPATIBLE = "upload_compatible_under_5m"

KEYWORD_DOMAIN_BY_TAXONOMY_LEAF = {
    "phone": "smartphone",
    "camera": "general",
    "laptop": "general",
    "audio": "audio",
    "headphone": "audio",
    "hardware": "general",
    "general_food": "food_drink",
    "drink": "food_drink",
    "makeup": "general",
    "grooming": "general",
    "shirt": "fashion",
    "shoes": "fashion",
}

GENERIC_RECOMMENDATION_BLACKLIST = {
    "video",
    "clip",
    "review",
    "youtube",
    "content",
    "subscribe",
    "follow",
    "like",
    "watch",
    "new",
    "best",
    "reviewing",
    "today",
    "รีวิว",
    "คลิป",
    "วิดีโอ",
    "วันนี้",
    "ครับ",
    "ค่ะ",
    "นะครับ",
    "นะคะ",
    "ช่อง",
    "ฝาก",
    "กดไลก์",
    "กดติดตาม",
    "มือถือ",
    "โทรศัพท์",
    "สมาร์ตโฟน",
}

KEYWORD_DOCUMENT_WEIGHT = 0.45
KEYWORD_FREQUENCY_WEIGHT = 0.25
KEYWORD_ENGAGEMENT_WEIGHT = 0.30
KEYWORD_EVIDENCE_EXAMPLE_LIMIT = 3

def _keyword_domain(leaf_key: str) -> str:
    return KEYWORD_DOMAIN_BY_TAXONOMY_LEAF.get(leaf_key, "general")


def recommendation_domain_for_taxonomy_leaf(leaf_key: str) -> str:
    """Map the Active Model taxonomy leaf to its downstream rule profile."""
    canonical_leaf = normalize_taxonomy_leaf(leaf_key)
    if canonical_leaf == UNKNOWN_LEAF_KEY:
        return "general"
    return _keyword_domain(canonical_leaf)


def _normalize_keyword(keyword: str) -> str:
    return normalize_text_for_nlp(keyword or "").strip().lower()


def _keyword_identity(keyword: str, domain: str) -> str:
    """Return one canonical identity so surface synonyms cannot create a gap."""
    normalized = _normalize_keyword(keyword)
    if not normalized:
        return ""
    comparable = extract_comparable_keyword_candidates(normalized, domain)
    if comparable:
        return _normalize_keyword(str(comparable[0]["keyword"]))
    return normalized


def _keyword_is_domain_relevant(keyword: str, domain: str) -> bool:
    if not keyword:
        return False
    if domain == "general":
        return True
    lower = _normalize_keyword(keyword)
    canonical_dimensions = {
        _normalize_keyword(name)
        for name in DOMAIN_DIMENSIONS_ORDER.get(domain, [])
    }
    if lower in canonical_dimensions:
        return True
    hints = [*DOMAIN_HINTS.get(domain, []), *DOMAIN_BASE.get(domain, [])]
    hint_words: set[str] = set()
    for hint in hints:
        if not hint:
            continue
        normalized_hint = hint.lower()
        if normalized_hint in lower:
            return True
        for token in re.findall(r"[\u0E00-\u0E7Fa-z0-9]+", normalized_hint):
            if token:
                hint_words.add(token)
    keyword_tokens = set(re.findall(r"[\u0E00-\u0E7Fa-z0-9]+", lower))
    if len(keyword_tokens & hint_words) >= 2:
        return True
    return False


def _should_recommend_keyword(keyword: str, domain: str) -> bool:
    lower = _normalize_keyword(keyword)
    if not lower or lower in GENERIC_RECOMMENDATION_BLACKLIST:
        return False
    if domain != "general" and not _keyword_is_domain_relevant(lower, domain):
        return False
    return True


def _row_performance_signal(row: DatasetContent) -> float:
    """Comparable public performance signal captured with the dataset row."""
    average_views_per_day = max(0.0, float(row.average_views_per_day or 0.0))
    engagement_rate = max(0.0, float(row.engagement_rate or 0.0))
    computed = math.log1p(average_views_per_day) * (
        1.0 + min(engagement_rate * 10.0, 1.0)
    )
    return max(computed, float(row.trend_score or 0.0), 0.0)


def _dataset_keyword_occurrences(
    row: DatasetContent,
    *,
    domain: str,
) -> Dict[str, Dict[str, Any]]:
    """Extract per-document term frequency from spoken transcript evidence only."""
    transcript = str(row.transcript or "")
    if not transcript.strip():
        return {}

    occurrences: Dict[str, Dict[str, Any]] = {}
    for item in extract_comparable_keyword_candidates(transcript, domain):
        keyword = str(item["keyword"]).strip()
        identity = _keyword_identity(keyword, domain)
        if not identity or not _should_recommend_keyword(keyword, domain):
            continue
        occurrences[identity] = {
            "keyword": keyword,
            "frequency": max(1, int(item.get("frequency") or 1)),
            "matched_terms": list(item.get("matched_terms") or []),
        }

    # Canonical concepts are preferred. Domain-specific surface terms remain useful
    # for taxonomies that do not yet have a synonym map of their own.
    for item in extract_keyword_candidates(transcript)[:40]:
        surface_keyword = str(item.get("keyword") or "").strip()
        identity = _keyword_identity(surface_keyword, domain)
        if not identity or identity in occurrences:
            continue
        display_keyword = identity if identity != _normalize_keyword(surface_keyword) else surface_keyword
        if not _should_recommend_keyword(display_keyword, domain):
            continue
        occurrences[identity] = {
            "keyword": display_keyword,
            "frequency": max(1, int(item.get("frequency") or 1)),
            "matched_terms": [surface_keyword],
        }
    segments = freeze_reference(row)["segments"] if getattr(row, "transcript_timestamps_available", False) else []
    for identity, item in list(occurrences.items()):
        proof = locate_terms(transcript, [item["keyword"], *item["matched_terms"]], segments=segments)
        if not proof:
            del occurrences[identity]
            continue
        item["frequency"] = len(proof)
        item["occurrences"] = proof[:3]
        item["matched_terms"] = sorted({match["matched_text"] for match in proof})
    return occurrences


def _build_keyword_evidence(
    rows: List[DatasetContent],
    *,
    row_weights: Dict[int, float],
    domain: str,
    max_items: int,
) -> List[Dict[str, Any]]:
    """Rank terms using document support, per-video frequency, and performance."""
    if not rows:
        return []

    aggregates: Dict[str, Dict[str, Any]] = {}
    total_row_weight = sum(
        row_weights.get(int(row.dataset_id), 1.0)
        for row in rows
    ) or float(len(rows))

    for row in rows:
        dataset_id = int(row.dataset_id)
        performance_weight = row_weights.get(dataset_id, 1.0)
        statistics = freeze_reference(row)["statistics"]
        for identity, occurrence in _dataset_keyword_occurrences(
            row,
            domain=domain,
        ).items():
            frequency = max(1, int(occurrence["frequency"]))
            aggregate = aggregates.setdefault(
                identity,
                {
                    "keyword": str(occurrence["keyword"]),
                    "support_count": 0,
                    "total_frequency": 0,
                    "frequency_signal": 0.0,
                    "engagement_signal": 0.0,
                    "matched_terms": set(),
                    "supporting_examples": [],
                },
            )
            aggregate["support_count"] += 1
            aggregate["total_frequency"] += frequency
            aggregate["frequency_signal"] += math.log1p(frequency)
            aggregate["engagement_signal"] += performance_weight
            aggregate["matched_terms"].update(occurrence["matched_terms"])
            aggregate["supporting_examples"].append(
                {
                    "dataset_id": dataset_id,
                    "source_record_id": str(row.source_record_id or ""),
                    "title": str(row.title or "Untitled"),
                    "video_url": str(row.video_url or row.source_release_url or ""),
                    "published_at": utc_isoformat(row.published_at),
                    "statistics_captured_at": utc_isoformat(row.statistics_captured_at),
                    "source_channel_id": str(row.source_channel_id or ""),
                    "data_split": row.data_split,
                    "platform": _platform_key(row.source_platform, "youtube"),
                    "frequency": frequency,
                    "occurrences": occurrence["occurrences"],
                    "matched_terms": list(occurrence["matched_terms"]),
                    **statistics,
                    "average_views_per_day": round(
                        max(0.0, float(row.average_views_per_day or 0.0)),
                        3,
                    ),
                    "engagement_rate": round(
                        max(0.0, float(row.engagement_rate or 0.0)),
                        6,
                    ),
                    "performance_weight": round(performance_weight, 4),
                }
            )

    minimum_support = 1 if len(rows) < 4 else 2
    supported = [
        aggregate
        for aggregate in aggregates.values()
        if int(aggregate["support_count"]) >= minimum_support
    ]
    if not supported:
        return []

    max_frequency_signal = max(
        float(aggregate["frequency_signal"]) for aggregate in supported
    ) or 1.0
    ranked: List[Dict[str, Any]] = []
    for aggregate in supported:
        support_count = int(aggregate["support_count"])
        document_component = support_count / len(rows)
        frequency_component = float(aggregate["frequency_signal"]) / max_frequency_signal
        engagement_component = float(aggregate["engagement_signal"]) / total_row_weight
        score = (
            KEYWORD_DOCUMENT_WEIGHT * document_component
            + KEYWORD_FREQUENCY_WEIGHT * frequency_component
            + KEYWORD_ENGAGEMENT_WEIGHT * engagement_component
        )
        examples = sorted(
            aggregate["supporting_examples"],
            key=lambda item: (
                -float(item["performance_weight"]),
                -int(item["frequency"]),
                int(item["dataset_id"]),
            ),
        )
        ranked.append(
            {
                "keyword": str(aggregate["keyword"]),
                "score": round(score, 4),
                "support_count": support_count,
                "sample_size": len(rows),
                "support_ratio": round(document_component, 4),
                "total_frequency": int(aggregate["total_frequency"]),
                "matched_terms": sorted(str(term) for term in aggregate["matched_terms"]),
                "supporting_dataset_row_ids": [
                    int(item["dataset_id"]) for item in examples
                ],
                "supporting_examples": examples[:KEYWORD_EVIDENCE_EXAMPLE_LIMIT],
                "supporting_records": examples,
                "channel_count": len({item["source_channel_id"] for item in examples if item["source_channel_id"]}),
                "score_components": {
                    "document_coverage": round(document_component, 4),
                    "frequency": round(frequency_component, 4),
                    "engagement": round(engagement_component, 4),
                },
            }
        )

    ranked.sort(
        key=lambda item: (
            -float(item["score"]),
            -int(item["support_count"]),
            str(item["keyword"]),
        )
    )
    return ranked[:max_items]


def _clean_profile_keywords(items: List[Dict[str, float]], domain: str, max_items: int) -> List[Dict[str, float]]:
    cleaned: List[Dict[str, float]] = []
    seen: set[str] = set()
    for item in items:
        keyword = str(item.get("keyword") or "").strip()
        if not keyword:
            continue
        lower = _normalize_keyword(keyword)
        if lower in seen:
            continue
        if not _should_recommend_keyword(lower, domain):
            continue
        seen.add(lower)
        cleaned.append({"keyword": keyword, "score": float(item.get("score", 0.0))})
        if len(cleaned) >= max_items:
            break
    return cleaned


def _weighted_increment(counter: Dict[str, float], key: str, weight: float) -> None:
    if not key:
        return
    counter[key] = counter.get(key, 0.0) + weight


def _fast_dataset_tokens(text: str) -> List[str]:
    return filter_tokens(tokenize_text(text or ""))


def _fast_keyword_items(text: str, domain: str, max_keywords: int) -> List[Dict[str, float]]:
    normalized = normalize_space(text or "").lower()
    token_counts = Counter(_fast_dataset_tokens(normalized))
    scores: Dict[str, float] = {}

    for phrase in [*DOMAIN_BASE.get(domain, []), *DOMAIN_HINTS.get(domain, [])]:
        phrase_text = str(phrase or "").strip().lower()
        if not phrase_text:
            continue
        if phrase_text in normalized:
            scores[phrase_text] = max(scores.get(phrase_text, 0.0), 2.5 + len(phrase_text.split()) * 0.3)

    for token, count in token_counts.items():
        scores[token] = max(scores.get(token, 0.0), float(count))

    for item in extract_comparable_keyword_candidates(normalized, domain):
        canonical_keyword = str(item["keyword"])
        scores[canonical_keyword] = max(
            scores.get(canonical_keyword, 0.0),
            float(item["score"]),
        )

    ranked = [
        {"keyword": keyword, "score": round(score, 3)}
        for keyword, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    ]
    return ranked[:max_keywords]


def _analyze_dataset_profile_snapshot(
    text: str,
    title: str | None = None,
    category: str | None = None,
    max_keywords: int = 12,
    hook_duration: int = 60,
) -> Dict[str, object]:
    merged_text = " ".join(part for part in [title or "", text or "", category or ""] if part).strip()
    category_domain = normalize_domain(category)
    detected = detect_domain(f"{merged_text} {category or ''}")
    domain = category_domain if category_domain != "general" else detected
    if domain not in DEFAULT_DURATION_BY_DOMAIN:
        domain = detected if detected in DEFAULT_DURATION_BY_DOMAIN else "general"

    ranked_keywords = _fast_keyword_items(merged_text, domain, max_keywords)
    tokens = _fast_dataset_tokens(merged_text)
    hook_term_limit = min(12, max(4, int(hook_duration / 15)))
    return {
        "domain": domain,
        "nlp_result": {"top_keywords": ranked_keywords},
        "comparison_dimensions": [
            {"name": name, "confidence": 1.0}
            for name in DOMAIN_DIMENSIONS_ORDER.get(domain, [])[:8]
        ],
        "hook_terms": tokens[:hook_term_limit],
    }


def analyze_text_snapshot(
    text: str,
    title: str | None = None,
    max_keywords: int = 12,
    hook_duration: int = 60,
) -> Dict[str, object]:
    merged_text = " ".join(part for part in [title or "", text or ""] if part).strip()
    merged_text = normalize_asr_terms(merged_text)
    features = extract_features(merged_text)
    detected = detect_domain(merged_text)
    domain = infer_domain_from_features(features, detected)

    nlp_result = run_nlp_pipeline(merged_text, max_keywords=max_keywords)
    ranked_keywords = [
        {"keyword": item["keyword"], "score": float(item["score"]) }
        for item in nlp_result.get("top_keywords", [])
    ]
    existing_keywords = {item["keyword"] for item in ranked_keywords}
    for keyword in feature_to_keywords(features, domain):
        if keyword not in existing_keywords:
            ranked_keywords.append({"keyword": keyword, "score": 1.0})

    comparable_keywords, comparison_dimensions = build_comparison_profile(
        domain=domain,
        features=features,
        ranked_keywords=ranked_keywords,
        text=merged_text,
    )
    dimension_status = build_dimension_status(domain, comparison_dimensions)

    tokens = filter_tokens(tokenize_text(normalize_text_for_nlp(merged_text)))
    hook_term_limit = min(12, max(4, int(hook_duration / 15)))
    hook_terms = tokens[:hook_term_limit]
    return {
        "domain": domain,
        "features": features,
        "nlp_result": nlp_result,
        "comparable_keywords": comparable_keywords,
        "comparison_dimensions": comparison_dimensions,
        "dimension_status": dimension_status,
        "tokens": tokens,
        "hook_terms": hook_terms,
    }


def build_classified_user_signal_snapshot(
    *,
    text: str,
    hook_text: str,
    taxonomy_leaf_key: str,
    max_keywords: int = 10,
) -> Dict[str, object]:
    """Build every downstream user signal from the Active Model category."""
    transcript = normalize_text_for_nlp(str(text or "").strip())
    canonical_leaf = normalize_taxonomy_leaf(taxonomy_leaf_key)
    recommendation_domain = recommendation_domain_for_taxonomy_leaf(canonical_leaf)

    nlp_result = run_nlp_pipeline(transcript, max_keywords=max_keywords)
    ranked_keywords = [
        {
            "keyword": str(item.get("keyword") or "").strip(),
            "score": float(item.get("score") or 0.0),
        }
        for item in nlp_result.get("top_keywords", [])
        if str(item.get("keyword") or "").strip()
    ]
    comparable_candidates = extract_comparable_keyword_candidates(
        transcript,
        recommendation_domain,
    )
    comparable_keywords = [
        str(item["keyword"])
        for item in comparable_candidates
    ]
    comparison_dimensions = [
        {
            "name": str(item["keyword"]),
            "confidence": min(1.0, float(item["score"]) / 5.0),
            "value": "mentioned",
        }
        for item in comparable_candidates
    ]
    dimension_status = build_dimension_status(
        recommendation_domain,
        comparison_dimensions,
    )

    def evidence_first_keywords(
        candidates: List[Dict[str, object]],
        ranked: List[Dict[str, object]],
    ) -> List[str]:
        selected: List[str] = []
        seen: set[str] = set()

        for candidate in candidates:
            matched_terms = [
                str(term).strip()
                for term in candidate.get("matched_terms", [])
                if str(term).strip()
            ]
            if not matched_terms:
                continue
            surface_term = matched_terms[0]
            normalized_term = surface_term.lower()
            if normalized_term in seen:
                continue
            seen.add(normalized_term)
            selected.append(surface_term)
            if len(selected) >= max_keywords:
                return selected

        for item in ranked:
            keyword = str(item.get("keyword") or "").strip()
            normalized_keyword = keyword.lower()
            if not normalized_keyword or normalized_keyword in seen:
                continue
            if (
                recommendation_domain != "general"
                and not _keyword_is_domain_relevant(
                    normalized_keyword,
                    recommendation_domain,
                )
            ):
                continue
            seen.add(normalized_keyword)
            selected.append(keyword)
            if len(selected) >= max_keywords:
                break
        return selected

    content_keywords = evidence_first_keywords(
        comparable_candidates,
        ranked_keywords,
    )

    user_keywords: List[str] = []
    seen_keywords: set[str] = set()
    for keyword in [
        *content_keywords,
        *comparable_keywords,
    ]:
        normalized_keyword = str(keyword or "").strip().lower()
        if not normalized_keyword or normalized_keyword in seen_keywords:
            continue
        seen_keywords.add(normalized_keyword)
        user_keywords.append(str(keyword).strip())

    hook_nlp_result = (
        run_nlp_pipeline(
            normalize_text_for_nlp(str(hook_text or "").strip()),
            max_keywords=max_keywords,
        )
        if str(hook_text or "").strip()
        else {}
    )
    hook_comparable_candidates = extract_comparable_keyword_candidates(
        str(hook_text or ""),
        recommendation_domain,
    )
    hook_ranked_keywords = [
        item
        for item in hook_nlp_result.get("top_keywords", [])
        if isinstance(item, dict)
    ]
    hook_terms = evidence_first_keywords(
        hook_comparable_candidates,
        hook_ranked_keywords,
    )
    if not hook_terms:
        hook_terms = [
            str(term).strip()
            for term in hook_nlp_result.get("filtered_tokens", [])
            if str(term).strip()
        ][:max_keywords]
    comparable_keyword_evidence = [
        {
            "keyword": str(item["keyword"]),
            "score": float(item["score"]),
            "frequency": int(item["frequency"]),
            "matched_terms": list(item["matched_terms"]),
        }
        for item in comparable_candidates
    ]
    hook_comparable_keywords = [
        str(item["keyword"])
        for item in hook_comparable_candidates
    ]

    content_ranked_lookup = {
        str(item["keyword"]).strip().lower(): float(item["score"])
        for item in ranked_keywords
    }
    nlp_result["top_keywords"] = [
        {
            "keyword": keyword,
            "score": content_ranked_lookup.get(keyword.lower(), 1.0),
        }
        for keyword in content_keywords
    ]
    nlp_result["content_keywords"] = list(content_keywords)
    nlp_result["comparable_keywords"] = list(comparable_keywords)
    nlp_result["comparable_keyword_evidence"] = comparable_keyword_evidence

    return {
        "taxonomy_leaf_key": canonical_leaf,
        "recommendation_domain": recommendation_domain,
        "nlp_result": nlp_result,
        "content_keywords": content_keywords,
        "user_keywords": user_keywords,
        "hook_terms": hook_terms,
        "hook_comparable_keywords": hook_comparable_keywords,
        "comparable_keywords": comparable_keywords,
        "comparable_keyword_evidence": comparable_keyword_evidence,
        "comparison_dimensions": comparison_dimensions,
        "dimension_status": dimension_status,
    }


def _percentile(values: List[int], percentile: int) -> int:
    if not values:
        raise ValueError("Percentile requires at least one value")
    position = (len(values) - 1) * (percentile / 100.0)
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return int(round(values[lower_index]))
    fraction = position - lower_index
    interpolated = values[lower_index] + (
        (values[upper_index] - values[lower_index]) * fraction
    )
    return int(round(interpolated))


def _duration_summary(durations: List[int], domain: str) -> Dict[str, object]:
    cleaned = sorted(duration for duration in durations if duration and duration > 0)
    base = {
        "sample_size": len(cleaned),
        "minimum_sample_size": DURATION_MINIMUM_SAMPLE_SIZE,
        "target_sample_size": DURATION_TARGET_SAMPLE_SIZE,
        "cohort": DURATION_COHORT_UPLOAD_COMPATIBLE,
        "percentile_low": DURATION_PERCENTILE_LOW,
        "percentile_high": DURATION_PERCENTILE_HIGH,
    }
    if len(cleaned) < DURATION_MINIMUM_SAMPLE_SIZE:
        return {
            **base,
            "recommended_seconds": None,
            "recommended_range": "Insufficient evidence",
            "median_seconds": None,
            "percentile_low_seconds": None,
            "percentile_high_seconds": None,
            "source": "youtube_metadata" if cleaned else "none",
            "evidence_status": "insufficient_evidence",
        }

    mid = int(round(float(median(cleaned))))
    low = _percentile(cleaned, DURATION_PERCENTILE_LOW)
    high = _percentile(cleaned, DURATION_PERCENTILE_HIGH)
    if high < low:
        high = low
    return {
        **base,
        "recommended_seconds": mid,
        "recommended_range": f"{low}-{high} sec",
        "median_seconds": mid,
        "percentile_low_seconds": low,
        "percentile_high_seconds": high,
        "source": "youtube_metadata",
        "evidence_status": "sufficient",
    }


def _source_label(
    source_prefix: str,
    sample_size: int,
    eligible_pool_size: int = 0,
) -> str:
    if sample_size <= 0:
        return "No eligible verified transcript samples found for this taxonomy leaf"
    if source_prefix == "youtube":
        pool_label = (
            f" from {eligible_pool_size} eligible same-category clips"
            if eligible_pool_size > sample_size
            else ""
        )
        return (
            "Human-reviewed public YouTube transcripts "
            f"({sample_size} high-performing clips{pool_label})"
        )
    if source_prefix == "google":
        return f"Google Trends dataset ({sample_size} same-type items)"
    if source_prefix == "tiktok":
        return f"TikTok live/dataset trends ({sample_size} same-type items)"
    return f"{source_prefix} dataset ({sample_size} same-type samples)"


def _build_evidence(profile: Dict[str, object], *, source_prefix: str) -> Dict[str, object]:
    duration = profile.get("recommended_duration")
    if not isinstance(duration, dict):
        duration = {}
    sample_size = int(profile.get("sample_size") or 0)
    eligible_pool_size = int(profile.get("eligible_pool_size") or sample_size)
    duration_sample_size = int(duration.get("sample_size") or 0)
    duration_source = str(duration.get("source") or "none")
    duration_status = str(
        duration.get("evidence_status") or "insufficient_evidence"
    )
    duration_minimum = int(
        duration.get("minimum_sample_size") or DURATION_MINIMUM_SAMPLE_SIZE
    )
    duration_target = int(
        duration.get("target_sample_size") or DURATION_TARGET_SAMPLE_SIZE
    )
    return {
        "source": profile.get("source") or source_prefix,
        "dataset_sources": profile.get("dataset_sources") or [],
        "dataset_versions": profile.get("dataset_versions") or [],
        "data_source_label": _source_label(
            source_prefix,
            sample_size,
            eligible_pool_size,
        ),
        "dataset_sample_size": sample_size,
        "eligible_pool_size": eligible_pool_size,
        "view_metric_version": profile.get("view_metric_version") or "",
        "view_metric_cohort_size": int(
            profile.get("view_metric_cohort_size") or 0
        ),
        "performance_eligible_pool_size": int(
            profile.get("performance_eligible_pool_size") or 0
        ),
        "excluded_incompatible_view_metric_rows": int(
            profile.get("excluded_incompatible_view_metric_rows") or 0
        ),
        "source_platform_counts": profile.get("source_platform_counts") or {},
        "transcript_source_counts": profile.get("transcript_source_counts") or {},
        "language_counts": profile.get("language_counts") or {},
        "collection_strategy_counts": profile.get("collection_strategy_counts") or {},
        "selection_rule": profile.get("selection_rule") or "none",
        "reference_policy": "train_only_no_evaluation_channel_overlap_v1",
        "reference_period": profile.get("reference_period") or {},
        "reference_records": profile.get("reference_records") or [],
        "license_name": profile.get("license_name") or "",
        "verification_status": profile.get("verification_status") or "",
        "duration_source": duration_source,
        "duration_evidence_status": duration_status,
        "duration_sample_size": duration_sample_size,
        "duration_minimum_sample_size": duration_minimum,
        "duration_target_sample_size": duration_target,
        "duration_cohort": duration.get("cohort")
        or DURATION_COHORT_UPLOAD_COMPATIBLE,
        "duration_samples": profile.get("duration_samples") or [],
        "duration_dataset_row_ids": profile.get("duration_dataset_row_ids") or [],
        "duration_source_record_ids": profile.get("duration_source_record_ids") or [],
        "duration_exemplar_titles": profile.get("duration_exemplar_titles") or [],
        "duration_selection_rule": profile.get("duration_selection_rule") or "none",
        "exemplar_titles": profile.get("exemplar_titles") or [],
        "dataset_row_ids": profile.get("dataset_row_ids") or [],
        "source_record_ids": profile.get("source_record_ids") or [],
        "keyword_evidence_dataset_row_ids": sorted(
            {
                int(dataset_id)
                for item in profile.get("top_keywords") or []
                for dataset_id in item.get("supporting_dataset_row_ids", [])
            }
        ),
        "keyword_score_weights": {
            "document_coverage": KEYWORD_DOCUMENT_WEIGHT,
            "frequency": KEYWORD_FREQUENCY_WEIGHT,
            "engagement": KEYWORD_ENGAGEMENT_WEIGHT,
        },
        "keyword_score_explanation": (
            "Keyword gap uses only human-reviewed public YouTube transcripts in the "
            "same taxonomy leaf. Each score combines the number of supporting clips "
            "(45%), term frequency inside each transcript (25%), and the public "
            "performance weight of those clips (30%). High-performing examples are "
            "selected by average views per day and engagement rate inside one "
            "compatible public view-count metric version."
            if sample_size > 0
            else "No eligible same-type transcript samples were available; no dataset keyword evidence was generated."
        ),
        "duration_explanation": (
            "Recommended duration is the median of "
            f"{duration_sample_size} human-reviewed, same-category videos; the "
            f"displayed range is P{DURATION_PERCENTILE_LOW}-P{DURATION_PERCENTILE_HIGH}. "
            "Durations come from YouTube contentDetails metadata and are limited "
            "to videos compatible with the current five-minute upload limit."
            if duration_status == "sufficient"
            else "Insufficient evidence: "
            f"{duration_sample_size} of {duration_minimum} required same-category "
            "YouTube duration samples are available. No duration number is "
            f"recommended until the minimum is reached; the collection target is {duration_target}."
        ),
    }


def build_dataset_profiles(
    db: Session,
    *,
    source_prefix: str = "youtube",
    limit: int = 150,
) -> List[Dict[str, object]]:
    admin_config = get_admin_config(db)
    if source_prefix == "youtube" and not admin_config.enable_youtube_trending:
        return []
    if source_prefix == "google" and not admin_config.enable_google_trends:
        return []
    profiles = [
        build_dataset_profile_for_domain(
            db,
            domain=leaf_key,
            source_prefix=source_prefix,
            limit=limit,
        )
        for leaf_key in sorted(ready_leaf_keys(db))
    ]
    return [profile for profile in profiles if int(profile["sample_size"]) > 0]


def _platform_key(source_platform: str | None, source_prefix: str) -> str:
    value = str(source_platform or source_prefix).strip().lower()
    for platform in ("youtube", "google", "tiktok"):
        if value.startswith(platform):
            return platform
    return value or source_prefix


def _high_performing_rows(
    rows: List[DatasetContent],
    *,
    limit: int,
) -> tuple[List[DatasetContent], Dict[int, float]]:
    if not rows:
        return [], {}
    rankable = [row for row in rows if _row_performance_signal(row) > 0.0]
    ranked = sorted(
        rankable,
        key=lambda row: (
            -_row_performance_signal(row),
            -int(row.views or 0),
            int(row.dataset_id),
        ),
    )
    if not ranked:
        return [], {}
    selection_size = min(limit, max(10, math.ceil(len(ranked) * 0.4)))
    selected = ranked[:selection_size]
    signals = [_row_performance_signal(row) for row in selected]
    minimum_signal = min(signals)
    signal_range = max(signals) - minimum_signal
    weights = {}
    for row, signal in zip(selected, signals):
        normalized_signal = (
            (signal - minimum_signal) / signal_range
            if signal_range > 0
            else 1.0
        )
        weights[int(row.dataset_id)] = 1.0 + (2.0 * normalized_signal)
    return selected, weights


def _single_view_metric_cohort(
    rows: List[DatasetContent],
) -> tuple[List[DatasetContent], str, int]:
    if not rows:
        return [], "", 0

    grouped: Dict[str, List[DatasetContent]] = defaultdict(list)
    for row in rows:
        version = resolve_view_metric_version(
            row.source_platform,
            row.statistics_captured_at or row.created_at,
            row.view_metric_version,
        )
        grouped[version].append(row)

    selected_version, selected_rows = max(
        grouped.items(),
        key=lambda item: (
            len(item[1]),
            max(int(row.dataset_id or 0) for row in item[1]),
        ),
    )
    excluded = len(rows) - len(selected_rows)
    return selected_rows, selected_version, excluded


def _has_youtube_duration_metadata(row: DatasetContent) -> bool:
    try:
        metadata = json.loads(str(row.raw_metadata_json or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(metadata, dict):
        return False
    content_details = metadata.get("contentDetails")
    if not isinstance(content_details, dict):
        nested = metadata.get("raw_metadata")
        content_details = (
            nested.get("contentDetails") if isinstance(nested, dict) else None
        )
    return bool(
        isinstance(content_details, dict)
        and str(content_details.get("duration") or "").strip()
    )


def _duration_evidence_rows(
    rows: Iterable[DatasetContent],
) -> List[DatasetContent]:
    selected = []
    for row in rows:
        duration = int(row.duration_seconds or 0)
        if (
            row.is_duration_recommendation_eligible
            and 0 < duration <= RECOMMENDATION_DURATION_MAX_SECONDS
            and _has_youtube_duration_metadata(row)
        ):
            selected.append(row)
    return sorted(selected, key=lambda row: int(row.dataset_id or 0))


def build_dataset_profile_for_domain(
    db: Session,
    *,
    domain: str,
    source_prefix: str = "youtube",
    limit: int = 150,
    now: datetime | None = None,
) -> Dict[str, object]:
    """Build recommendation evidence from the exact canonical category rows used."""
    canonical_domain = normalize_taxonomy_leaf(domain)
    keyword_domain = _keyword_domain(canonical_domain)
    admin_config = get_admin_config(db)
    eligible_rows: List[DatasetContent] = []
    if canonical_domain in ready_leaf_keys(db):
        eligible_rows = [row for row in reference_transcript_rows(db, domain=canonical_domain, now=now)
                         if row.source_platform.startswith(source_prefix)]
    # A video imported in multiple versions remains one supporting clip.
    eligible_rows = list({row.source_youtube_id or f"row:{row.dataset_id}": row for row in eligible_rows}.values())
    metric_cohort, view_metric_version, excluded_metric_rows = (
        _single_view_metric_cohort(eligible_rows)
    )
    rows, row_weights = _high_performing_rows(metric_cohort, limit=limit)
    duration_rows = _duration_evidence_rows(eligible_rows)
    durations = [int(row.duration_seconds) for row in duration_rows]
    duration_summary = _duration_summary(durations, canonical_domain)

    platform_counts: Counter[str] = Counter()
    transcript_source_counts: Counter[str] = Counter()
    language_counts: Counter[str] = Counter()
    collection_strategy_counts: Counter[str] = Counter()

    for row in rows:
        platform_counts[_platform_key(row.source_platform, source_prefix)] += 1
        transcript_source_counts[str(row.transcript_source or "unknown")] += 1
        language_counts[str(row.language or "und")] += 1
        collection_strategy_counts[
            str(row.collection_strategy or "classification_diverse")
        ] += 1

    top_keywords = _build_keyword_evidence(
        rows,
        row_weights=row_weights,
        domain=keyword_domain,
        max_items=max(10, admin_config.max_keywords_display),
    )
    top_dimensions = [dict(item) for item in top_keywords[:8]]
    # No timing claim can be made from the beginning of an untimed transcript.
    hook_keywords = []

    sample_size = len(rows)
    if sum(platform_counts.values()) != sample_size:
        raise RuntimeError("Recommendation evidence platform counts do not match sample size")

    evidence_rows = list({row.dataset_id: row for row in [*rows, *duration_rows]}.values())
    return {
        "domain": canonical_domain,
        # Removed before serialization and used only by the Phase 5 comparison service.
        # This is the complete reference cohort before the performance filter.
        "_comparison_reference_rows": eligible_rows,
        "_reference_documents": [freeze_reference(row) for row in evidence_rows],
        "sample_size": sample_size,
        "eligible_pool_size": len(eligible_rows),
        "reference_period": {
            "published_from": utc_isoformat(min(row.published_at for row in evidence_rows)) if evidence_rows else None,
            "published_to": utc_isoformat(max(row.published_at for row in evidence_rows)) if evidence_rows else None,
            "statistics_from": utc_isoformat(min(row.statistics_captured_at for row in evidence_rows)) if evidence_rows else None,
            "statistics_to": utc_isoformat(max(row.statistics_captured_at for row in evidence_rows)) if evidence_rows else None,
        },
        "reference_records": [
            {"dataset_id": row.dataset_id, "video_url": row.video_url or row.source_release_url,
             "source_channel_id": row.source_channel_id, "data_split": row.data_split,
             "published_at": utc_isoformat(row.published_at),
             "statistics_captured_at": utc_isoformat(row.statistics_captured_at)}
            for row in evidence_rows
        ],
        "view_metric_version": view_metric_version,
        "view_metric_cohort_size": len(metric_cohort),
        "performance_eligible_pool_size": sum(
            1 for row in metric_cohort if _row_performance_signal(row) > 0.0
        ),
        "excluded_incompatible_view_metric_rows": excluded_metric_rows,
        "top_keywords": top_keywords,
        "top_dimensions": top_dimensions,
        "hook_keywords": hook_keywords,
        "recommended_duration": duration_summary,
        "duration_samples": sorted(durations),
        "duration_metadata_coverage_size": sum(
            1 for row in eligible_rows if _has_youtube_duration_metadata(row)
        ),
        "duration_eligible_pool_size": len(duration_rows),
        "duration_dataset_row_ids": [int(row.dataset_id) for row in duration_rows],
        "duration_source_record_ids": [
            str(row.source_record_id) for row in duration_rows
        ],
        "duration_exemplar_titles": [str(row.title) for row in duration_rows[:5]],
        "duration_selection_rule": (
            "same_category_human_verified_youtube_metadata_under_5_minutes"
            if duration_rows
            else "none"
        ),
        "exemplar_titles": [str(row.title) for row in rows[:5]],
        "dataset_row_ids": [int(row.dataset_id) for row in rows],
        "source_record_ids": [str(row.source_record_id) for row in rows],
        "source": "youtube_public_human_verified" if rows else "none",
        "dataset_sources": sorted({str(row.dataset_source) for row in rows}),
        "dataset_versions": sorted({str(row.dataset_version) for row in rows}),
        "source_platform_counts": dict(platform_counts),
        "transcript_source_counts": dict(transcript_source_counts),
        "language_counts": dict(language_counts),
        "collection_strategy_counts": dict(collection_strategy_counts),
        "selection_rule": (
            "same_category_single_view_metric_top_40_percent_by_performance"
            if rows
            else "none"
        ),
        "license_name": (
            ", ".join(sorted({str(row.license_name) for row in rows}))
            if rows
            else ""
        ),
        "verification_status": "human_verified" if rows else "",
    }


def _find_profile(profiles: Iterable[Dict[str, object]], domain: str) -> Dict[str, object]:
    domain = normalize_taxonomy_leaf(domain)
    for profile in profiles:
        if profile["domain"] == domain:
            return profile
    return {
        "domain": domain,
        "sample_size": 0,
        "eligible_pool_size": 0,
        "view_metric_version": "",
        "view_metric_cohort_size": 0,
        "performance_eligible_pool_size": 0,
        "excluded_incompatible_view_metric_rows": 0,
        "top_keywords": [],
        "top_dimensions": [
            {"keyword": name, "score": 0.0}
            for name in DOMAIN_DIMENSIONS_ORDER.get(_keyword_domain(domain), [])[:8]
        ],
        "hook_keywords": [],
        "recommended_duration": _duration_summary([], domain),
        "exemplar_titles": [],
        "duration_samples": [],
        "duration_metadata_coverage_size": 0,
        "duration_eligible_pool_size": 0,
        "duration_dataset_row_ids": [],
        "duration_source_record_ids": [],
        "duration_exemplar_titles": [],
        "duration_selection_rule": "none",
        "dataset_row_ids": [],
        "source_record_ids": [],
        "source": "none",
        "dataset_sources": [],
        "dataset_versions": [],
        "source_platform_counts": {},
        "transcript_source_counts": {},
        "language_counts": {},
        "collection_strategy_counts": {},
        "selection_rule": "none",
        "license_name": "",
        "verification_status": "",
    }


def build_recommendation_from_text(
    db: Session,
    *,
    title: str | None,
    text: str,
    source_prefix: str = "youtube",
    profile_limit: int = 150,
) -> Dict[str, object]:
    admin_config = get_admin_config(db)
    classification = classify_text_domain(
        db,
        title=None,
        text=text,
        source_prefix=source_prefix,
        profile_limit=profile_limit,
        require_active_model=True,
    )
    selected_domain = normalize_taxonomy_leaf(
        str(classification.get("taxonomy_leaf_key") or classification.get("domain"))
    )
    user_snapshot = build_classified_user_signal_snapshot(
        text=text,
        hook_text="",
        taxonomy_leaf_key=selected_domain,
        max_keywords=admin_config.max_keywords_display,
    )
    recommendation = build_recommendation_from_analysis_data(
        db,
        domain=selected_domain,
        user_keywords=list(user_snapshot["user_keywords"]),
        dimension_status=user_snapshot["dimension_status"],
        hook_terms=user_snapshot["hook_terms"],
        transcript=text,
        source_prefix=source_prefix,
        profile_limit=profile_limit,
        evidence_context=user_context(transcript=text, classification=classification),
    )
    recommendation["classification"] = classification
    return recommendation


def _finish_recommendation(db: Session, result: dict, context: dict, *, keyword_domain: str,
                           as_of: datetime) -> dict:
    comparison_rows = result["dataset_profile"].pop("_comparison_reference_rows", [])
    attach_evidence(result, context, keyword_domain=keyword_domain)
    result["actionable_recommendations"] = build_actionable_recommendations(result)
    comparisons = build_topic_comparisons(db, result, comparison_rows, as_of=as_of)
    result["evidence_bundle"]["topic_comparisons"] = comparisons
    result["evidence_bundle"]["data_fingerprint"] = fingerprint({
        "phase2_data_fingerprint": result["evidence_bundle"]["data_fingerprint"],
        "topic_comparisons": comparisons,
    })
    result["actionable_recommendations"]["evidence_data_fingerprint"] = (
        result["evidence_bundle"]["data_fingerprint"]
    )
    return result


def build_recommendation_from_analysis_data(
    db: Session,
    *,
    domain: str,
    user_keywords: List[str],
    dimension_status: List[Dict[str, object]],
    hook_terms: List[str],
    transcript: str = "",
    source_prefix: str = "youtube",
    profile_limit: int = 150,
    evidence_context: dict | None = None,
    as_of: datetime | None = None,
) -> Dict[str, object]:
    as_of = as_of or datetime.utcnow()
    domain = normalize_taxonomy_leaf(domain)
    context = evidence_context or user_context(transcript=transcript)
    if domain == "unknown":
        profile = _find_profile([], domain)
        profile["top_dimensions"] = []
        return _finish_recommendation(db, {
            "domain": domain, "status": "withheld_unknown", "user_keywords": list(user_keywords),
            "missing_keywords": [], "hook_keywords": [], "missing_dimensions": [],
            "current_trend_ideas": {"status": "unsupported_category", "ideas": []},
            "recommended_duration": profile["recommended_duration"], "dataset_profile": profile,
            "evidence": _build_evidence(profile, source_prefix=source_prefix),
        }, context, keyword_domain="unknown", as_of=as_of)
    keyword_domain = _keyword_domain(domain)
    profile = build_dataset_profile_for_domain(
        db,
        domain=domain,
        source_prefix=source_prefix,
        limit=profile_limit,
        now=as_of,
    )

    normalized_user_keywords = {
        identity
        for keyword in user_keywords
        for identity in (
            _normalize_keyword(keyword),
            _keyword_identity(keyword, keyword_domain),
        )
        if identity
    }
    normalized_user_keywords.update(
        _keyword_identity(str(row.get("name") or ""), keyword_domain)
        for row in dimension_status
        if str(row.get("status") or "").lower() == "present"
    )
    # Display limits must not turn an observed topic into a recommendation gap.
    observed_terms = [*hook_terms]
    if transcript.strip():
        observed_terms.extend(str(item["keyword"]) for item in (
            extract_comparable_keyword_candidates(transcript, keyword_domain)
            + extract_keyword_candidates(transcript)
        ))
    for term in observed_terms:
        normalized_user_keywords.update((
            _normalize_keyword(term), _keyword_identity(term, keyword_domain),
        ))
    missing_keywords = []
    for item in profile["top_keywords"]:
        keyword = str(item["keyword"]).strip()
        if not keyword:
            continue
        if (
            _normalize_keyword(keyword) in normalized_user_keywords
            or _keyword_identity(keyword, keyword_domain) in normalized_user_keywords
        ):
            continue
        missing_item = dict(item)
        missing_item["score"] = round(float(item["score"]), 4)
        missing_keywords.append(missing_item)
        if len(missing_keywords) >= 6:
            break

    # Propose supported missing concepts for the opening, preserving their evidence.
    # Untimed reference transcripts cannot prove these were successful opening words.
    hook_keywords = [dict(item) for item in missing_keywords[:5]]

    user_dimensions = {row["name"]: row for row in dimension_status}
    missing_dimensions = []
    for item in profile["top_dimensions"]:
        name = item["keyword"]
        user_dimension = user_dimensions.get(name)
        if user_dimension and user_dimension["status"] == "present":
            continue
        missing_dimensions.append(
            {
                "name": name,
                "score": round(float(item["score"]), 3),
                "user_status": user_dimension["status"] if user_dimension else "missing",
            }
        )
        if len(missing_dimensions) >= 6:
            break

    deduped_user_keywords = []
    seen = set()
    for keyword in user_keywords:
        low = keyword.lower()
        if low in seen:
            continue
        seen.add(low)
        deduped_user_keywords.append(keyword)

    from app.services.current_trend_ideas import build_current_trend_ideas
    current_ideas = build_current_trend_ideas(db, transcript=transcript, domain=domain)
    return _finish_recommendation(db, {
        "domain": domain,
        "user_keywords": deduped_user_keywords[:12],
        "current_trend_ideas": current_ideas,
        "missing_keywords": missing_keywords,
        "hook_keywords": hook_keywords,
        "missing_dimensions": missing_dimensions,
        "recommended_duration": profile["recommended_duration"],
        "dataset_profile": profile,
        "evidence": _build_evidence(profile, source_prefix=source_prefix),
    }, context, keyword_domain=keyword_domain, as_of=as_of)


def build_recommendation_from_saved_content(
    db: Session,
    *,
    content_id: int,
    source_prefix: str = "youtube",
    profile_limit: int = 150,
    user_id: int | None = None,
    allow_admin: bool = False,
) -> Dict[str, object] | None:
    query = db.query(UserContent).filter(UserContent.content_id == content_id)
    if user_id is not None and not allow_admin:
        query = query.filter(UserContent.user_id == user_id)

    content = query.first()
    if content is None:
        return None
    saved = db.query(AnalysisResult).filter(AnalysisResult.content_id == content_id).order_by(
        AnalysisResult.created_at.desc(), AnalysisResult.result_id.desc()).first()
    from app.services.saved_recommendations import stored_recommendation
    return stored_recommendation(content, saved)


def compare_dataset_profiles(
    db: Session,
    *,
    left_source: str = "youtube",
    right_source: str = "google",
    limit: int = 150,
) -> Dict[str, object]:
    left_profiles = build_dataset_profiles(db, source_prefix=left_source, limit=limit)
    right_profiles = build_dataset_profiles(db, source_prefix=right_source, limit=limit)

    left_map = {profile["domain"]: profile for profile in left_profiles}
    right_map = {profile["domain"]: profile for profile in right_profiles}
    domains = sorted(set(left_map) | set(right_map))

    comparisons = []
    for domain in domains:
        left_profile = _find_profile(left_profiles, domain)
        right_profile = _find_profile(right_profiles, domain)
        comparisons.append(
            {
                "domain": domain,
                "left_sample_size": int(left_profile["sample_size"]),
                "right_sample_size": int(right_profile["sample_size"]),
                "left_top_keywords": left_profile["top_keywords"][:5],
                "right_top_keywords": right_profile["top_keywords"][:5],
                "left_duration": left_profile["recommended_duration"],
                "right_duration": right_profile["recommended_duration"],
            }
        )

    return {
        "left_source": left_source,
        "right_source": right_source,
        "comparisons": comparisons,
    }


def build_recommendation_admin_report(db: Session, *, profile_limit: int = 150) -> Dict[str, object]:
    youtube_profiles = build_dataset_profiles(db, source_prefix="youtube", limit=profile_limit)
    google_profiles = build_dataset_profiles(db, source_prefix="google", limit=profile_limit)
    tiktok_profiles = build_dataset_profiles(db, source_prefix="tiktok", limit=profile_limit)

    production_query = production_transcript_query(db)
    total_datasets = production_query.count()
    with_duration = production_query.filter(
        DatasetContent.is_duration_recommendation_eligible.is_(True)
    ).count()
    youtube_count = production_transcript_query(db).filter(
        DatasetContent.source_platform.like("youtube%")
    ).count()
    google_count = production_transcript_query(db).filter(
        DatasetContent.source_platform.like("google%")
    ).count()
    tiktok_count = production_transcript_query(db).filter(
        DatasetContent.source_platform.like("tiktok%")
    ).count()

    recent_sources = (
        production_transcript_query(db)
        .with_entities(DatasetContent.source_platform)
        .order_by(DatasetContent.created_at.desc())
        .limit(50)
        .all()
    )
    recent_source_counts: Dict[str, int] = defaultdict(int)
    for (source_platform,) in recent_sources:
        recent_source_counts[source_platform or "unknown"] += 1

    return {
        "dataset_health": {
            "total_dataset_contents": total_datasets,
            "youtube_dataset_contents": youtube_count,
            "google_dataset_contents": google_count,
            "tiktok_dataset_contents": tiktok_count,
            "duration_coverage_count": with_duration,
            "duration_coverage_ratio": round((with_duration / total_datasets), 3) if total_datasets else 0.0,
        },
        "profile_health": {
            "youtube_profiles": len(youtube_profiles),
            "google_profiles": len(google_profiles),
            "tiktok_profiles": len(tiktok_profiles),
            "youtube_domains": [profile["domain"] for profile in youtube_profiles],
            "google_domains": [profile["domain"] for profile in google_profiles],
            "tiktok_domains": [profile["domain"] for profile in tiktok_profiles],
        },
        "recent_source_activity": [
            {"source_platform": key, "count": value}
            for key, value in sorted(recent_source_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "youtube_profiles": youtube_profiles,
        "google_profiles": google_profiles,
        "tiktok_profiles": tiktok_profiles,
    }
