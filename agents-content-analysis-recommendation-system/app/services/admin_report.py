from datetime import datetime
import json
import re

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.models import Cluster, ClusterMembership, ClusterRun, DatasetContent, SystemLog
from app.schemas.admin_report import AdminDatasetCreate, AdminDatasetUpdate
from app.services.dataset_eligibility import validate_training_eligibility_values
from app.services.persistence import log_system_event
from app.services.taxonomy import (
    ACTIVE_LEAF_KEYS,
    normalize_taxonomy_leaf,
    taxonomy_path,
)
from app.services.training_transcript import (
    normalize_training_transcript,
    training_transcript_sha256,
)
from app.services.view_metrics import resolve_view_metric_version


_SENSITIVE_LOG_KEY = re.compile(
    r"(?:api[_-]?key|access[_-]?token|refresh[_-]?token|authorization|"
    r"password|secret|cookie|session(?:[_-]?(?:id|key|token))?)",
    re.IGNORECASE,
)


def _sanitize_log_value(value):
    if isinstance(value, dict):
        return {
            key: "[redacted]" if _SENSITIVE_LOG_KEY.fullmatch(str(key))
            else _sanitize_log_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_log_value(item) for item in value]
    if isinstance(value, str):
        return sanitize_system_log_detail(value)
    return value


def sanitize_system_log_detail(detail: str | None) -> str | None:
    """Return concise admin-safe log text without changing the audit row."""
    if detail is None:
        return None
    raw = str(detail).strip()
    if not raw:
        return raw
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        parsed = None
    if isinstance(parsed, (dict, list)):
        return json.dumps(_sanitize_log_value(parsed), ensure_ascii=False)

    for marker in ("Traceback (most recent call last):", "[SQL:", "\nSQL:"):
        if marker in raw:
            raw = raw.split(marker, 1)[0]
    raw = re.sub(
        r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+",
        "Bearer [redacted]",
        raw,
    )
    raw = re.sub(
        r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|authorization|"
        r"password|secret|cookie|session(?:[_-]?(?:id|key|token))?)"
        r"\s*[:=]\s*([^,;\s]+)",
        lambda match: f"{match.group(1)}=[redacted]",
        raw,
    )
    raw = re.sub(r"\s+", " ", raw).strip()
    if len(raw) > 500:
        raw = raw[:497].rstrip() + "..."
    return raw


def list_admin_datasets(
    db: Session,
    *,
    limit: int = 20,
    offset: int = 0,
    source: str | None = None,
    category: str | None = None,
    search: str | None = None,
    trashed: bool = False,
):
    query = db.query(DatasetContent).filter(
        DatasetContent.deleted_at.is_not(None) if trashed else DatasetContent.deleted_at.is_(None))
    if source:
        query = query.filter(DatasetContent.source_platform.like(f"{source}%"))
    if category:
        query = query.filter((DatasetContent.taxonomy_leaf_key == category) |
                             (DatasetContent.category == category))
    if search:
        like_value = f"%{search.strip()}%"
        query = query.filter(
            (DatasetContent.title.like(like_value)) | (DatasetContent.transcript.like(like_value))
        )
    total = query.count()
    items = (
        query.order_by(DatasetContent.created_at.desc(), DatasetContent.trend_score.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return total, items


def create_admin_dataset(
    db: Session,
    *,
    payload: AdminDatasetCreate,
    user_id: int | None = None,
) -> DatasetContent:
    values = payload.model_dump()
    explicit_fields = payload.model_fields_set

    values["title"] = str(values.get("title") or "").strip()

    requested_leaf = values.pop("taxonomy_leaf_key", None)
    if requested_leaf is None and values.get("category"):
        category_leaf = normalize_taxonomy_leaf(str(values["category"]))
        if category_leaf in ACTIVE_LEAF_KEYS:
            requested_leaf = category_leaf

    derived_taxonomy_fields = {
        "taxonomy_version",
        "category_level_1",
        "category_level_2",
        "category_level_3",
    }
    if requested_leaf is None and derived_taxonomy_fields.intersection(explicit_fields):
        raise ValueError(
            "Set taxonomy_leaf_key instead of supplying derived taxonomy fields"
        )
    for field in derived_taxonomy_fields:
        values.pop(field, None)

    if requested_leaf is not None:
        normalized_leaf = normalize_taxonomy_leaf(str(requested_leaf))
        if normalized_leaf not in ACTIVE_LEAF_KEYS:
            raise ValueError(
                "taxonomy_leaf_key must be one of: " + ", ".join(ACTIVE_LEAF_KEYS)
            )
        path = taxonomy_path(normalized_leaf)
        values.update(
            {
                "category": normalized_leaf,
                "taxonomy_version": path["taxonomy_version"],
                "taxonomy_leaf_key": normalized_leaf,
                "category_level_1": path["category_level_1"],
                "category_level_2": path["category_level_2"],
                "category_level_3": path["category_level_3"],
            }
        )
    else:
        values["taxonomy_version"] = payload.taxonomy_version

    supplied_transcript_hash = values.pop("transcript_sha256", None)
    if values.get("transcript") is None:
        if supplied_transcript_hash is not None:
            raise ValueError(
                "transcript_sha256 is derived automatically; submit transcript instead"
            )
    else:
        minimum_length = 80 if values.get("is_training_eligible") else 1
        normalized_transcript = normalize_training_transcript(
            values["transcript"], minimum_length=minimum_length
        )
        transcript_hash = training_transcript_sha256(normalized_transcript)
        if supplied_transcript_hash is not None and supplied_transcript_hash != transcript_hash:
            raise ValueError("transcript_sha256 does not match the normalized transcript")
        duplicate = (
            db.query(DatasetContent)
            .filter(DatasetContent.transcript_sha256 == transcript_hash)
            .first()
        )
        if duplicate is not None:
            raise ValueError(
                "Transcript duplicates existing dataset "
                f"#{duplicate.dataset_id} ({duplicate.title})"
            )
        values["transcript"] = normalized_transcript
        values["transcript_sha256"] = transcript_hash

    values["view_metric_version"] = resolve_view_metric_version(
        values.get("source_platform"),
        values.get("statistics_captured_at"),
        values.get("view_metric_version"),
    )
    validate_training_eligibility_values(values)
    item = DatasetContent(**values)
    db.add(item)
    db.flush()
    log_system_event(
        db,
        user_id=user_id,
        action="admin_dataset_create",
        status="success",
        detail=(
            f"dataset_id={item.dataset_id}, source={item.source_platform}, "
            f"taxonomy={item.taxonomy_leaf_key or '-'}, "
            f"split={item.data_split}, training_eligible={item.is_training_eligible}"
        ),
    )
    db.commit()
    db.refresh(item)
    return item


def update_admin_dataset(
    db: Session,
    *,
    dataset_id: int,
    payload: AdminDatasetUpdate,
    user_id: int | None = None,
    reviewer: str | None = None,
) -> DatasetContent | None:
    item = db.query(DatasetContent).filter(
        DatasetContent.dataset_id == dataset_id,
    ).populate_existing().with_for_update().first()
    if item is None or item.deleted_at is not None:
        return None
    update_data = payload.model_dump(exclude_unset=True)
    # Once assigned, evaluation membership cannot be repurposed as reference data.
    for field in ("data_split", "split_strategy", "creator_group_key"):
        if (item.data_split in {"train", "validation", "test"}
                and field in update_data and update_data[field] != getattr(item, field)):
            raise ValueError("Assigned channel split is locked; import a new independent channel instead")

    old_leaf_key = str(item.taxonomy_leaf_key or "")
    old_transcript_hash = str(item.transcript_sha256 or "")
    requested_leaf = update_data.pop("taxonomy_leaf_key", None)
    derived_taxonomy_fields = {
        "taxonomy_version",
        "category_level_1",
        "category_level_2",
        "category_level_3",
    }
    if requested_leaf is None and "category" in update_data and item.is_training_eligible:
        requested_leaf = update_data.get("category")
    if requested_leaf is None and derived_taxonomy_fields.intersection(update_data):
        raise ValueError(
            "Set taxonomy_leaf_key instead of editing derived taxonomy fields directly"
        )
    for field in derived_taxonomy_fields:
        update_data.pop(field, None)

    if requested_leaf is not None:
        normalized_leaf = normalize_taxonomy_leaf(str(requested_leaf))
        if normalized_leaf not in ACTIVE_LEAF_KEYS:
            raise ValueError(
                "taxonomy_leaf_key must be one of: " + ", ".join(ACTIVE_LEAF_KEYS)
            )
        path = taxonomy_path(normalized_leaf)
        update_data.update(
            {
                "category": normalized_leaf,
                "taxonomy_version": path["taxonomy_version"],
                "taxonomy_leaf_key": normalized_leaf,
                "category_level_1": path["category_level_1"],
                "category_level_2": path["category_level_2"],
                "category_level_3": path["category_level_3"],
            }
        )

    supplied_transcript_hash = update_data.pop("transcript_sha256", None)
    if supplied_transcript_hash is not None and "transcript" not in update_data:
        raise ValueError(
            "transcript_sha256 is derived automatically; submit transcript instead"
        )
    if "transcript" in update_data:
        will_be_training_eligible = bool(
            update_data.get("is_training_eligible", item.is_training_eligible)
        )
        minimum_length = 80 if will_be_training_eligible else 1
        normalized_transcript = normalize_training_transcript(
            update_data.get("transcript"),
            minimum_length=minimum_length,
        )
        transcript_hash = training_transcript_sha256(normalized_transcript)
        duplicate = (
            db.query(DatasetContent)
            .filter(
                DatasetContent.transcript_sha256 == transcript_hash,
                DatasetContent.dataset_id != dataset_id,
            )
            .first()
        )
        if duplicate is not None:
            raise ValueError(
                "Transcript duplicates existing dataset "
                f"#{duplicate.dataset_id} ({duplicate.title})"
            )
        update_data["transcript"] = normalized_transcript
        update_data["transcript_sha256"] = transcript_hash

    if "title" in update_data:
        update_data["title"] = str(update_data["title"] or "").strip()

    explicit_metric_version = update_data.get("view_metric_version")
    metric_inputs_changed = any(
        key in update_data
        for key in (
            "source_platform",
            "statistics_captured_at",
            "views",
        )
    )
    current_values = {
        column.name: getattr(item, column.name)
        for column in DatasetContent.__table__.columns
    }
    current_values.update(update_data)
    current_values["view_metric_version"] = resolve_view_metric_version(
        current_values.get("source_platform"),
        current_values.get("statistics_captured_at") or current_values.get("created_at"),
        (
            explicit_metric_version
            if explicit_metric_version is not None
            else None if metric_inputs_changed else current_values.get("view_metric_version")
        ),
    )

    corrected_training_content = (
        str(current_values.get("taxonomy_leaf_key") or "") != old_leaf_key
        or str(current_values.get("transcript_sha256") or "") != old_transcript_hash
    )
    if corrected_training_content:
        current_values["reviewed_by"] = (
            str(reviewer or "").strip()
            or (f"admin_user_id:{user_id}" if user_id is not None else "admin")
        )
        current_values["reviewed_at"] = datetime.utcnow()

    try:
        validate_training_eligibility_values(current_values)
    except ValueError:
        db.rollback()
        raise

    for key, value in current_values.items():
        if key in update_data or (
            corrected_training_content and key in {"reviewed_by", "reviewed_at"}
        ) or key == "view_metric_version":
            setattr(item, key, value)

    changed_fields = sorted(update_data)
    detail_parts = [
        f"dataset_id={dataset_id}",
        f"fields={changed_fields}",
    ]
    if corrected_training_content:
        detail_parts.extend(
            (
                f"taxonomy={old_leaf_key or '-'}->{item.taxonomy_leaf_key or '-'}",
                "transcript_sha256="
                f"{old_transcript_hash or '-'}->{item.transcript_sha256 or '-'}",
                "model_retrain_required=true",
            )
        )
    log_system_event(
        db,
        user_id=user_id,
        action=(
            "admin_dataset_training_content_corrected"
            if corrected_training_content
            else "admin_dataset_update"
        ),
        status="success",
        detail=", ".join(detail_parts),
    )
    db.commit()
    db.refresh(item)
    return item


def delete_admin_dataset(db: Session, *, dataset_id: int, user_id: int,
                         confirmation_id: int) -> bool:
    if confirmation_id != dataset_id:
        raise ValueError("Dataset confirmation does not match")
    item = db.query(DatasetContent).filter(
        DatasetContent.dataset_id == dataset_id,
    ).populate_existing().with_for_update().first()
    if item is None or item.deleted_at is not None:
        return False
    item.deletion_state_json = json.dumps({name: bool(getattr(item, name)) for name in (
        "is_active", "is_training_eligible", "is_keyword_recommendation_eligible",
        "is_duration_recommendation_eligible")})
    item.deleted_at = datetime.utcnow()
    item.is_active = False
    item.is_training_eligible = False
    item.is_keyword_recommendation_eligible = False
    item.is_duration_recommendation_eligible = False
    log_system_event(db, user_id=user_id, action="admin_dataset_delete", status="success",
                     detail=f"dataset_id={dataset_id}, archived=true, model_retrain_required=true")
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return True


def restore_admin_dataset(db: Session, *, dataset_id: int, user_id: int,
                          confirmation_id: int) -> DatasetContent | None:
    if confirmation_id != dataset_id:
        raise ValueError("Dataset confirmation does not match")
    item = db.query(DatasetContent).filter_by(dataset_id=dataset_id).populate_existing().with_for_update().first()
    if item is None or item.deleted_at is None:
        return None
    state = json.loads(item.deletion_state_json or "{}")
    fields = ("is_active", "is_training_eligible", "is_keyword_recommendation_eligible",
              "is_duration_recommendation_eligible")
    # Legacy deletions have no eligibility backup. Never grant inferred permissions.
    restored = {name: state.get(name, name == "is_active") is True for name in fields}
    values = {column.name: getattr(item, column.name) for column in DatasetContent.__table__.columns}
    values.update(restored, deleted_at=None)
    validate_training_eligibility_values(values)
    for name, value in restored.items():
        setattr(item, name, value)
    item.deleted_at = None
    item.deletion_state_json = None
    log_system_event(db, user_id=user_id, action="admin_dataset_restore", status="success",
                     detail=json.dumps({"dataset_id": dataset_id, "restored_flags": restored,
                                        "legacy_without_backup": not bool(state)}))
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(item)
    return item


def list_admin_cluster_runs(
    db: Session,
    *,
    limit: int = 20,
    offset: int = 0,
    algorithm: str | None = None,
):
    query = db.query(ClusterRun)
    if algorithm:
        query = query.filter(ClusterRun.algorithm == algorithm)
    total = query.count()
    rows = (
        query.with_entities(ClusterRun, func.count(ClusterMembership.membership_id))
        .outerjoin(ClusterMembership, ClusterMembership.run_id == ClusterRun.run_id)
        .group_by(ClusterRun.run_id)
        .order_by(ClusterRun.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    items = [
        {
            "run_id": run.run_id,
            "algorithm": run.algorithm,
            "n_clusters": run.n_clusters,
            "feature_dimension": run.feature_dimension,
            "inertia": float(run.inertia),
            "membership_count": int(membership_count),
            "created_at": run.created_at,
        }
        for run, membership_count in rows
    ]
    return total, items


def list_admin_logs(
    db: Session,
    *,
    limit: int = 30,
    offset: int = 0,
    status: str | None = None,
    action: str | None = None,
):
    query = db.query(SystemLog)
    if status:
        query = query.filter(SystemLog.status == status)
    if action:
        query = query.filter(SystemLog.action.like(f"%{action.strip()}%"))
    total = query.count()
    items = query.order_by(SystemLog.timestamp.desc()).offset(offset).limit(limit).all()
    return total, items


def build_admin_overview_report(db: Session):
    dataset_total = db.query(func.count(DatasetContent.dataset_id)).scalar() or 0
    cluster_run_total = db.query(func.count(ClusterRun.run_id)).scalar() or 0
    system_log_total = db.query(func.count(SystemLog.log_id)).scalar() or 0

    top_sources_raw = (
        db.query(
            DatasetContent.source_platform,
            func.count(DatasetContent.dataset_id),
            func.avg(DatasetContent.trend_score),
        )
        .group_by(DatasetContent.source_platform)
        .order_by(func.count(DatasetContent.dataset_id).desc())
        .limit(10)
        .all()
    )
    top_sources = [
        {
            "source_platform": source_platform or "unknown",
            "count": int(count),
            "avg_trend_score": round(float(avg_trend_score or 0.0), 3),
        }
        for source_platform, count, avg_trend_score in top_sources_raw
    ]

    top_categories_raw = (
        db.query(DatasetContent.category, func.count(DatasetContent.dataset_id))
        .group_by(DatasetContent.category)
        .order_by(func.count(DatasetContent.dataset_id).desc())
        .limit(10)
        .all()
    )
    top_categories = [
        {"category": category or "uncategorized", "count": int(count)}
        for category, count in top_categories_raw
    ]

    status_breakdown_raw = (
        db.query(SystemLog.status, func.count(SystemLog.log_id))
        .group_by(SystemLog.status)
        .order_by(func.count(SystemLog.log_id).desc())
        .all()
    )
    status_breakdown = [
        {"status": status or "unknown", "count": int(count)}
        for status, count in status_breakdown_raw
    ]

    recent_actions_raw = db.query(SystemLog).order_by(SystemLog.timestamp.desc()).limit(10).all()
    recent_actions = [
        {
            "log_id": log.log_id,
            "action": log.action,
            "status": log.status,
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            "detail": log.detail or "",
        }
        for log in recent_actions_raw
    ]

    return {
        "dataset_total": int(dataset_total),
        "cluster_run_total": int(cluster_run_total),
        "system_log_total": int(system_log_total),
        "top_sources": top_sources,
        "top_categories": top_categories,
        "status_breakdown": status_breakdown,
        "recent_actions": recent_actions,
    }


def get_admin_cluster_run_detail(db: Session, *, run_id: int):
    run = db.query(ClusterRun).filter(ClusterRun.run_id == run_id).first()
    if run is None:
        return None

    cluster_rows = (
        db.query(
            ClusterMembership.cluster_id,
            func.count(ClusterMembership.membership_id),
            func.max(ClusterMembership.created_at),
        )
        .filter(ClusterMembership.run_id == run_id)
        .group_by(ClusterMembership.cluster_id)
        .all()
    )
    cluster_names = {
        cluster_id: cluster_name
        for cluster_id, cluster_name in (
            db.query(Cluster.cluster_id, Cluster.cluster_name)
            .join(ClusterMembership, ClusterMembership.cluster_id == Cluster.cluster_id)
            .filter(ClusterMembership.run_id == run_id)
            .group_by(Cluster.cluster_id, Cluster.cluster_name)
            .all()
        )
    }

    cluster_breakdown = [
        {
            "cluster_id": int(cluster_id),
            "cluster_name": cluster_names.get(cluster_id) or f"cluster_{cluster_id}",
            "member_count": int(member_count),
        }
        for cluster_id, member_count, _last_seen in cluster_rows
    ]
    cluster_breakdown.sort(key=lambda item: (-item["member_count"], item["cluster_name"]))

    recent_membership_rows = (
        db.query(ClusterMembership)
        .join(ClusterMembership.cluster)
        .filter(ClusterMembership.run_id == run_id)
        .order_by(ClusterMembership.created_at.desc())
        .limit(20)
        .all()
    )
    recent_memberships = [
        {
            "membership_id": row.membership_id,
            "cluster_id": row.cluster_id,
            "cluster_name": row.cluster.cluster_name if row.cluster else f"cluster_{row.cluster_id}",
            "dataset_id": row.dataset_id,
            "content_id": row.content_id,
            "item_text": row.item_text,
            "top_terms": row.top_terms,
            "created_at": row.created_at,
        }
        for row in recent_membership_rows
    ]

    return {
        "run_id": run.run_id,
        "algorithm": run.algorithm,
        "n_clusters": run.n_clusters,
        "feature_dimension": run.feature_dimension,
        "inertia": float(run.inertia or 0.0),
        "membership_count": sum(item["member_count"] for item in cluster_breakdown),
        "created_at": run.created_at,
        "cluster_breakdown": cluster_breakdown,
        "recent_memberships": recent_memberships,
    }
