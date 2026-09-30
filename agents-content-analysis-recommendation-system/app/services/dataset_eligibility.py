from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from datetime import datetime
from sqlalchemy import func, or_, and_
from sqlalchemy.orm import Query, Session, aliased

from app.database.models import DatasetContent
from app.services.dataset_contract import (
    ACCEPTED_TRANSCRIPT_QUALITIES,
    PRIMARY_CONTENT_LANGUAGE,
    PRODUCTION_SPLITS,
    SUPPORTED_CAPTION_TYPES,
    SUPPORTED_TRANSCRIPT_SOURCES,
    SUPPORTED_TRANSCRIPT_ACQUISITION_METHODS,
    SUPPORTED_TRANSCRIPT_LANGUAGES,
    SUPPORTED_TRANSCRIPT_SCOPES,
    SUPPORTED_YOUTUBE_DATASET_SOURCES,
    YOUTUBE_CC_LABEL_SOURCE,
    YOUTUBE_CC_VERIFICATION_STATUS,
)
from app.services.taxonomy import (
    ACTIVE_LEAF_KEYS,
    TAXONOMY_VERSION,
    UNKNOWN_LEAF_KEY,
)


def production_transcript_conditions(*, train_only: bool = False, require_training: bool = True):
    conditions = [
        DatasetContent.deleted_at.is_(None),
        DatasetContent.is_active.is_(True),
        DatasetContent.dataset_source.in_(SUPPORTED_YOUTUBE_DATASET_SOURCES),
        DatasetContent.dataset_version != "legacy-v1",
        DatasetContent.taxonomy_version == TAXONOMY_VERSION,
        DatasetContent.taxonomy_leaf_key.in_(ACTIVE_LEAF_KEYS),
        DatasetContent.verification_status == YOUTUBE_CC_VERIFICATION_STATUS,
        DatasetContent.label_source == YOUTUBE_CC_LABEL_SOURCE,
        DatasetContent.language == PRIMARY_CONTENT_LANGUAGE,
        DatasetContent.source_platform == "youtube",
        DatasetContent.transcript_source.in_(SUPPORTED_TRANSCRIPT_SOURCES),
        DatasetContent.transcript_acquisition_method.in_(
            SUPPORTED_TRANSCRIPT_ACQUISITION_METHODS
        ),
        DatasetContent.transcript_scope.in_(SUPPORTED_TRANSCRIPT_SCOPES),
        DatasetContent.caption_type.in_(SUPPORTED_CAPTION_TYPES),
        DatasetContent.transcript_quality.in_(ACCEPTED_TRANSCRIPT_QUALITIES),
        DatasetContent.collection_run_id.is_not(None),
        DatasetContent.source_record_id.is_not(None),
        DatasetContent.source_youtube_id.is_not(None),
        DatasetContent.source_channel_id.is_not(None),
        DatasetContent.source_creator.is_not(None),
        DatasetContent.source_category.is_not(None),
        DatasetContent.collection_query.is_not(None),
        DatasetContent.source_release_url.is_not(None),
        DatasetContent.source_archive_sha256.is_not(None),
        DatasetContent.source_annotation_path.is_not(None),
        DatasetContent.source_annotation_sha256.is_not(None),
        DatasetContent.import_batch_id.is_not(None),
        DatasetContent.split_strategy.is_not(None),
        DatasetContent.creator_group_key.is_not(None),
        DatasetContent.transcript_sha256.is_not(None),
        DatasetContent.license_name.is_not(None),
        DatasetContent.license_url.is_not(None),
        DatasetContent.reviewed_by.is_not(None),
        DatasetContent.reviewed_at.is_not(None),
        DatasetContent.statistics_captured_at.is_not(None),
        DatasetContent.license_verified_at.is_not(None),
        DatasetContent.raw_metadata_json.is_not(None),
        func.length(func.trim(DatasetContent.transcript)) > 0,
        func.length(func.trim(DatasetContent.source_youtube_id)) > 0,
        func.length(func.trim(DatasetContent.source_channel_id)) > 0,
        func.length(func.trim(DatasetContent.source_creator)) > 0,
        func.length(func.trim(DatasetContent.source_category)) > 0,
        func.length(func.trim(DatasetContent.collection_query)) > 0,
        func.length(func.trim(DatasetContent.source_release_url)) > 0,
        func.length(func.trim(DatasetContent.source_archive_sha256)) == 64,
        func.length(func.trim(DatasetContent.source_annotation_path)) > 0,
        func.length(func.trim(DatasetContent.source_annotation_sha256)) == 64,
        func.length(func.trim(DatasetContent.import_batch_id)) == 64,
        func.length(func.trim(DatasetContent.split_strategy)) > 0,
        func.length(func.trim(DatasetContent.creator_group_key)) == 64,
        func.length(func.trim(DatasetContent.transcript_sha256)) == 64,
        func.length(func.trim(DatasetContent.license_name)) > 0,
        func.length(func.trim(DatasetContent.license_url)) > 0,
        func.length(func.trim(DatasetContent.reviewed_by)) > 0,
        func.length(func.trim(DatasetContent.raw_metadata_json)) > 2,
        DatasetContent.transcript_window_seconds > 0,
        DatasetContent.transcript_end_seconds > 0,
        DatasetContent.transcript_end_seconds <= DatasetContent.duration_seconds,
        DatasetContent.duration_seconds > 0,
    ]
    if require_training:
        conditions.append(DatasetContent.is_training_eligible.is_(True))
    if train_only:
        conditions.append(DatasetContent.data_split == "train")
    else:
        conditions.append(DatasetContent.data_split.in_(PRODUCTION_SPLITS))
    return tuple(conditions)


def out_of_scope_evaluation_conditions():
    """Return auditable human-reviewed rows used only to evaluate rejection."""
    return (
        DatasetContent.deleted_at.is_(None),
        DatasetContent.is_active.is_(True),
        DatasetContent.is_training_eligible.is_(False),
        DatasetContent.is_keyword_recommendation_eligible.is_(False),
        DatasetContent.is_duration_recommendation_eligible.is_(False),
        DatasetContent.dataset_source.in_(SUPPORTED_YOUTUBE_DATASET_SOURCES),
        DatasetContent.dataset_version != "legacy-v1",
        DatasetContent.taxonomy_version == TAXONOMY_VERSION,
        DatasetContent.taxonomy_leaf_key == UNKNOWN_LEAF_KEY,
        DatasetContent.verification_status == YOUTUBE_CC_VERIFICATION_STATUS,
        DatasetContent.label_source == YOUTUBE_CC_LABEL_SOURCE,
        DatasetContent.language == PRIMARY_CONTENT_LANGUAGE,
        DatasetContent.source_platform == "youtube",
        DatasetContent.transcript_source.in_(SUPPORTED_TRANSCRIPT_SOURCES),
        DatasetContent.transcript_acquisition_method.in_(
            SUPPORTED_TRANSCRIPT_ACQUISITION_METHODS
        ),
        DatasetContent.transcript_scope.in_(SUPPORTED_TRANSCRIPT_SCOPES),
        DatasetContent.caption_type.in_(SUPPORTED_CAPTION_TYPES),
        DatasetContent.transcript_quality.in_(ACCEPTED_TRANSCRIPT_QUALITIES),
        DatasetContent.data_split.in_(PRODUCTION_SPLITS),
        DatasetContent.collection_run_id.is_not(None),
        DatasetContent.source_record_id.is_not(None),
        DatasetContent.source_youtube_id.is_not(None),
        DatasetContent.source_channel_id.is_not(None),
        DatasetContent.creator_group_key.is_not(None),
        DatasetContent.transcript_sha256.is_not(None),
        DatasetContent.reviewed_by.is_not(None),
        DatasetContent.reviewed_at.is_not(None),
        DatasetContent.raw_metadata_json.is_not(None),
        func.length(func.trim(DatasetContent.transcript)) > 0,
        func.length(func.trim(DatasetContent.source_youtube_id)) > 0,
        func.length(func.trim(DatasetContent.source_channel_id)) > 0,
        func.length(func.trim(DatasetContent.creator_group_key)) == 64,
        func.length(func.trim(DatasetContent.transcript_sha256)) == 64,
        func.length(func.trim(DatasetContent.reviewed_by)) > 0,
        func.length(func.trim(DatasetContent.raw_metadata_json)) > 2,
        DatasetContent.transcript_end_seconds > 0,
        DatasetContent.transcript_end_seconds <= DatasetContent.duration_seconds,
        DatasetContent.duration_seconds > 0,
    )


def out_of_scope_evaluation_query(db: Session) -> Query:
    return db.query(DatasetContent).filter(*out_of_scope_evaluation_conditions())


def validate_training_eligibility_values(values: Mapping[str, Any] | object) -> None:
    def value(name: str) -> Any:
        if isinstance(values, Mapping):
            return values.get(name)
        return getattr(values, name, None)

    if not bool(value("is_training_eligible")):
        return

    errors: list[str] = []
    required_text = (
        "transcript",
        "source_record_id",
        "source_youtube_id",
        "source_channel_id",
        "source_creator",
        "source_category",
        "collection_query",
        "source_release_url",
        "source_annotation_path",
        "split_strategy",
        "creator_group_key",
        "transcript_source",
        "transcript_acquisition_method",
        "transcript_scope",
        "caption_type",
        "transcript_quality",
        "reviewed_by",
        "raw_metadata_json",
    )
    for field in required_text:
        if not str(value(field) or "").strip():
            errors.append(field)

    for field in (
        "source_archive_sha256",
        "source_annotation_sha256",
        "import_batch_id",
        "transcript_sha256",
    ):
        if not re.fullmatch(r"[0-9a-fA-F]{64}", str(value(field) or "")):
            errors.append(field)

    if not value("collection_run_id"):
        errors.append("collection_run_id")
    if str(value("dataset_source") or "") not in SUPPORTED_YOUTUBE_DATASET_SOURCES:
        errors.append(
            "dataset_source=" + "/".join(SUPPORTED_YOUTUBE_DATASET_SOURCES)
        )
    if str(value("dataset_version") or "") in {"", "legacy-v1"}:
        errors.append("dataset_version")
    if str(value("taxonomy_version") or "") != TAXONOMY_VERSION:
        errors.append(f"taxonomy_version={TAXONOMY_VERSION}")
    if str(value("taxonomy_leaf_key") or "") not in ACTIVE_LEAF_KEYS:
        errors.append("taxonomy_leaf_key")
    if str(value("verification_status") or "") != YOUTUBE_CC_VERIFICATION_STATUS:
        errors.append(f"verification_status={YOUTUBE_CC_VERIFICATION_STATUS}")
    if str(value("label_source") or "") != YOUTUBE_CC_LABEL_SOURCE:
        errors.append(f"label_source={YOUTUBE_CC_LABEL_SOURCE}")
    if str(value("language") or "") not in SUPPORTED_TRANSCRIPT_LANGUAGES:
        errors.append("language")
    if str(value("source_platform") or "") != "youtube":
        errors.append("source_platform=youtube")
    if str(value("transcript_source") or "") not in SUPPORTED_TRANSCRIPT_SOURCES:
        errors.append("transcript_source")
    if (
        str(value("transcript_acquisition_method") or "")
        not in SUPPORTED_TRANSCRIPT_ACQUISITION_METHODS
    ):
        errors.append("transcript_acquisition_method")
    if str(value("transcript_scope") or "") not in SUPPORTED_TRANSCRIPT_SCOPES:
        errors.append("transcript_scope")
    if str(value("caption_type") or "") not in SUPPORTED_CAPTION_TYPES:
        errors.append("caption_type")
    if str(value("transcript_quality") or "") not in ACCEPTED_TRANSCRIPT_QUALITIES:
        errors.append("transcript_quality")
    if str(value("data_split") or "") not in PRODUCTION_SPLITS:
        errors.append("data_split")
    if not str(value("license_name") or "").strip():
        errors.append("license_name")
    if not str(value("license_url") or "").strip():
        errors.append("license_url")
    if value("reviewed_at") is None:
        errors.append("reviewed_at")
    if value("statistics_captured_at") is None:
        errors.append("statistics_captured_at")
    if value("license_verified_at") is None:
        errors.append("license_verified_at")
    transcript_window = value("transcript_window_seconds")
    if transcript_window is None or int(transcript_window) <= 0:
        errors.append("transcript_window_seconds")
    transcript_end = value("transcript_end_seconds")
    if transcript_end is None or float(transcript_end) <= 0:
        errors.append("transcript_end_seconds")
    duration = value("duration_seconds")
    if duration is None or int(duration) <= 0:
        errors.append("duration_seconds")
    elif transcript_end is not None and float(transcript_end) > int(duration):
        errors.append("transcript_end_seconds")
    if not bool(value("is_active")):
        errors.append("is_active")

    if errors:
        raise ValueError(
            "Training-eligible YouTube row has invalid or missing provenance: "
            + ", ".join(dict.fromkeys(errors))
        )


def production_transcript_query(
    db: Session,
    *,
    train_only: bool = False,
) -> Query:
    return db.query(DatasetContent).filter(
        *production_transcript_conditions(train_only=train_only)
    )


def reference_transcript_query(db: Session, *, now: datetime | None = None) -> Query:
    """Reference evidence never uses evaluation clips or their channel/content duplicates."""
    holdout = aliased(DatasetContent)
    overlap = db.query(holdout.dataset_id).filter(
        holdout.data_split.in_(("validation", "test")),
        or_(*(
            and_(getattr(DatasetContent, key) != "",
                 getattr(holdout, key) == getattr(DatasetContent, key))
            for key in ("source_channel_id", "creator_group_key", "source_youtube_id", "transcript_sha256")
        )),
    ).exists()
    return db.query(DatasetContent).filter(
        *production_transcript_conditions(train_only=True, require_training=False),
        DatasetContent.is_keyword_recommendation_eligible.is_(True),
        DatasetContent.published_at.is_not(None),
        DatasetContent.statistics_captured_at >= DatasetContent.published_at,
        DatasetContent.statistics_captured_at <= (now or datetime.utcnow()),
        DatasetContent.views >= 0, DatasetContent.likes >= 0, DatasetContent.comments >= 0,
        ~overlap,
    )


def reference_source_matches(row: DatasetContent) -> bool:
    from app.services.youtube_cc_dataset import extract_youtube_video_id, YouTubeCCDatasetError
    url = str(row.video_url or row.source_release_url or "")
    if not url.startswith(("https://", "http://")):
        return False
    try:
        return extract_youtube_video_id(url) == row.source_youtube_id
    except YouTubeCCDatasetError:
        return False


def reference_transcript_rows(db: Session, *, now: datetime | None = None,
                              domain: str | None = None) -> list[DatasetContent]:
    query = reference_transcript_query(db, now=now)
    if domain is not None:
        query = query.filter(DatasetContent.taxonomy_leaf_key == domain)
    return [row for row in query.order_by(DatasetContent.dataset_id).all()
            if reference_source_matches(row)]
