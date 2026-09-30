"""Read-only role audit and collection planning; no relabeling or model training."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.datetime_utils import utc_isoformat
from app.database.models import DatasetContent, TrendSnapshotRun
from app.services.dataset_contract import ACCEPTED_TRANSCRIPT_QUALITIES, PRIMARY_CONTENT_LANGUAGE
from app.services.dataset_eligibility import (
    production_transcript_query, reference_transcript_rows, reference_source_matches,
)
from app.services.recommendation import (
    _high_performing_rows, _single_view_metric_cohort, _duration_evidence_rows,
)
from app.services.taxonomy import ACTIVE_LEAF_KEYS, TAXONOMY_VERSION, ready_leaf_keys
from app.services.topic_comparisons import topic_comparison_readiness
from app.services.trend_history import _samples_for_run
from app.services.youtube_cc_dataset import extract_youtube_video_id, YouTubeCCDatasetError

PRIMARY_CATEGORIES = ("phone", "camera", "laptop")
POLICY_VERSION = "dataset-roles-v1"


def _current_trends(db: Session, now: datetime) -> tuple[dict, dict]:
    matches, feeds = {}, []
    for kind in ("global", "youtube_categories"):
        run = db.query(TrendSnapshotRun).options(selectinload(TrendSnapshotRun.items)).filter(
            TrendSnapshotRun.region == settings.youtube_region,
            TrendSnapshotRun.snapshot_kind == kind,
            TrendSnapshotRun.status.in_(("completed", "partial")),
            TrendSnapshotRun.completed_at <= now,
        ).order_by(TrendSnapshotRun.completed_at.desc(), TrendSnapshotRun.run_id.desc()).first()
        if run is None:
            continue
        fresh = now - run.completed_at <= timedelta(hours=24)
        try:
            samples = _samples_for_run(run)
        except (ValueError, TypeError, AttributeError):
            samples = []
        for platform, scope, sample in samples:
            feeds.append({"platform": platform, "scope": scope, "run_id": run.run_id,
                          "observed_at": utc_isoformat(run.completed_at),
                          "fresh": fresh, "count": len(sample["items"])})
        scopes = {(p, scope) for p, scope, _ in samples}
        if not fresh:
            continue
        for item in run.items:
            if item.platform != "youtube" or (item.platform, item.ranking_scope) not in scopes:
                continue
            if not 1 <= item.provider_rank <= 50:
                continue
            try:
                video_id = extract_youtube_video_id(item.video_url or "")
            except YouTubeCCDatasetError:
                continue
            matches.setdefault(video_id, []).append({
                "run_id": run.run_id, "scope": item.ranking_scope, "rank": item.provider_rank,
                "observed_at": utc_isoformat(run.completed_at), "video_url": item.video_url,
            })
    return matches, {"freshness_hours": 24, "region": settings.youtube_region, "feeds": feeds}


def _checks(row: DatasetContent, now: datetime) -> list[dict]:
    published, captured = row.published_at, row.statistics_captured_at
    if _is_trend_archive(row):
        return [{"key": "statistics_captured_at", "label": "วันที่เก็บข้อมูลเทรนด์",
                 "ok": captured is not None and captured <= now}]
    conditions = [
        ("active", "เปิดใช้งานข้อมูล", row.is_active),
        ("language", "ภาษาไทยตามขอบเขตโมเดล", row.language == PRIMARY_CONTENT_LANGUAGE),
        ("transcript", "Transcript ผ่านการตรวจ", bool(str(row.transcript or "").strip())
         and row.transcript_quality in ACCEPTED_TRANSCRIPT_QUALITIES),
        ("category", "หมวดผ่านการยืนยัน", row.taxonomy_leaf_key in ACTIVE_LEAF_KEYS
         and row.taxonomy_version == TAXONOMY_VERSION and row.verification_status == "human_verified"),
        ("source", "ลิงก์ตรงกับ YouTube Video ID", reference_source_matches(row)),
        ("published_at", "วันที่เผยแพร่", published is not None and published <= now),
        ("statistics_captured_at", "วันที่เก็บสถิติ", captured is not None and published is not None
         and published <= captured <= now),
        ("duration", "ความยาวและช่วง Transcript", bool(row.duration_seconds and row.duration_seconds > 0)
         and (row.transcript_end_seconds is None or row.transcript_end_seconds <= row.duration_seconds)),
        ("channel", "ช่องต้นทาง", bool(str(row.source_channel_id or "").strip())),
    ]
    return [{"key": key, "label": label, "ok": bool(ok)} for key, label, ok in conditions]


def _is_trend_archive(row: DatasetContent) -> bool:
    return (row.source_platform in {"youtube_live", "google_live"}
            and row.dataset_source == "legacy" and not row.taxonomy_leaf_key
            and not row.is_training_eligible and not row.is_keyword_recommendation_eligible)


def dataset_quality(row: DatasetContent) -> dict:
    checks = _checks(row, datetime.utcnow())
    return {"status": "archived" if row.deleted_at else
            "needs_attention" if any(not c["ok"] for c in checks) else "complete",
            "issues": [c["label"] for c in checks if not c["ok"]],
            "training_enabled": bool(row.is_training_eligible),
            "reference_enabled": bool(row.is_keyword_recommendation_eligible)}


def dataset_readiness(db: Session, *, category: str | None = None, role: str = "all",
                      offset: int = 0, limit: int = 20, now: datetime | None = None) -> dict:
    now = now or datetime.utcnow()
    rows = db.query(DatasetContent).filter(DatasetContent.deleted_at.is_(None)).order_by(
        DatasetContent.dataset_id.desc()).all()
    training_ids = {row.dataset_id for row in production_transcript_query(db).all()}
    reference_rows = reference_transcript_rows(db, now=now)
    reference_ids = {row.dataset_id for row in reference_rows}
    ready = set(ready_leaf_keys(db))
    trends, trend_summary = _current_trends(db, now)
    performance, selected_ids, plans = {}, set(), []
    leaves = list(PRIMARY_CATEGORIES) + sorted({r.taxonomy_leaf_key for r in rows
        if r.taxonomy_leaf_key in ACTIVE_LEAF_KEYS} - set(PRIMARY_CATEGORIES))
    for leaf in leaves:
        classified = [r for r in rows if r.taxonomy_leaf_key == leaf and r.dataset_id in training_ids]
        candidates = [r for r in reference_rows if r.taxonomy_leaf_key == leaf]
        cohort, metric, _ = _single_view_metric_cohort(candidates)
        high, _ = _high_performing_rows(cohort, limit=150)
        high_ids = {r.dataset_id for r in high}
        if leaf in ready:
            selected_ids.update(high_ids)
        for row in cohort:
            performance[row.dataset_id] = "upper_pool" if row.dataset_id in high_ids else "comparison_pool"
        channels = Counter(r.source_channel_id for r in classified if r.source_channel_id)
        splits = Counter(r.data_split for r in classified)
        durations = len(_duration_evidence_rows(candidates))
        missing = Counter(c["key"] for r in rows if r.taxonomy_leaf_key == leaf
                          for c in _checks(r, now) if not c["ok"])
        general = len(cohort) - len(high)
        comparison_audit = topic_comparison_readiness(
            db, candidates, domain=leaf, as_of=now
        )
        actions = []
        if len(classified) < 80:
            actions.append(f"เพิ่มคลิปที่ตรวจแล้วอีก {80 - len(classified)} คลิป ให้ถึงเป้าหมายเริ่มต้น 80 คลิป")
        if len(channels) < 10:
            actions.append(f"เพิ่มช่องอิสระอีกอย่างน้อย {10 - len(channels)} ช่อง เพื่อให้ถึงเป้าหมาย 10 ช่อง")
        largest = max(channels.values(), default=0)
        if classified and largest / len(classified) > 0.4:
            actions.append("ข้อมูลกระจุกตัวในช่องเดียวเกิน 40% ควรเพิ่มช่องอื่น ไม่ได้จำกัดคลิปต่อช่อง")
        for split, label in (("validation", "Validation"), ("test", "Test")):
            if splits[split] < 5:
                actions.append(f"เก็บ {label} จากช่องที่ถูกกันไว้เพิ่ม {5 - splits[split]} คลิป ห้ามย้ายชุดฝึกมาเติม")
        if len(high) < 10:
            actions.append(f"เพิ่มคลิปอ้างอิงกลุ่มคะแนนบนอย่างน้อย {10 - len(high)} คลิป พร้อมสถิติและวันที่เก็บ")
        if general < 10:
            actions.append(f"เพิ่มคลิปเปรียบเทียบทั่วไปอย่างน้อย {10 - general} คลิป จากหมวด/ช่วงเวลา/รูปแบบใกล้กัน")
        if not any(topic["views_status"] in {"comparison_descriptive", "comparison_uncertain", "comparison_supported"}
                   for topic in comparison_audit["topics"]):
            actions.append("ยังไม่มีหัวข้อที่มีกลุ่มตรวจพบ/ยังไม่ตรวจพบอย่างน้อยฝั่งละ 10 คลิปจาก 5 ช่องคู่เทียบ")
        if durations < 10:
            actions.append(f"ยังขาดหลักฐานความยาว {10 - durations} คลิป สำหรับคำแนะนำคลิปไม่เกิน 5 นาที")
        if missing:
            actions.append("แก้ข้อมูลที่ขาดหรือไม่สอดคล้องตามรายการตรวจ ก่อนนำไปอ้างเหตุผล")
        plans.append({"category": leaf, "classification_count": len(classified),
                      "split_counts": dict(splits), "channels": len(channels),
                      "largest_channel_share": round(largest / len(classified), 4) if classified else 0,
                      "reference_count": len(candidates), "selected_reference_count": len(high) if leaf in ready else 0,
                      "upper_pool_count": len(high), "comparison_pool_count": general,
                      "duration_count": durations, "view_metric_version": metric,
                      "missing_fields": dict(missing), "topic_comparison": comparison_audit,
                      "actions": actions})
    items = []
    # Include archived evaluation channels too: deleting a row must not release its holdout.
    held_channels = {v for (v,) in db.query(DatasetContent.source_channel_id).filter(
        DatasetContent.data_split.in_(("validation", "test"))).all() if v}
    for row in rows:
        checks = _checks(row, now)
        issues = [check["label"] for check in checks if not check["ok"]]
        roles = []
        if _is_trend_archive(row):
            roles.append("trend_archive")
        if row.dataset_id in training_ids and row.data_split == "train":
            roles.append("classification")
        if row.data_split in ("validation", "test"):
            roles.append("evaluation")
        if row.dataset_id in reference_ids:
            roles.append("reference")
        evidence = trends.get(row.source_youtube_id, [])
        if evidence:
            roles.append("current_trend")
        blockers = list(issues)
        if row.data_split in ("validation", "test"):
            blockers.insert(0, "กันไว้ประเมินโมเดล ห้ามใช้สร้างคำแนะนำ")
        elif row.data_split != "train":
            blockers.insert(0, "ยังไม่กำหนดชุดข้อมูลตามช่อง")
        elif row.source_channel_id in held_channels:
            blockers.insert(0, "ช่องเดียวกับชุดประเมิน ต้องกันออกจากคลิปอ้างอิง")
        if not row.is_keyword_recommendation_eligible:
            blockers.append("ไม่ได้เปิดสิทธิ์ใช้เป็นคลิปอ้างอิง")
        if row.dataset_id not in reference_ids and not blockers:
            blockers.append("หลักฐานนำเข้าหรือข้อมูลซ้ำกับชุดประเมินไม่ผ่านเกณฑ์อ้างอิง")
        if row.dataset_id in reference_ids:
            blockers = []
        if _is_trend_archive(row):
            blockers = ["ข้อมูลเทรนด์ที่เก็บไว้ ไม่ใช่ Transcript ที่ผ่านการตรวจสำหรับแนะนำ"]
        items.append({"dataset_id": row.dataset_id, "title": row.title, "category": row.taxonomy_leaf_key,
                      "source_platform": row.source_platform, "channel": row.source_creator,
                      "source_channel_id": row.source_channel_id, "video_url": row.video_url or row.source_release_url,
                      "published_at": utc_isoformat(row.published_at),
                      "statistics_captured_at": utc_isoformat(row.statistics_captured_at),
                      "duration_seconds": row.duration_seconds, "data_split": row.data_split,
                      "language": row.language, "training_contract_passed": row.dataset_id in training_ids,
                      "roles": roles, "checks": checks, "issues": issues, "reference_blockers": blockers,
                      "reference_selected": row.dataset_id in selected_ids,
                      "performance_group": performance.get(row.dataset_id, "not_comparable"),
                      "trend_evidence": evidence, "collection_strategy": row.collection_strategy})
    summary = {"total": len(items), "classification": sum("classification" in i["roles"] for i in items),
               "evaluation": sum("evaluation" in i["roles"] for i in items),
               "reference": len(reference_ids), "reference_selected": len(selected_ids),
               "current_trend": sum("current_trend" in i["roles"] for i in items),
               "trend_archive": sum("trend_archive" in i["roles"] for i in items),
               "needs_attention": sum(bool(i["issues"]) for i in items)}
    filtered = [item for item in items if (not category or item["category"] == category)
                and (role == "all" or role in item["roles"]
                     or (role == "needs_attention" and item["issues"]))]
    return {"policy_version": POLICY_VERSION, "generated_at": utc_isoformat(now),
            "summary": summary, "plans": plans, "current_trends": trend_summary,
            "total": len(filtered), "items": filtered[offset:offset + limit],
            "policy": {"reference_splits": ["train"], "excluded_splits": ["validation", "test"],
                       "target_per_category": [80, 100], "target_channels": 10,
                       "target_upper_pool": 10, "target_comparison_pool": 10,
                       "topic_comparison_policy": "topic-comparison-policy-v1",
                       "evaluation_minimum_per_category": 5,
                       "performance_rule": "existing_top_40_percent_min_10_in_same_category_and_view_metric",
                       "causal_claim": False}}
