"""Offline evaluation checks. Structural checks are not human usefulness scores."""
from __future__ import annotations

import hashlib
import itertools
import json
import random
import re
import statistics
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from types import SimpleNamespace


LABELS = ("phone", "camera", "laptop", "unknown")
REVIEW_FIELDS = ("relevant", "not_already_covered", "evidence_correct", "actionable")
PROTOCOL_SCHEMA_VERSION = "recommendation-utility-protocol-v2"
MANIFEST_SCHEMA_VERSION = "recommendation-utility-manifest-v1"
REVIEW_SCHEMA_VERSION = "recommendation-utility-review-v2"
VARIANT_IDS = ("A", "B", "C")
VARIANT_ORDERS = tuple("".join(row) for row in itertools.permutations(VARIANT_IDS))
UTILITY_SCORE_FIELDS = ("relevance", "novelty", "clarity", "actionability")
EVIDENCE_SCORE_FIELD = "evidence_correctness"
ABSTENTION_SCORE_FIELD = "abstention_appropriateness"
CRITICAL_FLAGS = (
    "wrong_category",
    "duplicated_topic",
    "fabricated_quote_or_time",
    "incorrect_count",
    "unsupported_spec",
    "causal_engagement_claim",
    "test_data_leakage",
)
RUBRIC_ANCHORS = {
    "relevance": ["ผิดสินค้า/ผิดบริบท", "เกี่ยวบางส่วน ยังทั่วไป", "ตรงคลิปและเงื่อนไขสินค้า"],
    "novelty": ["ส่วนใหญ่พูดแล้ว", "มีทั้งใหม่และซ้ำ", "เป็นประเด็นเพิ่มที่ยังไม่พบจริง"],
    "clarity": ["อ่านแล้วไม่รู้ความหมาย", "เข้าใจแต่ต้องถามเพิ่ม", "เข้าใจได้ด้วยตนเอง"],
    "actionability": ["ไม่รู้ว่าจะปรับอะไร", "รู้เรื่องที่จะเพิ่มแต่ขั้นตอนไม่ชัด", "บอกได้ว่าจะปรับตรงไหนและทำอย่างไร"],
    "evidence_correctness": ["แหล่ง/ข้อความ/ตัวเลขผิด", "ตรวจได้บางส่วน ข้อจำกัดไม่ชัด", "ตรวจย้อนกลับได้และข้อสรุปไม่เกินข้อมูล"],
    "abstention_appropriateness": ["ควรแนะนำแต่ระบบงด", "ยังไม่แน่ใจว่าควรงด", "งดได้เหมาะสมกับคลิปและหลักฐาน"],
}
IN_SCOPE_LABELS = ("phone", "camera", "laptop")
PILOT_SCENARIOS = {
    "phone": ("general_review", "camera_focus", "gaming_focus"),
    "camera": ("dedicated_camera", "video_focus", "phone_camera_confusion"),
    "laptop": ("general_productivity", "gaming_laptop", "confusion_hard_case"),
    "unknown": ("accessory", "non_it"),
}


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     default=str).encode("utf-8")).hexdigest()


def normalized_transcript(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text).casefold())


def diagnose_transcript_pair(asr_text: str, review: dict, classify) -> dict:
    """Compare unchanged ASR with an audio-verified transcript, never guessed corrections."""
    asr = classify(asr_text)
    result = {"asr_prediction": asr, "verified_transcript_prediction": None,
              "diagnosis": "awaiting_audio_verified_transcript", "is_new_test": False}
    if (not review.get("transcript_reviewed_by") or not review.get("listened_to_audio")
            or not str(review.get("verified_transcript") or "").strip()
            or review.get("expected_label") not in LABELS or not review.get("label_reviewed_by")):
        return result
    verified = classify(str(review["verified_transcript"]))
    gold = review["expected_label"]
    asr_label = asr.get("taxonomy_leaf_key")
    verified_label = verified.get("taxonomy_leaf_key")
    if asr.get("acceptance", {}).get("reason") == "scope_validation_unavailable":
        diagnosis = "scope_not_validated_cannot_attribute_error"
    elif verified_label != gold:
        diagnosis = "classification_error_remains_on_verified_text"
    elif asr_label != gold:
        diagnosis = "prediction_sensitive_to_transcription"
    else:
        diagnosis = "no_classification_error_in_this_pair"
    result.update(verified_transcript_prediction=verified, diagnosis=diagnosis,
                  transcript_changed=normalized_transcript(asr_text) != normalized_transcript(review["verified_transcript"]))
    return result


def overlap_audit(case: dict, transcript: str, pool: list[dict]) -> list[dict]:
    """Identity matches block scoring; long character overlaps require human review."""
    text = normalized_transcript(transcript)
    grams = {text[i:i + 12] for i in range(max(0, len(text) - 11))}
    matches = []
    for row in pool:
        reasons = []
        for key in ("source_youtube_id", "source_channel_id", "creator_group_key"):
            if case.get(key) and case[key] == row.get(key):
                reasons.append(key)
        other = normalized_transcript(str(row.get("transcript") or ""))
        if text and text == other:
            reasons.append("exact_transcript")
        elif len(text) >= 200 and len(other) >= 200:
            other_grams = {other[i:i + 12] for i in range(len(other) - 11)}
            containment = len(grams & other_grams) / max(1, min(len(grams), len(other_grams)))
            if containment >= 0.8:
                reasons.append("near_transcript_requires_review")
        if reasons:
            matches.append({"dataset_id": row.get("dataset_id"),
                            "pool": row.get("evaluation_pool"), "reasons": reasons})
    return matches


def scoring_exclusions(case: dict, overlaps: list[dict], *, duplicate: bool = False,
                       speech_ok: bool = True) -> list[str]:
    reasons = []
    if case.get("role") != "heldout":
        reasons.append("regression_not_new_holdout")
    if case.get("expected_label") not in LABELS or not case.get("label_reviewed_by"):
        reasons.append("human_label_missing")
    if not case.get("independence_confirmed_by"):
        reasons.append("independence_not_confirmed")
    if case.get("source_kind") == "self_recorded":
        if not case.get("provenance_note"):
            reasons.append("recording_provenance_missing")
    elif not case.get("source_youtube_id") or not case.get("source_channel_id"):
        reasons.append("source_identity_missing")
    if duplicate:
        reasons.append("duplicate_media")
    if not speech_ok:
        reasons.append("no_speech_transcript")
    if overlaps:
        reasons.append("training_or_reference_overlap")
    return reasons


def classification_metrics(rows: list[dict]) -> dict:
    """Macro F1 is over represented gold classes; abstention remains an error."""
    from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support
    eligible = [r for r in rows if not r.get("exclusions") and r.get("expected_label") in LABELS]
    failed = [r for r in rows if r.get("error")]
    # A partial run must not look more accurate by silently dropping failed jobs.
    if failed:
        return {"sample_size": len(eligible), "accuracy": None, "macro_f1": None,
                "unknown_recall": None, "per_class": [], "confusion_matrix": None,
                "status": "incomplete_run", "failed_case_count": len(failed)}
    if not eligible:
        return {"sample_size": 0, "accuracy": None, "macro_f1": None,
                "unknown_recall": None, "per_class": [], "confusion_matrix": None}
    gold = [r["expected_label"] for r in eligible]
    predicted = [r["predicted_label"] for r in eligible]
    precision, recall, f1, support = precision_recall_fscore_support(
        gold, predicted, labels=list(LABELS), zero_division=0)
    represented = [i for i, count in enumerate(support) if count]
    unknown_index = LABELS.index("unknown")
    return {"sample_size": len(gold), "accuracy": float(accuracy_score(gold, predicted)),
            "macro_f1": float(sum(f1[i] for i in represented) / len(represented)),
            "macro_f1_labels": [LABELS[i] for i in represented],
            "unknown_recall": float(recall[unknown_index]) if support[unknown_index] else None,
            "unknown_prediction_count": predicted.count("unknown"),
            "per_class": [{"label": label, "support": int(support[i]),
                           "precision": float(precision[i]) if support[i] else None,
                           "recall": float(recall[i]) if support[i] else None,
                           "f1": float(f1[i]) if support[i] else None}
                          for i, label in enumerate(LABELS)],
            "confusion_labels": list(LABELS),
            "confusion_matrix": confusion_matrix(gold, predicted, labels=list(LABELS)).tolist()}


def audit_recommendation(result: dict, reference_rows: list[dict]) -> list[dict]:
    from app.services.recommendation import (
        _dataset_keyword_occurrences, _keyword_identity, recommendation_domain_for_taxonomy_leaf,
    )
    recommendation = result.get("recommendation", {})
    domain = recommendation.get("domain", "unknown")
    keyword_domain = recommendation_domain_for_taxonomy_leaf(domain)
    transcript = result.get("cleaned_transcript") or result.get("transcript") or ""
    observed = _dataset_keyword_occurrences(SimpleNamespace(transcript=transcript), domain=keyword_domain)
    normalized_text = normalized_transcript(transcript)
    refs = {int(r["dataset_id"]): r for r in reference_rows}
    occurrences = {}
    checks = []
    for lane in ("missing_keywords", "hook_keywords"):
        seen = set()
        for index, item in enumerate(recommendation.get(lane, [])):
            keyword = item["keyword"]
            identity = _keyword_identity(keyword, keyword_domain)
            reasons = []
            if identity in observed or normalized_transcript(keyword) in normalized_text:
                reasons.append("already_mentioned_or_synonym")
            if identity in seen:
                reasons.append("duplicate_suggestion")
            seen.add(identity)
            ids = item.get("supporting_dataset_row_ids") or []
            if not ids:
                reasons.append("no_dataset_evidence")
            if len(ids) != len(set(ids)) or item.get("support_count", 0) != len(set(ids)):
                reasons.append("invalid_support_count")
            frequency = 0
            for dataset_id in ids:
                row = refs.get(dataset_id)
                if row is None or row.get("taxonomy_leaf_key") != domain or row.get("data_split") != "train":
                    reasons.append("invalid_reference_row")
                    continue
                if dataset_id not in occurrences:
                    occurrences[dataset_id] = _dataset_keyword_occurrences(
                        SimpleNamespace(transcript=row["transcript"]), domain=keyword_domain)
                occurrence = occurrences[dataset_id].get(identity)
                if not occurrence:
                    reasons.append("term_not_found_in_cited_transcript")
                else:
                    frequency += occurrence["frequency"]
            if ids and frequency != item.get("total_frequency"):
                reasons.append("invalid_total_frequency")
            for example in item.get("supporting_examples", []):
                row = refs.get(example.get("dataset_id"))
                if not row or example.get("dataset_id") not in ids:
                    reasons.append("example_not_in_support")
                elif any(str(example.get(key) or "") != str(row.get(key) or "") for key in (
                        "video_url", "source_channel_id", "published_at", "statistics_captured_at")):
                    reasons.append("example_provenance_mismatch")
            if domain == "unknown":
                reasons.append("unknown_should_abstain")
            checks.append({"lane": lane, "index": index, "keyword": keyword,
                           "structural_issues": sorted(set(reasons)),
                           "human_review": "pending"})
    return checks


def structural_summary(cases: list[dict]) -> dict:
    checks = [check for case in cases for check in case.get("recommendation_checks", [])]
    return {"suggestion_count": len(checks),
            "suggestions_with_issues": sum(bool(c["structural_issues"]) for c in checks),
            "issues": dict(Counter(issue for c in checks for issue in c["structural_issues"])),
            "human_usefulness": "not_evaluated", "engagement_effect": "not_measured"}


def human_review_summary(reviews: list[dict], expected: list[dict]) -> dict:
    keys = {(r["case_id"], r["output_sha256"], r["lane"], r["index"]): r for r in expected}
    accepted = {}
    rejected = 0
    for review in reviews:
        key = tuple(str(review.get(k, "")) for k in ("case_id", "output_sha256", "lane", "index"))
        if key not in keys or key in accepted or not str(review.get("reviewer", "")).strip() or any(
                str(review.get(field, "")) not in {"0", "1"} for field in REVIEW_FIELDS):
            rejected += 1
            continue
        accepted[key] = review
    n = len(accepted)
    return {"reviewed": n, "reviewed_case_count": len({key[0] for key in accepted}),
            "pending": len(keys) - n, "rejected_rows": rejected,
            "scope": "reviewed suggestions only; includes regression clips, not a generalization estimate",
            "pass_rates": {field: sum(int(r[field]) for r in accepted.values()) / n if n else None
                           for field in REVIEW_FIELDS}, "engagement_effect": "not_measured"}


def _nonempty(value) -> bool:
    return bool(str(value or "").strip())


def build_identity_registry(records: list[dict]) -> dict:
    """Index prior uses without inferring identity from filenames."""
    registry = {"media_sha256": {}, "source_youtube_id": {},
                "source_channel_id": {}, "creator_group_key": {}}
    for record in records:
        source = str(record.get("registry_source") or record.get("case_id") or "prior_use")
        for key in registry:
            value = str(record.get(key) or "").strip()
            if value:
                registry[key].setdefault(value, []).append(source)
    return registry


def audit_study_manifest(manifest: dict, *, prior_records: list[dict] | None = None) -> dict:
    """Validate declared provenance and mark reuse; hashes alone never prove independence."""
    cases = manifest.get("cases") if isinstance(manifest, dict) else None
    if not isinstance(cases, list):
        raise ValueError("Manifest must contain a cases list")
    registry = build_identity_registry(prior_records or [])
    ids = set()
    current = {key: {} for key in registry}
    audited = []
    for raw in cases:
        case = dict(raw) if isinstance(raw, dict) else {}
        case_id = str(case.get("case_id") or "")
        issues = []
        if not re.fullmatch(r"[A-Za-z0-9_-]{3,80}", case_id) or case_id in ids:
            issues.append("invalid_or_duplicate_case_id")
        ids.add(case_id)
        if not re.fullmatch(r"[0-9a-f]{64}", str(case.get("media_sha256") or "")):
            issues.append("invalid_media_sha256")
        if case.get("role") not in {"heldout", "regression", "development"}:
            issues.append("invalid_role")
        if case.get("role") != "heldout":
            issues.append("not_fresh_heldout")
        if case.get("expected_label") not in LABELS or not _nonempty(case.get("label_reviewed_by")):
            issues.append("human_gold_label_missing")
        expected_scenarios = PILOT_SCENARIOS.get(case.get("expected_label"), ())
        if case.get("scenario_kind") not in expected_scenarios:
            issues.append("scenario_kind_missing_or_invalid")
        if not _nonempty(case.get("registered_at")):
            issues.append("registration_time_missing")
        else:
            try:
                registered = datetime.fromisoformat(str(case["registered_at"]).replace("Z", "+00:00"))
                if registered.tzinfo is None:
                    issues.append("registration_timezone_missing")
            except ValueError:
                issues.append("invalid_registration_time")
        if case.get("consent_status") not in {"granted", "public_research_allowed"}:
            issues.append("consent_not_confirmed")
        if not _nonempty(case.get("independence_confirmed_by")):
            issues.append("independence_unconfirmed")
        source_kind = str(case.get("source_kind") or "")
        if source_kind == "self_recorded":
            if not _nonempty(case.get("creator_group_key")) or not _nonempty(case.get("provenance_note")):
                issues.append("self_recording_provenance_missing")
        elif source_kind == "public_video":
            if not _nonempty(case.get("source_youtube_id")) or not _nonempty(case.get("source_channel_id")):
                issues.append("public_source_identity_missing")
        else:
            issues.append("source_kind_unverified")

        identity_matches = []
        for key in registry:
            value = str(case.get(key) or "").strip()
            if not value:
                continue
            if value in registry[key]:
                reason = {
                    "media_sha256": "previously_used_media",
                    "source_youtube_id": "previously_used_video",
                    "source_channel_id": "development_channel_overlap",
                    "creator_group_key": "development_creator_overlap",
                }[key]
                issues.append(reason)
                identity_matches.append({"field": key, "value": value,
                                         "prior_sources": registry[key][value]})
            if value in current[key] and key in {"media_sha256", "source_youtube_id"}:
                issues.append(f"duplicate_{key}")
                identity_matches.append({"field": key, "value": value,
                                         "current_case_id": current[key][value]})
            current[key].setdefault(value, case_id)
        issues = sorted(set(issues))
        audited.append({"case_id": case_id, "spec": case,
                        "identity_matches": identity_matches,
                        "exclusions": issues, "fresh_heldout_eligible": not issues})

    eligible_counts = {label: sum(
        row["fresh_heldout_eligible"] and row["spec"].get("expected_label") == label
        for row in audited) for label in LABELS}
    scenario_coverage = {label: sorted({
        row["spec"].get("scenario_kind") for row in audited
        if row["fresh_heldout_eligible"] and row["spec"].get("expected_label") == label
    }) for label in LABELS}
    self_recorded_counts = {label: sum(
        row["fresh_heldout_eligible"] and row["spec"].get("expected_label") == label and
        row["spec"].get("source_kind") == "self_recorded"
        for row in audited) for label in IN_SCOPE_LABELS}
    diversity_complete = (
        all(set(PILOT_SCENARIOS[label]).issubset(scenario_coverage[label])
            for label in IN_SCOPE_LABELS) and
        set(PILOT_SCENARIOS["unknown"]).issubset(scenario_coverage["unknown"]) and
        all(self_recorded_counts[label] >= 1 for label in IN_SCOPE_LABELS)
    )
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_sha256": digest(manifest),
        "cases": audited,
        "eligible_counts": eligible_counts,
        "scenario_coverage": scenario_coverage,
        "self_recorded_counts": self_recorded_counts,
        "diversity_complete": diversity_complete,
        "eligible_case_count": sum(row["fresh_heldout_eligible"] for row in audited),
        "pilot_minimum": {"phone": 3, "camera": 3, "laptop": 3, "unknown": 3,
                          "total": 12, "reviewers": 3},
        "pilot_manifest_complete": (
            all(eligible_counts[label] >= 3 for label in LABELS) and diversity_complete
        ),
    }


def freeze_utility_protocol(*, study_id: str, manifest_sha256: str, context_lock: dict,
                            reviewer_ids: list[str], seed: int = 260930,
                            created_at: str | None = None) -> dict:
    reviewers = sorted({str(item).strip() for item in reviewer_ids if str(item).strip()})
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,80}", study_id):
        raise ValueError("Study ID must be a safe stable identifier")
    if any(not re.fullmatch(r"[A-Za-z0-9_-]{2,40}", item) for item in reviewers):
        raise ValueError("Reviewer IDs must be anonymous safe identifiers")
    protocol = {
        "schema_version": PROTOCOL_SCHEMA_VERSION,
        "protocol_version": 2,
        "study_id": study_id,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "seed": int(seed),
        "manifest_sha256": manifest_sha256,
        "reviewer_ids": reviewers,
        "pilot": {
            "minimum_cases": 12,
            "minimum_per_gold_class": 3,
            "minimum_reviewers": 3,
            "scenario_kinds": PILOT_SCENARIOS,
            "minimum_self_recorded_per_in_scope_class": 1,
            "role": "pilot",
            "stop_plan": "register at least three eligible cases per gold class, then freeze before prediction",
            "inclusion": "consented, labeled, independence-reviewed heldout video within upload limit",
            "exclusion": "prior use, identity/development overlap, transcript overlap, missing provenance or failed analysis",
        },
        "context_lock": context_lock,
        "variants": {
            "A": "ชื่อหัวข้อภาษาไทยเท่านั้น",
            "B": "หัวข้อเดียวกับ A พร้อมสิ่งที่พบ สิ่งที่เสนอ เงื่อนไข วิธีทำ และตัวอย่าง",
            "C": "เนื้อหา B เดิม พร้อมเหตุผล หลักฐาน ที่มา เวลา และข้อจำกัด",
        },
        "allocation": {"orders": list(VARIANT_ORDERS), "balanced_by": ["case_id", "reviewer_id"]},
        "limitations": ["carryover: reviewers may remember earlier presentations",
                        "partial blinding: evidence makes presentation C recognizable"],
        "rubric": {"scale": "1-5", "higher_is_better": True,
                   "utility_fields": list(UTILITY_SCORE_FIELDS),
                   "evidence_field": EVIDENCE_SCORE_FIELD,
                   "critical_flags": list(CRITICAL_FLAGS),
                   "low_score_reason_required_at_or_below": 2,
                   "evidence_for_A_B": "N/A", "anchors_1_3_5": RUBRIC_ANCHORS,
                   "intermediate_scores": "2 และ 4 คือระดับระหว่างตัวอย่างข้างเคียง"},
        "primary_metrics": {
            "unit": "clip after aggregating reviewers",
            "actionability_B_minus_A_median_min": 0.5,
            "actionability_C_minus_B_median_min": 0.0,
            "C_evidence_correctness_median_min": 4.0,
            "C_relevance_novelty_clarity_median_min": 4.0,
            "confirmed_critical_flags_max": 0,
            "minimum_complete_primary_clips": 6,
            "minimum_complete_reviewers": 3,
            "classification": {"in_scope_accuracy_min": 0.8,
                               "in_scope_macro_f1_min": 0.75,
                               "analysis_failures_max": 0,
                               "unknown_false_acceptance_max": 0},
        },
        "missing_data": {
            "scores": "missing_not_zero",
            "empty_primary_advice": "human-confirmed missed_opportunity requires actionability=1",
            "failed_job": "failure_not_unknown_rejection",
            "N_A": "not_scored",
            "duplicate_rating": "reject",
            "stale_hash": "reject",
        },
        "critical_error_policy": "reported flags require adjudication before final status",
        "claims_not_measured": ["causal_engagement_gain", "future_views", "future_likes", "future_comments"],
    }
    protocol["protocol_sha256"] = digest(protocol)
    return protocol


def verify_utility_protocol(protocol: dict) -> bool:
    claimed = str(protocol.get("protocol_sha256") or "")
    payload = dict(protocol)
    payload.pop("protocol_sha256", None)
    return bool(claimed) and claimed == digest(payload)


def build_presentation_variants(result: dict) -> dict:
    """Build presentation-only variants from one frozen recommendation snapshot."""
    recommendation = result.get("recommendation") or result
    actionable = recommendation.get("actionable_recommendations") or {}
    items = [row for row in actionable.get("items", []) if isinstance(row, dict)]
    bundle = recommendation.get("evidence_bundle") or {}
    comparisons = {str(row.get("evidence_topic_id")): row
                   for row in (bundle.get("topic_comparisons") or {}).get("items", [])
                   if isinstance(row, dict)}
    topics = {str(row.get("topic_id")): row for row in bundle.get("action_topics", [])
              if isinstance(row, dict)}
    documents = {row.get("dataset_id"): row for row in bundle.get("reference_documents", [])
                 if isinstance(row, dict)}
    variants = {key: {"variant_id": key, "items": [], "recommendation_status": actionable.get("status")}
                for key in VARIANT_IDS}
    action_fields = ("finding", "proposal", "condition", "steps", "example")
    for order, item in enumerate(items, 1):
        unit_id = str(item.get("id") or digest([item.get("title"), order])[:24])
        base = {"unit_id": unit_id, "order": order,
                "evidence_topic_id": item.get("evidence_topic_id"),
                "title": str(item.get("title") or item.get("template_key") or "")}
        action = {field: item.get(field) for field in action_fields}
        variants["A"]["items"].append(dict(base))
        variants["B"]["items"].append({**base, "action": action})
        topic_id = str(item.get("evidence_topic_id") or "")
        topic = topics.get(topic_id, {})
        support_rows = []
        for dataset_id in item.get("supporting_dataset_row_ids", [])[:5]:
            doc = documents.get(dataset_id, {})
            references = [row for row in topic.get("references", [])
                          if row.get("dataset_id") == dataset_id]
            support_rows.append({
                "dataset_id": dataset_id,
                "video_id": doc.get("video_id"),
                "channel_id": doc.get("channel_id"),
                "title": doc.get("title"), "url": doc.get("url"),
                "statistics": doc.get("statistics"),
                "published_at": doc.get("published_at"),
                "statistics_captured_at": doc.get("statistics_captured_at"),
                "occurrences": (references[0].get("occurrences", [])[:2] if references else []),
            })
        variants["C"]["items"].append({
            **base,
            "action": action,
            "evidence": {
                "reason": item.get("reason"),
                "relevance_reason": item.get("relevance_reason"),
                "support_count": item.get("support_count"),
                "channel_count": item.get("channel_count"),
                "sample_size": item.get("sample_size"),
                "references": support_rows,
                "topic_comparison": {key: value for key, value in comparisons.get(topic_id, {}).items()
                                     if key not in {"records", "reference_documents"}},
                "limitation": actionable.get("limitation"),
                "causal_engagement_claim": False,
            },
        })
    for variant in variants.values():
        variant["item_count"] = len(variant["items"])
        variant["output_sha256"] = digest(variant)
    assert_variant_parity(variants)
    return variants


def assert_variant_parity(variants: dict) -> None:
    rows = {key: variants.get(key, {}).get("items", []) for key in VARIANT_IDS}
    identity = lambda row: (row.get("unit_id"), row.get("order"), row.get("title"),
                            row.get("evidence_topic_id"))
    baseline = [identity(row) for row in rows["A"]]
    if any([identity(row) for row in rows[key]] != baseline for key in ("B", "C")):
        raise ValueError("A/B/C must contain identical topics in identical order")
    for left, right in zip(rows["B"], rows["C"]):
        if left.get("action") != right.get("action"):
            raise ValueError("B/C actionable content must be identical")


def allocate_variant_orders(*, study_id: str, protocol_sha256: str,
                            case_ids: list[str], reviewer_ids: list[str], seed: int) -> list[dict]:
    cases = sorted(set(case_ids))
    reviewers = sorted(set(reviewer_ids))
    rng = random.Random(int(seed))
    rng.shuffle(cases)
    rng.shuffle(reviewers)
    symbols = list(VARIANT_IDS)
    rng.shuffle(symbols)
    forward, reverse = "".join(symbols), "".join(reversed(symbols))
    orders = [word[i:] + word[:i] for word in (forward, reverse) for i in range(3)]
    # Latin rotations balance positions per clip; alternate forward/reverse blocks
    # so each reviewer sees all six orders equally in the 12-clip pilot.
    pairs = [(case_id, reviewer_id, orders[((i + j // 3) % 2) * 3 + (i // 2 + j) % 3])
             for i, case_id in enumerate(cases) for j, reviewer_id in enumerate(reviewers)]
    allocations = []
    for case_id, reviewer_id, order in pairs:
        for position, variant_id in enumerate(order, 1):
            presentation_id = digest([study_id, protocol_sha256, case_id, reviewer_id,
                                      position, variant_id])[:20]
            allocations.append({"case_id": case_id, "reviewer_id": reviewer_id,
                                "position": position, "presentation_id": presentation_id,
                                "variant_id": variant_id})
    return sorted(allocations, key=lambda row: (row["reviewer_id"], row["case_id"], row["position"]))


def allocation_balance(allocations: list[dict]) -> dict:
    first = Counter(row["variant_id"] for row in allocations if row["position"] == 1)
    order_counts = Counter()
    grouped = {}
    for row in allocations:
        grouped.setdefault((row["case_id"], row["reviewer_id"]), []).append(row)
    for rows in grouped.values():
        order_counts["".join(r["variant_id"] for r in sorted(rows, key=lambda x: x["position"]))] += 1
    counts = list(order_counts.values()) or [0]
    return {"pair_count": len(grouped), "first_variant_counts": dict(first),
            "order_counts": dict(order_counts), "max_order_imbalance": max(counts) - min(counts)}


def validate_utility_responses(*, response_documents: list[dict], allocations: list[dict],
                               protocol: dict, case_outputs: dict) -> dict:
    if not verify_utility_protocol(protocol):
        raise ValueError("Protocol hash mismatch")
    mapping = {row["presentation_id"]: row for row in allocations}
    planned_reviewers = set(protocol.get("reviewer_ids") or [])
    accepted_ratings, accepted_pre, rejected = [], [], []
    rating_keys, pre_keys = set(), set()
    for document in response_documents:
        if not isinstance(document, dict):
            rejected.append({"reason": "invalid_response_document"})
            continue
        reviewer = str(document.get("reviewer_id") or "")
        base_error = None
        if document.get("schema_version") != REVIEW_SCHEMA_VERSION:
            base_error = "review_schema_mismatch"
        elif document.get("study_id") != protocol.get("study_id"):
            base_error = "study_id_mismatch"
        elif document.get("protocol_sha256") != protocol.get("protocol_sha256"):
            base_error = "stale_protocol_hash"
        elif reviewer not in planned_reviewers:
            base_error = "reviewer_not_in_protocol"
        elif document.get("consent") is not True:
            base_error = "reviewer_consent_missing"
        elif not isinstance(document.get("pre_reviews", []), list) or not isinstance(document.get("ratings", []), list):
            base_error = "invalid_response_rows"
        if base_error:
            rejected.append({"reviewer_id": reviewer, "reason": base_error})
            continue
        for row in document.get("pre_reviews", []):
            if not isinstance(row, dict):
                rejected.append({"reviewer_id": reviewer, "reason": "invalid_pre_review"})
                continue
            case_id = str(row.get("case_id") or "")
            key = (reviewer, case_id)
            if (key in pre_keys or case_id not in case_outputs or
                    not any(a["case_id"] == case_id and a["reviewer_id"] == reviewer for a in allocations) or
                    row.get("watched_video") is not True or not _nonempty(row.get("notes")) or
                    row.get("improvement_opportunity") not in {"yes", "no", "unclear"}):
                rejected.append({"reviewer_id": reviewer, "case_id": case_id,
                                 "reason": "invalid_or_duplicate_pre_review"})
                continue
            pre_keys.add(key)
            accepted_pre.append({**row, "reviewer_id": reviewer})
        for row in document.get("ratings", []):
            if not isinstance(row, dict):
                rejected.append({"reviewer_id": reviewer, "reason": "invalid_rating"})
                continue
            presentation_id = str(row.get("presentation_id") or "")
            allocation = mapping.get(presentation_id)
            reason = None
            if allocation is None or allocation["reviewer_id"] != reviewer:
                reason = "presentation_not_allocated"
            else:
                case_id = allocation["case_id"]
                variant_id = allocation["variant_id"]
                expected = case_outputs.get(case_id, {}).get("variants", {}).get(variant_id, {})
                unit_id = allocation.get("unit_id") or f"{case_id}:{variant_id}:set"
                key = (protocol["study_id"], protocol["protocol_sha256"], case_id,
                       expected.get("output_sha256"), variant_id, reviewer, unit_id)
                if key in rating_keys:
                    reason = "duplicate_rating"
                elif (reviewer, case_id) not in pre_keys:
                    reason = "pre_review_required"
                elif case_outputs[case_id].get("analysis_status") not in {None, "completed"} or case_outputs[case_id].get("exclusions"):
                    reason = "case_not_reviewable"
                elif expected.get("output_sha256") != digest({k: v for k, v in expected.items() if k != "output_sha256"}):
                    reason = "output_integrity_mismatch"
                elif row.get("case_id") != case_id or row.get("unit_id") != unit_id:
                    reason = "rating_key_mismatch"
                elif row.get("output_sha256") != expected.get("output_sha256"):
                    reason = "stale_output_hash"
                scores = row.get("scores") if isinstance(row.get("scores"), dict) else {}
                empty = int(expected.get("item_count") or 0) == 0
                missed = row.get("missed_opportunity") is True
                required = [] if empty and not missed else list(UTILITY_SCORE_FIELDS)
                if empty and missed:
                    required = ["actionability"]
                for field in required:
                    if type(scores.get(field)) is not int or not 1 <= scores[field] <= 5:
                        reason = reason or f"invalid_score_{field}"
                evidence = scores.get(EVIDENCE_SCORE_FIELD)
                if variant_id == "C" and not empty:
                    if type(evidence) is not int or not 1 <= evidence <= 5:
                        reason = reason or "invalid_score_evidence_correctness"
                elif evidence not in (None, "", "N/A"):
                    reason = reason or "evidence_score_must_be_N_A"
                abstention = scores.get(ABSTENTION_SCORE_FIELD)
                if empty and not missed:
                    if type(abstention) is not int or not 1 <= abstention <= 5:
                        reason = reason or "invalid_abstention_score"
                elif abstention not in (None, "", "N/A"):
                    reason = reason or "abstention_score_not_applicable"
                numeric = [value for value in scores.values() if isinstance(value, int)]
                if any(value <= 2 for value in numeric) and not _nonempty(row.get("low_score_reason")):
                    reason = reason or "low_score_reason_missing"
                if empty and missed and scores.get("actionability") != 1:
                    reason = reason or "missed_opportunity_actionability_must_be_1"
                if missed and not empty:
                    reason = reason or "missed_opportunity_requires_empty_advice"
                allowed = set(required) | {EVIDENCE_SCORE_FIELD, ABSTENTION_SCORE_FIELD}
                if any(field not in allowed and value not in (None, "", "N/A") for field, value in scores.items()):
                    reason = reason or "unexpected_score_field"
                flags = row.get("critical_flags") or []
                if not isinstance(flags, list) or any(flag not in CRITICAL_FLAGS for flag in flags):
                    reason = reason or "invalid_critical_flag"
            if reason:
                rejected.append({"reviewer_id": reviewer, "presentation_id": presentation_id,
                                 "reason": reason})
                continue
            rating_keys.add(key)
            accepted_ratings.append({**row, "reviewer_id": reviewer, "case_id": case_id,
                                     "variant_id": variant_id, "unit_id": unit_id,
                                     "output_sha256": expected.get("output_sha256")})
    return {"schema_version": REVIEW_SCHEMA_VERSION, "ratings": accepted_ratings,
            "pre_reviews": accepted_pre, "rejected": rejected,
            "accepted_rating_count": len(accepted_ratings),
            "accepted_reviewer_count": len({row["reviewer_id"] for row in accepted_ratings})}


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    fraction = position - low
    return ordered[low] + (ordered[high] - ordered[low]) * fraction


def _distribution(values: list[float]) -> dict:
    return {"count": len(values), "median": statistics.median(values) if values else None,
            "p25": _percentile(values, 0.25), "p75": _percentile(values, 0.75)}


def pilot_classification_metrics(rows: list[dict]) -> dict:
    eligible = [row for row in rows if row.get("role") == "heldout" and
                row.get("expected_label") in LABELS and row.get("manifest_eligible", True) and
                not any(reason in {"training_or_reference_overlap", "duplicate_media"}
                        for reason in row.get("exclusions", []))]
    failures = [row for row in eligible if row.get("error") or not row.get("predicted_label") or
                "no_speech_transcript" in row.get("exclusions", [])]
    successful = [row for row in eligible if row not in failures]
    matrix_labels = [*LABELS, "error"]
    matrix = [[0 for _ in matrix_labels] for _ in LABELS]
    for row in eligible:
        gold = LABELS.index(row["expected_label"])
        predicted = "error" if row in failures else row.get("predicted_label", "error")
        if predicted not in matrix_labels:
            predicted = "error"
        matrix[gold][matrix_labels.index(predicted)] += 1
    per_class = []
    for label in LABELS:
        support = sum(row.get("expected_label") == label for row in eligible)
        tp = sum(row.get("expected_label") == label and row.get("predicted_label") == label
                 and row not in failures for row in eligible)
        fp = sum(row.get("expected_label") != label and row.get("predicted_label") == label
                 and row not in failures for row in eligible)
        precision = tp / (tp + fp) if tp + fp else (0.0 if support else None)
        recall = tp / support if support else None
        f1 = (2 * precision * recall / (precision + recall)
              if support and precision + recall else (0.0 if support else None))
        per_class.append({"label": label, "support": support, "precision": precision,
                          "recall": recall, "f1": f1})
    in_scope = [row for row in eligible if row["expected_label"] in IN_SCOPE_LABELS]
    unknown = [row for row in eligible if row["expected_label"] == "unknown"]
    correct = sum(row.get("predicted_label") == row.get("expected_label") and row not in failures
                  for row in eligible)
    in_scope_correct = sum(row.get("predicted_label") == row.get("expected_label") and row not in failures
                           for row in in_scope)
    represented_f1 = [row["f1"] for row in per_class if row["label"] in IN_SCOPE_LABELS and row["support"]]
    unknown_rejected = sum(row.get("predicted_label") == "unknown" and row not in failures for row in unknown)
    unknown_accepted = sum(row.get("predicted_label") in IN_SCOPE_LABELS and row not in failures for row in unknown)
    result = {
        "registered_eligible_count": len(eligible),
        "successful_count": len(successful),
        "failure_count": len(failures),
        "end_to_end_coverage": len(successful) / len(eligible) if eligible else None,
        "accuracy_successful_only": (sum(row.get("predicted_label") == row.get("expected_label")
                                         for row in successful) / len(successful) if successful else None),
        "end_to_end_accuracy": correct / len(eligible) if eligible else None,
        "in_scope_accuracy": in_scope_correct / len(in_scope) if in_scope else None,
        "in_scope_accuracy_numerator": in_scope_correct,
        "in_scope_accuracy_denominator": len(in_scope),
        "in_scope_macro_f1": statistics.mean(represented_f1) if represented_f1 else None,
        "unknown_rejection": unknown_rejected / len(unknown) if unknown else None,
        "unknown_rejection_numerator": unknown_rejected,
        "unknown_rejection_denominator": len(unknown),
        "unknown_false_acceptance": unknown_accepted / len(unknown) if unknown else None,
        "unknown_false_acceptance_numerator": unknown_accepted,
        "unknown_false_acceptance_denominator": len(unknown),
        "gold_counts": dict(Counter(row["expected_label"] for row in eligible)),
        "per_class": per_class,
        "confusion_gold_labels": list(LABELS),
        "confusion_prediction_labels": matrix_labels,
        "confusion_matrix": matrix,
        "failures_are_not_unknown_rejections": True,
    }
    pilot_complete = all(result["gold_counts"].get(label, 0) >= 3 for label in LABELS)
    result["criteria"] = {
        "pilot_complete": pilot_complete,
        "in_scope_accuracy_min": 0.8,
        "in_scope_macro_f1_min": 0.75,
        "unknown_false_acceptance_max": 0.0,
        "analysis_failures_max": 0,
    }
    if not pilot_complete:
        result["status"] = "insufficient_classification_evaluation"
    else:
        passed = bool(
            result["in_scope_accuracy"] is not None and result["in_scope_accuracy"] >= 0.8 and
            result["in_scope_macro_f1"] is not None and result["in_scope_macro_f1"] >= 0.75 and
            result["unknown_false_acceptance"] is not None and
            result["unknown_false_acceptance"] <= 0.0 and not failures
        )
        result["status"] = "pass" if passed else "fail"
    return result


def utility_metrics(*, validated: dict, case_outputs: dict,
                    adjudications: list[dict] | None = None) -> dict:
    ratings = validated.get("ratings") or []
    pre_reviews = validated.get("pre_reviews") or []
    if not ratings:
        return {"status": "not_evaluated", "reason": "no_human_scores",
                "human_utility": "not_evaluated", "engagement_effect": "not_measured"}
    pre_by_case = {}
    for row in pre_reviews:
        pre_by_case.setdefault(row["case_id"], []).append(row)
    grouped = {}
    for row in ratings:
        grouped.setdefault((row["case_id"], row["reviewer_id"]), {})[row["variant_id"]] = row
    complete_triplets = {key: rows for key, rows in grouped.items() if set(rows) == set(VARIANT_IDS)}
    abstention_by_case = {}
    for (case_id, _reviewer), rows in complete_triplets.items():
        output = case_outputs.get(case_id, {})
        for variant_id, row in rows.items():
            variant = (output.get("variants") or {}).get(variant_id, {})
            if int(variant.get("item_count") or 0) != 0:
                continue
            value = row.get("scores", {}).get(ABSTENTION_SCORE_FIELD)
            if isinstance(value, int):
                abstention_by_case.setdefault(case_id, []).append(value)
            if row.get("missed_opportunity") is True:
                abstention_by_case.setdefault(case_id, [])
    secondary_abstention = []
    for case_id, values in sorted(abstention_by_case.items()):
        rows = [row for (rated_case, _), triplet in complete_triplets.items()
                if rated_case == case_id for row in triplet.values()
                if int(((case_outputs.get(case_id, {}).get("variants") or {})
                        .get(row["variant_id"], {}).get("item_count") or 0)) == 0]
        secondary_abstention.append({
            "case_id": case_id,
            "gold_label": (case_outputs.get(case_id, {}).get("spec") or {}).get("expected_label"),
            "scores": _distribution(values),
            "missed_opportunity_count": sum(row.get("missed_opportunity") is True for row in rows),
            "rating_count": len(rows),
        })
    eligible_cases = []
    for case_id, output in case_outputs.items():
        spec = output.get("spec") or {}
        if spec.get("role") != "heldout" or spec.get("expected_label") not in IN_SCOPE_LABELS or output.get("exclusions"):
            continue
        pre = pre_by_case.get(case_id, [])
        yes = sum(row.get("improvement_opportunity") == "yes" for row in pre)
        no = sum(row.get("improvement_opportunity") == "no" for row in pre)
        if yes >= 2 and yes > no:
            eligible_cases.append(case_id)
    case_variant = {}
    reviewers = set()
    for (case_id, reviewer), rows in complete_triplets.items():
        if case_id not in eligible_cases:
            continue
        reviewers.add(reviewer)
        for variant, row in rows.items():
            case_variant.setdefault((case_id, variant), []).append(row)
    complete_cases = [case_id for case_id in eligible_cases
                      if all(len(case_variant.get((case_id, variant), [])) >= 3 for variant in VARIANT_IDS)]
    per_case = []
    abstention_cases = []
    for case_id in complete_cases:
        variants = {}
        for variant in VARIANT_IDS:
            rows = case_variant[(case_id, variant)]
            scores = {}
            for field in (*UTILITY_SCORE_FIELDS, EVIDENCE_SCORE_FIELD):
                values = [row.get("scores", {}).get(field) for row in rows]
                values = [float(value) for value in values if isinstance(value, int)]
                scores[field] = statistics.median(values) if values else None
            variants[variant] = scores
        actionability = [variants[key]["actionability"] for key in VARIANT_IDS]
        if any(value is None for value in actionability):
            abstention_values = []
            for variant in VARIANT_IDS:
                abstention_values.extend(
                    row.get("scores", {}).get(ABSTENTION_SCORE_FIELD)
                    for row in case_variant[(case_id, variant)]
                    if isinstance(row.get("scores", {}).get(ABSTENTION_SCORE_FIELD), int)
                )
            abstention_cases.append({
                "case_id": case_id,
                "reason": "empty_advice_or_non_comparable_utility_scores",
                "abstention_quality": _distribution(abstention_values),
            })
            continue
        per_case.append({"case_id": case_id, "variants": variants,
                         "B_minus_A_actionability": variants["B"]["actionability"] - variants["A"]["actionability"],
                         "C_minus_B_actionability": variants["C"]["actionability"] - variants["B"]["actionability"]})
    b_a = [row["B_minus_A_actionability"] for row in per_case]
    c_b = [row["C_minus_B_actionability"] for row in per_case]
    c_scores = {field: [row["variants"]["C"][field] for row in per_case
                        if row["variants"]["C"][field] is not None]
                for field in (*UTILITY_SCORE_FIELDS, EVIDENCE_SCORE_FIELD)}
    reported = {(row["case_id"], row.get("presentation_id"), flag)
                for row in ratings for flag in row.get("critical_flags", [])}
    decisions = {}
    for row in adjudications or []:
        key = (row.get("case_id"), row.get("presentation_id"), row.get("flag"))
        if not _nonempty(row.get("adjudicator_id")) or not _nonempty(row.get("reason")):
            continue
        if key in decisions:
            decisions[key] = "conflicting_decisions"
        else:
            decisions[key] = row.get("status")
    confirmed = sorted(key for key in reported if decisions.get(key) == "confirmed")
    unresolved = sorted(key for key in reported if decisions.get(key) not in {"confirmed", "dismissed"})
    enough = len(per_case) >= 6 and len(reviewers) >= 3
    criteria = {
        "B_minus_A_actionability": _distribution(b_a),
        "C_minus_B_actionability": _distribution(c_b),
        "C_scores": {field: _distribution(values) for field, values in c_scores.items()},
        "confirmed_critical_flag_count": len(confirmed),
    }
    thresholds_pass = bool(
        enough and not unresolved and
        criteria["B_minus_A_actionability"]["median"] >= 0.5 and
        criteria["C_minus_B_actionability"]["median"] >= 0 and
        criteria["C_scores"][EVIDENCE_SCORE_FIELD]["median"] is not None and
        criteria["C_scores"][EVIDENCE_SCORE_FIELD]["median"] >= 4 and
        all(criteria["C_scores"][field]["median"] is not None and
            criteria["C_scores"][field]["median"] >= 4
            for field in ("relevance", "novelty", "clarity")) and
        not confirmed
    )
    if unresolved:
        status = "pending_critical_flag_adjudication"
    elif not enough:
        status = "insufficient_utility_evaluation"
    else:
        status = "pass" if thresholds_pass else "fail"
    return {
        "status": status,
        "human_utility": "evaluated" if enough and not unresolved else "incomplete",
        "primary_case_count": len(per_case),
        "primary_reviewer_count": len(reviewers),
        "registered_primary_candidates": len(eligible_cases),
        "incomplete_primary_cases": [case_id for case_id in eligible_cases if case_id not in complete_cases],
        "complete_reviewers_per_case": {case_id: len(case_variant.get((case_id, "A"), []))
                                        for case_id in eligible_cases},
        "criteria": criteria,
        "paired_outcomes": {
            "B_minus_A": {"wins": sum(value > 0 for value in b_a),
                          "ties": sum(value == 0 for value in b_a),
                          "losses": sum(value < 0 for value in b_a)},
            "C_minus_B": {"wins": sum(value > 0 for value in c_b),
                          "ties": sum(value == 0 for value in c_b),
                          "losses": sum(value < 0 for value in c_b)},
        },
        "per_case": per_case,
        "abstention_cases": abstention_cases,
        "secondary_abstention": secondary_abstention,
        "confirmed_critical_flags": [list(row) for row in confirmed],
        "unresolved_critical_flags": [list(row) for row in unresolved],
        "missing_scores_are_not_zero": True,
        "engagement_effect": "not_measured",
    }
