import json
import os
from collections import Counter
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.database.models import (
    AnalysisResult,
    ClassificationModel,
    Cluster,
    ClusterMembership,
    ClusterRun,
    ContentKeyword,
    DatasetContent,
    Recommendation,
    Keyword,
    SystemLog,
    TrendingItem,
    User,
    UserContent,
)
from app.services.nlp import filter_tokens, tokenize_text
from app.services.view_metrics import resolve_view_metric_version


def log_system_event(db: Session, user_id: Optional[int], action: str, status: str, detail: Optional[str] = None) -> None:
    db.add(SystemLog(user_id=user_id, action=action, status=status, detail=detail))


def _save_dataset_trends(
    db: Session,
    items: List[object],
    user_id: Optional[int],
    source_mode: str,
    source_name: str,
    action_name: str,
) -> Dict[str, int]:
    created = 0
    updated = 0
    notifications_created = 0

    for item in items:
        captured_at = datetime.utcnow()
        source_platform = f"{source_name}_{source_mode}"
        view_metric_version = resolve_view_metric_version(
            source_platform,
            captured_at,
            getattr(item, "view_metric_version", None),
        )
        existing = (
            db.query(DatasetContent)
            .filter(
                DatasetContent.video_url == item.video_url,
                DatasetContent.view_metric_version == view_metric_version,
            )
            .first()
        )
        payload = {
            "title": item.title,
            "video_url": item.video_url,
            "transcript": None,
            "category": getattr(item, "category", None),
            "source_platform": source_platform,
            "statistics_captured_at": captured_at,
            "view_metric_version": view_metric_version,
            "views": item.views,
            "likes": item.likes,
            "comments": item.comments,
            "trend_score": item.trend_score,
            "duration_seconds": getattr(item, "duration_seconds", None),
            "published_at": item.published_at,
        }
        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
            updated += 1
        else:
            existing = DatasetContent(**payload)
            db.add(existing)
            created += 1
        db.flush()

    log_system_event(
        db,
        user_id=user_id,
        action=action_name,
        status="success",
        detail=f"created={created}, updated={updated}, notifications={notifications_created}",
    )
    db.commit()
    return {"created": created, "updated": updated, "notifications": notifications_created}


def save_youtube_trends(
    db: Session,
    items: List[object],
    user_id: Optional[int],
    source_mode: str,
) -> Dict[str, int]:
    return _save_dataset_trends(
        db=db,
        items=items,
        user_id=user_id,
        source_mode=source_mode,
        source_name="youtube",
        action_name="youtube_trends_sync",
    )


def save_google_trends(
    db: Session,
    items: List[object],
    user_id: Optional[int],
    source_mode: str,
) -> Dict[str, int]:
    return _save_dataset_trends(
        db=db,
        items=items,
        user_id=user_id,
        source_mode=source_mode,
        source_name="google",
        action_name="google_trends_sync",
    )


def save_tiktok_trends(
    db: Session,
    items: List[object],
    user_id: Optional[int],
    source_mode: str,
) -> Dict[str, int]:
    return _save_dataset_trends(
        db=db,
        items=items,
        user_id=user_id,
        source_mode=source_mode,
        source_name="tiktok",
        action_name="tiktok_trends_sync",
    )


def save_trending_items(
    db: Session,
    items: List[Dict[str, object]],
    user_id: Optional[int],
    action_name: str = "trending_items_sync",
) -> Dict[str, int]:
    created = 0
    updated = 0

    for payload in items:
        keyword = payload.get("keyword")
        source = payload.get("source")
        domain = payload.get("domain")
        existing = (
            db.query(TrendingItem)
            .filter(
                TrendingItem.keyword == keyword,
                TrendingItem.source == source,
                TrendingItem.domain == domain,
            )
            .first()
        )
        if existing:
            existing.score = float(payload.get("score", existing.score))
            existing.fetched_at = payload.get("fetched_at", existing.fetched_at)
            existing.meta = payload.get("meta", existing.meta)
            updated += 1
        else:
            db.add(TrendingItem(**payload))
            created += 1

    log_system_event(
        db,
        user_id=user_id,
        action=action_name,
        status="success",
        detail=f"created={created}, updated={updated}",
    )
    db.commit()
    return {"created": created, "updated": updated}


def _get_or_create_keyword(db: Session, keyword_text: str) -> Keyword:
    keyword = db.query(Keyword).filter(Keyword.keyword == keyword_text).first()
    if keyword is not None:
        return keyword
    keyword = Keyword(keyword=keyword_text)
    db.add(keyword)
    db.flush()
    return keyword


def save_nlp_result(
    db: Session,
    *,
    user: User,
    title: str,
    text: str,
    nlp_result: Dict[str, object],
) -> Dict[str, int]:
    content = UserContent(user_id=user.user_id, title=title, transcript=text)
    db.add(content)
    db.flush()

    saved_keywords = 0
    for item in nlp_result.get("top_keywords", []):
        keyword = _get_or_create_keyword(db, item["keyword"])
        db.add(
            ContentKeyword(
                content_id=content.content_id,
                keyword_id=keyword.keyword_id,
                score=float(item["score"]),
            )
        )
        saved_keywords += 1

    summary_payload = {
        "top_keywords": nlp_result.get("top_keywords", []),
        "feature_attributes": nlp_result.get("feature_attributes", {}),
    }
    db.add(
        AnalysisResult(
            content_id=content.content_id,
            summary=json.dumps(summary_payload, ensure_ascii=False),
        )
    )
    log_system_event(
        db,
        user_id=user.user_id,
        action="nlp_extract_save",
        status="success",
        detail=f"content_id={content.content_id}, keywords={saved_keywords}",
    )
    db.commit()
    return {"content_id": content.content_id, "saved_keywords": saved_keywords}


def save_cluster_result(
    db: Session,
    *,
    user: User,
    clustering_result: Dict[str, object],
    items: List[Dict[str, object]],
) -> Dict[str, int]:
    run = ClusterRun(
        user_id=user.user_id,
        algorithm=str(clustering_result["algorithm"]),
        n_clusters=int(clustering_result["n_clusters"]),
        feature_dimension=int(clustering_result["feature_dimension"]),
        inertia=float(clustering_result["inertia"]),
    )
    db.add(run)
    db.flush()

    cluster_id_map: Dict[int, int] = {}
    for cluster in clustering_result.get("clusters", []):
        cluster_name = f"{cluster['label']}|{','.join(cluster['top_terms'][:3])}"
        cluster_row = db.query(Cluster).filter(Cluster.cluster_name == cluster_name).first()
        if cluster_row is None:
            cluster_row = Cluster(
                cluster_name=cluster_name,
                description=f"Top terms: {', '.join(cluster['top_terms'])}",
            )
            db.add(cluster_row)
            db.flush()
        cluster_id_map[int(cluster["cluster_id"])] = int(cluster_row.cluster_id)

    saved_memberships = 0
    items_by_position = {index + 1: item for index, item in enumerate(items)}
    for assignment in clustering_result.get("assignments", []):
        ref = items_by_position.get(int(assignment["item_id"]), {})
        db.add(
            ClusterMembership(
                run_id=run.run_id,
                cluster_id=cluster_id_map[int(assignment["cluster_id"])],
                content_id=ref.get("content_id"),
                dataset_id=ref.get("dataset_id"),
                item_text=assignment["text"],
                top_terms=",".join(assignment.get("top_terms", [])),
            )
        )
        saved_memberships += 1

    log_system_event(
        db,
        user_id=user.user_id,
        action=f"{clustering_result['algorithm']}_save",
        status="success",
        detail=f"run_id={run.run_id}, memberships={saved_memberships}",
    )
    db.commit()
    return {"run_id": run.run_id, "saved_memberships": saved_memberships}


def _collect_dataset_keyword_counts(db: Session, limit: int = 100) -> Counter[str]:
    rows = (
        db.query(DatasetContent.title, DatasetContent.transcript)
        .order_by(DatasetContent.trend_score.desc(), DatasetContent.created_at.desc())
        .limit(limit)
        .all()
    )
    counts: Counter[str] = Counter()
    for title, transcript in rows:
        text = " ".join(part for part in [title or "", transcript or ""] if part).strip()
        if not text:
            continue
        counts.update(filter_tokens(tokenize_text(text)))
    return counts


def build_keyword_recommendations(db: Session, existing_keywords: list[str], limit: int = 5) -> list[str]:
    blocked = {keyword.lower() for keyword in existing_keywords}
    dataset_counts = _collect_dataset_keyword_counts(db)
    recommendations: list[str] = []
    for keyword, _count in dataset_counts.most_common(50):
        if keyword.lower() in blocked:
            continue
        if len(keyword) <= 2:
            continue
        recommendations.append(keyword)
        if len(recommendations) >= limit:
            break
    return recommendations


def save_video_analysis_result(
    db: Session,
    *,
    user: User,
    filename: str,
    file_path: str,
    transcript: str,
    analysis_payload: Dict[str, object],
    nlp_result: Dict[str, object],
    recommendation_payload: Dict[str, object],
    raw_transcript: str | None = None,
    cleaned_transcript: str | None = None,
    commit: bool = True,
) -> Dict[str, object]:
    title = str(
        analysis_payload.get("analysis", {}).get("title")
        or os.path.splitext(filename)[0]
    )
    content = UserContent(
        user_id=user.user_id,
        title=title[:255],
        video_url=file_path,
        transcript=cleaned_transcript or transcript,
        raw_transcript=raw_transcript or transcript,
        cleaned_transcript=cleaned_transcript or transcript,
    )
    db.add(content)
    db.flush()
    content_id = content.content_id

    saved_keywords = 0
    top_keywords = nlp_result.get("top_keywords", [])
    for item in top_keywords:
        keyword = _get_or_create_keyword(db, item["keyword"])
        db.add(
            ContentKeyword(
                content_id=content.content_id,
                keyword_id=keyword.keyword_id,
                score=float(item["score"]),
            )
        )
        saved_keywords += 1

    recommendation_keywords = recommendation_payload.get("missing_keywords", [])
    recommended_duration = recommendation_payload.get("recommended_duration", {}).get("recommended_seconds")
    db.add(
        Recommendation(
            content_id=content.content_id,
            recommended_keywords=json.dumps(
                {
                    "missing_keywords": recommendation_payload.get("missing_keywords", []),
                    "hook_keywords": recommendation_payload.get("hook_keywords", []),
                    "domain": recommendation_payload.get("domain"),
                },
                ensure_ascii=False,
            ),
            recommended_duration=recommended_duration,
        )
    )
    classification = recommendation_payload.get("classification", {})
    if not isinstance(classification, dict):
        classification = {}
    classification_model = None
    classification_model_id = classification.get("model_id")
    if classification_model_id is not None:
        classification_model = (
            db.query(ClassificationModel)
            .filter(ClassificationModel.model_id == int(classification_model_id))
            .first()
        )
    if classification_model is None and "analysis_settings" not in analysis_payload:
        classification_model = (
            db.query(ClassificationModel)
            .filter(ClassificationModel.is_active.is_(True))
            .order_by(
                ClassificationModel.trained_at.desc(),
                ClassificationModel.model_id.desc(),
            )
            .first()
        )
    analysis_result = AnalysisResult(
            content_id=content.content_id,
            classification_model_id=(
                classification_model.model_id if classification_model else None
            ),
            taxonomy_version=classification.get("taxonomy_version"),
            taxonomy_leaf_key=classification.get("taxonomy_leaf_key"),
            category_level_1=classification.get("category_level_1"),
            category_level_2=classification.get("category_level_2"),
            category_level_3=classification.get("category_level_3"),
            classification_confidence=classification.get("confidence"),
            classification_is_unknown=bool(classification.get("is_unknown", False)),
            summary=json.dumps(
                {
                    "ai_analysis": analysis_payload,
                    "nlp_result": nlp_result,
                    "recommendation": recommendation_payload,
                },
                ensure_ascii=False,
            ),
        )
    db.add(analysis_result)
    db.flush()
    log_system_event(
        db,
        user_id=user.user_id,
        action="video_analyze_save",
        status="success",
        detail=f"content_id={content.content_id}, keywords={saved_keywords}",
    )
    if commit:
        db.commit()

    return {
        "content_id": content_id,
        "analysis_id": analysis_result.result_id,
        "saved_keywords": saved_keywords,
        "recommended_keywords": recommendation_keywords,
        "recommended_duration": recommended_duration,
    }
