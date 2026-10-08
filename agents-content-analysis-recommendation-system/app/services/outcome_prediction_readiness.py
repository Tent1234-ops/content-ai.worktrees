"""Read-only readiness audit and protocol gates for outcome prediction Phase 1."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.database.models import (
    ClassificationModel,
    DatasetContent,
    ReferenceStatisticsRun,
    ReferenceVideoStatistic,
)
from app.services.classification_readiness import classification_model_snapshot
from app.services.dataset_eligibility import (
    production_transcript_conditions,
    reference_transcript_rows,
)
from app.services.view_metrics import (
    YOUTUBE_PLAY_START_VIEW_V2,
    YOUTUBE_QUALIFIED_VIEW_V1,
    view_metric_version_for,
)


AUDIT_SCHEMA_VERSION = "outcome-readiness-audit-v1"
PROTOCOL_SCHEMA_VERSION = "outcome-prediction-protocol-v1"
DATA_USE_SCHEMA_VERSION = "outcome-data-use-decision-v1"
TARGET_VERSION = "reference_relative_views_v1"
TARGET_LEAVES = ("phone", "camera", "laptop")
SUCCESSFUL_OBSERVATION_STATUSES = {"complete", "partial"}
SUPPORTED_YOUTUBE_METRICS = {
    YOUTUBE_QUALIFIED_VIEW_V1,
    YOUTUBE_PLAY_START_VIEW_V2,
}
PROTECTED_SPLITS = {"validation", "test"}
WRITE_PREFIX = re.compile(
    r"^\s*(?:/\*.*?\*/\s*)*(INSERT|UPDATE|DELETE|ALTER|CREATE|DROP|TRUNCATE|REPLACE|MERGE|GRANT|REVOKE)\b",
    re.IGNORECASE | re.DOTALL,
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _as_naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _iso(value: datetime | None) -> str | None:
    value = _as_naive_utc(value)
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z") if value else None


def _transcript_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalized_text_hash(text: str) -> str | None:
    normalized = "".join(character.casefold() for character in text if character.isalnum())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else None


def _confirmed_format(row: DatasetContent) -> tuple[str, str | None]:
    """Mirror the explicit-metadata rule used by topic comparisons."""
    try:
        metadata = json.loads(row.raw_metadata_json or "{}")
    except (TypeError, ValueError):
        return "unknown", None
    if not isinstance(metadata, dict):
        return "unknown", None
    containers = [metadata]
    for key in ("raw_metadata", "video", "contentDetails"):
        if isinstance(metadata.get(key), dict):
            containers.append(metadata[key])
    for container in containers:
        for key in ("content_format", "video_format", "format"):
            raw = str(container.get(key) or "").strip().casefold().replace("-", "_")
            if raw in {"short", "shorts", "short_form", "shortform"}:
                return "short_form", f"raw_metadata.{key}"
            if raw in {"long", "long_form", "longform", "standard", "video"}:
                return "long_form", f"raw_metadata.{key}"
        raw_short = container.get("is_short")
        if isinstance(raw_short, bool):
            return ("short_form" if raw_short else "long_form"), "raw_metadata.is_short"
    return "unknown", None


def _age_bucket(published_at: datetime | None, observed_at: datetime | None) -> tuple[str, float | None]:
    published = _as_naive_utc(published_at)
    observed = _as_naive_utc(observed_at)
    if published is None or observed is None:
        return "unknown", None
    days = (observed - published).total_seconds() / 86400
    if days < 0:
        return "invalid", days
    if days < 7:
        return "age_0_7d", days
    if days < 30:
        return "age_7_30d", days
    if days < 90:
        return "age_30_90d", days
    if days < 365:
        return "age_90_365d", days
    return "age_365d_plus", days


def _counter(items: Iterable[Any]) -> dict[str, int]:
    return dict(sorted(Counter(str(item if item not in {None, ""} else "missing") for item in items).items()))


def validate_protocol(protocol: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    required = {
        "schema_version", "protocol_version", "target", "cutoff_policy", "sampling",
        "split_policy", "feature_policy", "model_policy", "evaluation", "qualification",
        "claims", "data_use", "resources", "utility_study",
    }
    for key in sorted(required - set(protocol)):
        errors.append(f"missing:{key}")
    if protocol.get("schema_version") != PROTOCOL_SCHEMA_VERSION:
        errors.append("invalid:schema_version")
    if (protocol.get("target") or {}).get("version") != TARGET_VERSION:
        errors.append("invalid:target.version")
    if (protocol.get("target") or {}).get("causal_claim") is not False:
        errors.append("invalid:target.causal_claim")
    split = protocol.get("split_policy") or {}
    if split.get("group_by") != ["source_channel_id", "creator_group_key", "source_youtube_id", "transcript_sha256"]:
        errors.append("invalid:split_policy.group_by")
    minimums = split.get("minimums") or {}
    expected_minimums = {
        "fit": {"videos": 40, "channels": 8},
        "tuning": {"videos": 30, "channels": 5},
        "calibration": {"videos": 20, "channels": 5},
        "independent_test": {"videos": 30, "channels": 10},
    }
    if minimums != expected_minimums:
        errors.append("invalid:split_policy.minimums")
    evaluation = protocol.get("evaluation") or {}
    if evaluation.get("bootstrap", {}).get("resamples") != 2000:
        errors.append("invalid:evaluation.bootstrap.resamples")
    if evaluation.get("calibration", {}).get("bins") != 3:
        errors.append("invalid:evaluation.calibration.bins")
    if (protocol.get("model_policy") or {}).get("random_seed") != 261008:
        errors.append("invalid:model_policy.random_seed")
    data_use = protocol.get("data_use") or {}
    if data_use.get("require_confirmation_for") != ["training", "serving"]:
        errors.append("invalid:data_use.require_confirmation_for")
    utility = protocol.get("utility_study") or {}
    if utility.get("minimum_real_reviewers") != 3:
        errors.append("invalid:utility_study.minimum_real_reviewers")
    canonical = {key: value for key, value in protocol.items() if key != "protocol_sha256"}
    digest = sha256_json(canonical)
    declared = protocol.get("protocol_sha256")
    if declared not in {None, "", digest}:
        errors.append("invalid:protocol_sha256")
    return {"valid": not errors, "errors": errors, "protocol_sha256": digest}


def data_use_gate(record: dict[str, Any], purpose: str) -> dict[str, Any]:
    reasons: list[str] = []
    if record.get("schema_version") != DATA_USE_SCHEMA_VERSION:
        reasons.append("data_use_schema_invalid")
    if purpose not in set(record.get("intended_uses") or []):
        reasons.append("purpose_not_registered")
    if not str(record.get("owner") or "").strip():
        reasons.append("decision_owner_missing")
    audit_only_allowed = purpose == "audit" and (record.get("decision") or {}).get("audit_allowed") is True
    if not audit_only_allowed:
        if record.get("status") != "confirmed":
            reasons.append(f"data_use_{record.get('status') or 'missing'}")
        evidence = record.get("confirmation_evidence") or []
        if not evidence:
            reasons.append("confirmation_evidence_missing")
    return {"purpose": purpose, "allowed": not reasons, "reason_codes": sorted(set(reasons))}


@contextmanager
def reject_database_writes(engine):
    """Fail immediately if an audit path attempts SQL that mutates the database."""
    def before_cursor_execute(_conn, _cursor, statement, _parameters, _context, _executemany):
        match = WRITE_PREFIX.match(str(statement or ""))
        if match:
            raise RuntimeError(f"read-only audit blocked SQL verb: {match.group(1).upper()}")

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        yield
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)


def database_identity(db: Session) -> dict[str, Any]:
    hasher = hashlib.sha256()
    tables = {
        "dataset_contents": db.query(DatasetContent).count(),
        "reference_video_statistics": db.query(ReferenceVideoStatistic).count(),
        "reference_statistics_runs": db.query(ReferenceStatisticsRun).count(),
        "classification_models": db.query(ClassificationModel).count(),
    }
    dataset_rows = db.query(
        DatasetContent.dataset_id, DatasetContent.taxonomy_leaf_key, DatasetContent.data_split,
        DatasetContent.source_youtube_id, DatasetContent.source_channel_id,
        DatasetContent.transcript_sha256, DatasetContent.is_active, DatasetContent.deleted_at,
        DatasetContent.is_training_eligible, DatasetContent.is_keyword_recommendation_eligible,
        DatasetContent.statistics_captured_at, DatasetContent.view_metric_version,
    ).order_by(DatasetContent.dataset_id)
    observation_rows = db.query(
        ReferenceVideoStatistic.observation_id, ReferenceVideoStatistic.run_id,
        ReferenceVideoStatistic.dataset_id, ReferenceVideoStatistic.video_id,
        ReferenceVideoStatistic.observed_at, ReferenceVideoStatistic.status,
        ReferenceVideoStatistic.error_code, ReferenceVideoStatistic.views,
        ReferenceVideoStatistic.likes, ReferenceVideoStatistic.comments,
        ReferenceVideoStatistic.view_metric_version,
    ).order_by(ReferenceVideoStatistic.observation_id)
    model_rows = db.query(
        ClassificationModel.model_id, ClassificationModel.model_key,
        ClassificationModel.model_version, ClassificationModel.status,
        ClassificationModel.is_active, ClassificationModel.updated_at,
    ).order_by(ClassificationModel.model_id)
    for row in list(dataset_rows) + list(observation_rows) + list(model_rows):
        hasher.update((_canonical_json(list(row)) + "\n").encode("utf-8"))
    return {"counts": tables, "identity_sha256": hasher.hexdigest()}


def scan_prior_artifact_use(repo_root: Path) -> dict[str, Any]:
    """Find explicit prior roles without interpreting local files as fresh tests."""
    by_dataset: defaultdict[int, set[str]] = defaultdict(set)
    by_video: defaultdict[str, set[str]] = defaultdict(set)
    scanned: list[str] = []
    errors: list[dict[str, str]] = []
    artifacts = repo_root / "artifacts"
    if not artifacts.exists():
        return {
            "by_dataset_id": {}, "by_video_id": {}, "files_scanned": [], "errors": [],
            "limitation": "No artifact directory was available; undocumented prior human use remains unknown.",
        }

    for path in sorted((artifacts / "classification_training").glob("**/*.jsonl")):
        split = path.stem
        if split not in {"train", "validation", "test", "out_of_scope"}:
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if isinstance(row.get("dataset_id"), int):
                    by_dataset[row["dataset_id"]].add(f"classification_{split}")
                if row.get("source_youtube_id"):
                    by_video[str(row["source_youtube_id"])].add(f"classification_{split}")
            scanned.append(str(path.relative_to(repo_root)))
        except (OSError, ValueError, TypeError) as exc:
            errors.append({"path": str(path.relative_to(repo_root)), "error": exc.__class__.__name__})

    for path in sorted((artifacts / "evaluation").glob("**/manifest*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            stack = [payload]
            while stack:
                value = stack.pop()
                if isinstance(value, dict):
                    role = str(value.get("role") or "utility_or_evaluation")
                    if isinstance(value.get("dataset_id"), int):
                        by_dataset[value["dataset_id"]].add(role)
                    if value.get("source_youtube_id"):
                        by_video[str(value["source_youtube_id"])].add(role)
                    stack.extend(value.values())
                elif isinstance(value, list):
                    stack.extend(value)
            scanned.append(str(path.relative_to(repo_root)))
        except (OSError, ValueError, TypeError) as exc:
            errors.append({"path": str(path.relative_to(repo_root)), "error": exc.__class__.__name__})
    return {
        "by_dataset_id": {str(key): sorted(value) for key, value in sorted(by_dataset.items())},
        "by_video_id": {key: sorted(value) for key, value in sorted(by_video.items())},
        "files_scanned": scanned,
        "errors": errors,
        "limitation": "Only explicit JSON/JSONL manifests are scanned; undocumented prior human use remains unknown.",
    }


def _duplicate_groups(rows: list[DatasetContent], key) -> list[dict[str, Any]]:
    grouped: defaultdict[str, list[DatasetContent]] = defaultdict(list)
    for row in rows:
        value = key(row)
        if value:
            grouped[str(value)].append(row)
    return [
        {"identity": identity, "dataset_ids": sorted(row.dataset_id for row in members),
         "splits": sorted({row.data_split for row in members})}
        for identity, members in sorted(grouped.items()) if len(members) > 1
    ]


def _latest_observation(
    observations: list[ReferenceVideoStatistic], row: DatasetContent, cutoff: datetime,
    latest_observation_hours: int,
) -> tuple[ReferenceVideoStatistic | None, list[str]]:
    reasons: list[str] = []
    before_cutoff = [item for item in observations if _as_naive_utc(item.observed_at) <= cutoff]
    matching = [item for item in before_cutoff if item.video_id == row.source_youtube_id]
    successful = [item for item in matching if item.status in SUCCESSFUL_OBSERVATION_STATUSES
                  and item.views is not None]
    latest = max(successful, key=lambda item: (item.observed_at, item.observation_id)) if successful else None
    if not observations:
        reasons.append("no_observation")
    elif not before_cutoff:
        reasons.append("observations_after_cutoff_only")
    elif not matching:
        reasons.append("observation_video_id_mismatch")
    elif not successful:
        reasons.append("no_successful_views_observation")
    if latest is not None:
        age = cutoff - _as_naive_utc(latest.observed_at)
        if age > timedelta(hours=latest_observation_hours):
            reasons.append("successful_observation_stale")
        expected = view_metric_version_for("youtube", latest.observed_at)
        if latest.view_metric_version not in SUPPORTED_YOUTUBE_METRICS:
            reasons.append("unknown_view_metric_version")
        elif latest.view_metric_version != expected:
            reasons.append("view_metric_version_timestamp_mismatch")
        if latest.views is not None and latest.views < 0:
            reasons.append("negative_views")
    return latest, reasons


def _gap(
    *, gap_id: str, reason_code: str, suggested_action: str, owner: str,
    deadline: str, dataset_id: int | None = None, video_id: str | None = None,
    category: str | None = None, current_split: str | None = None,
    split_protection: str = "none", missing_field: str | None = None,
    blocking_phase2: bool = True,
) -> dict[str, Any]:
    return {
        "gap_id": gap_id, "dataset_id": dataset_id, "video_id": video_id,
        "category": category, "current_split": current_split,
        "split_protection": split_protection, "missing_field": missing_field,
        "reason_code": reason_code, "suggested_action": suggested_action,
        "owner": owner, "deadline": deadline, "blocking_phase2": blocking_phase2,
    }


def audit_outcome_readiness(
    db: Session, *, cutoff: datetime, repo_root: Path,
    data_use_record: dict[str, Any], latest_observation_hours: int = 24,
) -> dict[str, Any]:
    cutoff = _as_naive_utc(cutoff)
    if cutoff is None:
        raise ValueError("cutoff is required")
    prior_use = scan_prior_artifact_use(repo_root)
    data_use = {
        purpose: data_use_gate(data_use_record, purpose)
        for purpose in ("audit", "training", "serving")
    }
    all_target_rows = db.query(DatasetContent).filter(
        DatasetContent.taxonomy_leaf_key.in_(TARGET_LEAVES)
    ).order_by(DatasetContent.dataset_id).all()
    rows = [row for row in all_target_rows if row.is_active and row.deleted_at is None]
    row_ids = [row.dataset_id for row in rows]
    observations = db.query(ReferenceVideoStatistic).filter(
        ReferenceVideoStatistic.dataset_id.in_(row_ids)
    ).order_by(
        ReferenceVideoStatistic.dataset_id,
        ReferenceVideoStatistic.observed_at,
        ReferenceVideoStatistic.observation_id,
    ).all() if row_ids else []
    observations_by_id: defaultdict[int, list[ReferenceVideoStatistic]] = defaultdict(list)
    for observation in observations:
        observations_by_id[int(observation.dataset_id)].append(observation)

    production_ids = {row.dataset_id for row in db.query(DatasetContent).filter(
        *production_transcript_conditions(train_only=False, require_training=False),
        DatasetContent.taxonomy_leaf_key.in_(TARGET_LEAVES),
    ).all()}
    reference_rows = reference_transcript_rows(db, now=cutoff)
    reference_ids = {row.dataset_id for row in reference_rows}
    reference_channels = {row.source_channel_id for row in reference_rows if row.source_channel_id}

    records: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    coverage: defaultdict[str, dict[str, Counter]] = defaultdict(
        lambda: {"split": Counter(), "format": Counter(), "age": Counter(), "strategy": Counter()}
    )
    ready_channels: defaultdict[str, set[str]] = defaultdict(set)
    latest_success_count = 0
    two_observation_videos = 0
    structurally_ready_count = 0
    for row in rows:
        text = str(row.transcript or "")
        actual_hash = _transcript_hash(text) if text else None
        transcript_state = (
            "empty" if not text.strip() else
            "full_video" if row.transcript_scope == "full_video" else
            "partial_or_windowed" if row.transcript_scope == "first_window" else
            "unknown_scope"
        )
        content_format, format_source = _confirmed_format(row)
        latest, observation_reasons = _latest_observation(
            observations_by_id[row.dataset_id], row, cutoff, latest_observation_hours
        )
        successful_count = sum(
            item.video_id == row.source_youtube_id
            and item.status in SUCCESSFUL_OBSERVATION_STATUSES
            and item.views is not None
            and _as_naive_utc(item.observed_at) <= cutoff
            for item in observations_by_id[row.dataset_id]
        )
        if successful_count >= 2:
            two_observation_videos += 1
        if latest is not None:
            latest_success_count += 1
        age_bucket, age_days = _age_bucket(row.published_at, latest.observed_at if latest else None)
        issues: list[str] = []
        if row.dataset_id not in production_ids:
            issues.append("production_contract_not_met")
        if transcript_state == "empty":
            issues.append("transcript_empty")
        elif transcript_state != "full_video":
            issues.append("transcript_not_full_video")
        if not row.transcript_sha256:
            issues.append("transcript_hash_missing")
        elif actual_hash != row.transcript_sha256:
            issues.append("transcript_hash_mismatch")
        if not row.source_youtube_id:
            issues.append("video_id_missing")
        if not row.source_channel_id:
            issues.append("channel_id_missing")
        if row.published_at is None:
            issues.append("published_at_missing")
        if not isinstance(row.duration_seconds, int) or row.duration_seconds <= 0:
            issues.append("duration_invalid")
        if content_format == "unknown":
            issues.append("confirmed_format_missing")
        issues.extend(observation_reasons)
        if age_bucket == "invalid":
            issues.append("publication_after_observation")
        prior_roles = sorted(set(
            prior_use["by_dataset_id"].get(str(row.dataset_id), [])
            + prior_use["by_video_id"].get(str(row.source_youtube_id or ""), [])
        ))
        protected = row.data_split in PROTECTED_SPLITS
        structural_ready = not issues
        if structural_ready:
            structurally_ready_count += 1
            if row.source_channel_id:
                ready_channels[row.taxonomy_leaf_key].add(row.source_channel_id)
        coverage[row.taxonomy_leaf_key]["split"][row.data_split or "missing"] += 1
        coverage[row.taxonomy_leaf_key]["format"][content_format] += 1
        coverage[row.taxonomy_leaf_key]["age"][age_bucket] += 1
        coverage[row.taxonomy_leaf_key]["strategy"][row.collection_strategy or "missing"] += 1
        record = {
            "dataset_id": row.dataset_id,
            "video_id": row.source_youtube_id,
            "category": row.taxonomy_leaf_key,
            "classification_split": row.data_split,
            "split_protection": "protected_holdout" if protected else "train_or_unassigned",
            "collection_strategy": row.collection_strategy,
            "channel_present": bool(row.source_channel_id),
            "transcript_state": transcript_state,
            "transcript_hash_present": bool(row.transcript_sha256),
            "transcript_hash_matches": bool(actual_hash and actual_hash == row.transcript_sha256),
            "format": content_format,
            "format_source": format_source,
            "duration_seconds": row.duration_seconds,
            "published_at": _iso(row.published_at),
            "latest_observation_id": latest.observation_id if latest else None,
            "latest_observed_at": _iso(latest.observed_at) if latest else None,
            "latest_view_metric_version": latest.view_metric_version if latest else None,
            "views_available": bool(latest is not None and latest.views is not None),
            "successful_observation_count": successful_count,
            "age_bucket": age_bucket,
            "age_days_at_observation": round(age_days, 6) if age_days is not None else None,
            "classification_production_contract": row.dataset_id in production_ids,
            "reference_eligible": row.dataset_id in reference_ids,
            "prior_explicit_roles": prior_roles,
            "fresh_outcome_test_status": "not_demonstrated" if protected else "not_applicable",
            "structurally_ready_without_rights_or_outcome_split": structural_ready,
            "training_allowed": structural_ready and data_use["training"]["allowed"],
            "issues": sorted(set(issues)),
        }
        records.append(record)
        for reason in record["issues"]:
            action = {
                "confirmed_format_missing": "ตรวจ metadata จากแหล่งที่อนุญาตและบันทึกรูปแบบ short_form/long_form ที่ยืนยันได้",
                "no_observation": "เก็บสถิติจาก Video ID ผ่าน collector ที่มีสิทธิ์ โดยไม่ทำ Transcript ใหม่",
                "no_successful_views_observation": "แก้/รอการเก็บสถิติสำเร็จ ไม่แทน Missing ด้วยศูนย์",
                "successful_observation_stale": "รีเฟรชสถิติหลัง Data-use gate ผ่าน",
                "transcript_not_full_video": "ตรวจและนำเข้า Transcript ทั้งคลิปจากแหล่งที่มีสิทธิ์",
                "transcript_hash_mismatch": "ตรวจ Transcript แล้วคำนวณ hash ใหม่ผ่าน workflow แก้ Dataset",
                "production_contract_not_met": "ตรวจ metadata/review fields ตาม production contract โดยไม่เปลี่ยน split",
            }.get(reason, "ตรวจข้อมูลต้นทางและแก้ผ่าน workflow Dataset โดยไม่เดาค่า")
            gaps.append(_gap(
                gap_id=f"row-{row.dataset_id}-{reason}", dataset_id=row.dataset_id,
                video_id=row.source_youtube_id, category=row.taxonomy_leaf_key,
                current_split=row.data_split,
                split_protection="protected" if protected else "none",
                missing_field=reason, reason_code=reason, suggested_action=action,
                owner="dataset_admin", deadline="2026-10-10",
            ))
        if protected and prior_roles:
            gaps.append(_gap(
                gap_id=f"row-{row.dataset_id}-fresh-independence",
                dataset_id=row.dataset_id, video_id=row.source_youtube_id,
                category=row.taxonomy_leaf_key, current_split=row.data_split,
                split_protection="protected", missing_field="fresh_test_independence",
                reason_code="prior_artifact_use_detected",
                suggested_action="คงแถวนี้เป็น protected regression/development และกัน Outcome holdout ใหม่ก่อนใช้",
                owner="evaluation_owner", deadline="2026-10-10",
            ))

    if not data_use["training"]["allowed"] or not data_use["serving"]["allowed"]:
        gaps.insert(0, _gap(
            gap_id="global-data-use-confirmation", reason_code="data_use_unverified",
            missing_field="derived_metrics_permission",
            suggested_action="เจ้าของโครงการตรวจและบันทึกหลักฐานการอนุมัติ/ยอมรับเงื่อนไขที่ใช้กับ Analytics & Reporting; Agent ห้ามยืนยันแทน",
            owner="project_owner", deadline="2026-10-09",
        ))
    gaps.append(_gap(
        gap_id="global-outcome-split-manifest", reason_code="outcome_partition_not_frozen",
        missing_field="fit_tuning_calibration_independent_test_manifest",
        suggested_action="Phase 2 ต้องสร้าง Manifest แยกตาม channel/identity หลังแก้ข้อมูลขั้นต่ำ โดยคง protected splits เดิมและห้ามใช้ Test เลือกวิธี",
        owner="data_engineer", deadline="2026-10-10",
    ))
    gaps.append(_gap(
        gap_id="global-fresh-outcome-holdout", reason_code="fresh_outcome_test_not_demonstrated",
        missing_field="independent_test",
        suggested_action="กันข้อมูล Outcome holdout ใหม่ก่อนตรวจผล และบันทึก independence/prior-use; แถว Test เดิมที่มี artifact role ให้คงเป็น protected regression/development",
        owner="evaluation_owner", deadline="2026-10-10",
    ))
    gaps.append(_gap(
        gap_id="global-sampling-frame", reason_code="general_video_sampling_not_demonstrated",
        missing_field="outcome_sampling_frame",
        suggested_action="หลังแก้ metadata ให้ตรวจ coverage ต่อ category/format/age/channel แล้วเก็บเฉพาะ cell ที่ขาดด้วยกฎก่อนเห็นยอด ไม่เรียก classification_diverse ว่าสุ่มทั่วไป",
        owner="dataset_admin", deadline="2026-10-10",
    ))

    active = db.query(ClassificationModel).filter(
        ClassificationModel.is_active.is_(True)
    ).order_by(ClassificationModel.model_id.desc()).first()
    classifier = classification_model_snapshot(active)
    if not classifier.get("readiness", {}).get("can_accept_predictions"):
        gaps.insert(1, _gap(
            gap_id="global-active-classifier", reason_code="classifier_live_flow_blocked",
            missing_field="accepted_active_classifier",
            suggested_action="ใช้ workflow Train/Evaluate/Activate ของ classifier แยกต่างหาก ห้ามต่ออายุ presentation bypass หรือให้ Outcome model ทายหมวดแทน",
            owner="model_admin", deadline="2026-10-15",
        ))

    split_overlap = {
        "channel": _duplicate_groups(rows, lambda row: row.source_channel_id),
        "video_id": _duplicate_groups(rows, lambda row: row.source_youtube_id),
        "transcript_sha256": _duplicate_groups(rows, lambda row: row.transcript_sha256),
        "normalized_transcript": _duplicate_groups(rows, lambda row: _normalized_text_hash(str(row.transcript or ""))),
    }
    for groups in split_overlap.values():
        for group in groups:
            group["cross_split"] = len(group["splits"]) > 1

    holdouts = [record for record in records if record["classification_split"] in PROTECTED_SPLITS]
    observation_statuses = _counter(item.status for item in observations)
    output = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "captured_at": _iso(datetime.utcnow()),
        "cutoff": _iso(cutoff),
        "mode": "read_only",
        "target_version": TARGET_VERSION,
        "latest_observation_hours": latest_observation_hours,
        "data_use": data_use,
        "dataset": {
            "target_rows_total_including_inactive_or_deleted": len(all_target_rows),
            "active_target_rows": len(rows),
            "independent_video_ids": len({row.source_youtube_id for row in rows if row.source_youtube_id}),
            "independent_channels": len({row.source_channel_id for row in rows if row.source_channel_id}),
            "by_category": _counter(row.taxonomy_leaf_key for row in rows),
            "by_split": _counter(row.data_split for row in rows),
            "by_collection_strategy": _counter(row.collection_strategy for row in rows),
            "by_dataset_source": _counter(row.dataset_source for row in rows),
            "by_license_name": _counter(row.license_name for row in rows),
            "by_verification_status": _counter(row.verification_status for row in rows),
            "by_transcript_source": _counter(row.transcript_source for row in rows),
            "by_transcript_acquisition_method": _counter(
                row.transcript_acquisition_method for row in rows
            ),
            "transcript_states": _counter(record["transcript_state"] for record in records),
            "semantic_summary_detection": "not_machine_verifiable_from_current_schema",
            "formats": _counter(record["format"] for record in records),
            "classification_production_contract_rows": len(production_ids),
            "reference_eligible_rows": len(reference_ids),
            "structurally_ready_without_rights_or_outcome_split": structurally_ready_count,
            "training_allowed_rows": sum(record["training_allowed"] for record in records),
        },
        "statistics": {
            "observation_rows": len(observations),
            "observation_statuses": observation_statuses,
            "videos_with_any_successful_views": latest_success_count,
            "videos_with_two_or_more_successful_observations": two_observation_videos,
            "collector_scope": {
                "selector": "reference_transcript_rows",
                "source": "app/services/reference_statistics.py:_refresh",
                "train_only": True,
                "holdout_collection_supported": False,
            },
        },
        "coverage": {
            category: {
                lane: dict(sorted(counter.items())) for lane, counter in lanes.items()
            } | {"structurally_ready_channels": len(ready_channels[category])}
            for category, lanes in sorted(coverage.items())
        },
        "holdout": {
            "classification_holdout_rows": len(holdouts),
            "with_recent_structural_outcome": sum(
                record["structurally_ready_without_rights_or_outcome_split"] for record in holdouts
            ),
            "missing_or_invalid_outcome": sum(
                not record["structurally_ready_without_rights_or_outcome_split"] for record in holdouts
            ),
            "with_explicit_prior_artifact_roles": sum(bool(record["prior_explicit_roles"]) for record in holdouts),
            "fresh_outcome_test_count": 0,
            "freshness_conclusion": "not_demonstrated",
            "reference_channel_overlap_count": len({
                row.source_channel_id for row in rows
                if row.data_split in PROTECTED_SPLITS and row.source_channel_id in reference_channels
            }),
        },
        "identity_review": split_overlap,
        "identity_review_method": {
            "exact": ["source_youtube_id", "source_channel_id", "transcript_sha256"],
            "near_duplicate_candidate": "exact SHA-256 after case-folding and removing non-alphanumeric characters; semantic duplicates still require human review",
        },
        "prior_use_scan": {
            "files_scanned_count": len(prior_use["files_scanned"]),
            "files_scanned": prior_use["files_scanned"],
            "errors": prior_use["errors"],
            "limitation": prior_use["limitation"],
        },
        "active_classifier": classifier,
        "records": records,
        "gaps": gaps,
        "decisions": {
            "software_readiness_audit": "complete",
            "data_rights": "blocked" if not data_use["training"]["allowed"] else "confirmed",
            "real_training": "blocked" if (
                not data_use["training"]["allowed"] or structurally_ready_count == 0
            ) else "requires_phase_2_manifest",
            "real_serving": "blocked",
            "prediction_qualified": False,
            "reason": "Phase 1 does not train or independently evaluate an outcome model.",
        },
    }
    output["audit_sha256"] = sha256_json(output)
    return output

