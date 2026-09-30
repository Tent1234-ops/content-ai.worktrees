import json
import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Dict, List

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.models import (
    AnalysisResult,
    Cluster,
    ClusterMembership,
    ClusterRun,
    DatasetContent,
    SystemLog,
    TrendingItem,
    User,
    UserContent,
)
from app.services.nlp import EN_STOPWORDS, THAI_STOPWORDS, filter_tokens, tokenize_text
from app.services.live_trend_snapshots import load_latest_live_snapshot
from app.services.recommendation import (
    GENERIC_RECOMMENDATION_BLACKLIST,
    build_dataset_profiles,
    compare_dataset_profiles,
)
from app.services.trends import get_google_trending, get_tiktok_trending, get_youtube_trending


def _safe_scalar(query, default: int = 0) -> int:
    value = query.scalar()
    if value is None:
        return default
    return int(value)


def _topic_keywords_from_text(text: str) -> list[str]:
    tokens = filter_tokens(tokenize_text(text))
    return [token for token in tokens if len(token) > 2]


def _normalize_trend_item(item: object) -> dict:
    if isinstance(item, dict):
        return item
    if hasattr(item, "dict") and callable(getattr(item, "dict")):
        return item.dict()
    return {}


def _build_topic_scores_from_trends(items: list[object]) -> Counter[str]:
    scores: Counter[str] = Counter()
    for item in items:
        data = _normalize_trend_item(item)
        title = str(data.get("title", "")) or ""
        category = str(data.get("category", "")) or ""
        trend_weight = float(data.get("trend_score", 1.0) or 1.0)
        text = " ".join([title, category]).strip()
        if not text:
            continue
        if trend_weight <= 0:
            trend_weight = 1.0
        for token in _topic_keywords_from_text(text):
            scores[token] += min(trend_weight / 1000.0, 10.0)
    return scores


def _build_item_novelty_score(item: object, historical_counts: Counter[str]) -> tuple[float, int]:
    data = _normalize_trend_item(item)
    title = str(data.get("title", "")) or ""
    category = str(data.get("category", "")) or ""
    text = " ".join([title, category]).strip()

    if not text:
        return 0.0, 0

    keywords = _topic_keywords_from_text(text)
    if not keywords:
        return 0.0, 0

    novelty = 0.0
    total_history = 0
    for keyword in set(keywords):
        history_count = historical_counts.get(keyword, 0)
        novelty += 1.0 / (1.0 + history_count)
        total_history += history_count

    return novelty, total_history


def _rank_priority_items(items: list[object], historical_counts: Counter[str], limit: int = 10) -> list[Dict[str, object]]:
    ranked: list[Dict[str, object]] = []
    for item in items:
        data = _normalize_trend_item(item)
        title = str(data.get("title", "")) or ""
        if not title:
            continue
        category = str(data.get("category", "")) if data.get("category") is not None else None
        source_platform = data.get("source") or data.get("source_platform")
        trend_score = float(data.get("trend_score", 0.0) or 0.0)
        novelty, total_history = _build_item_novelty_score(item, historical_counts)
        views = int(data.get("views", 0) or 0)
        likes = int(data.get("likes", 0) or 0)
        comments = int(data.get("comments", 0) or 0)
        published_at = data.get("published_at")
        video_url = data.get("video_url") or None

        priority_score = trend_score + (novelty * 120.0) + min(views / 20000.0, 10.0)
        ranked.append(
            {
                "title": title,
                "category": category,
                "source_platform": source_platform,
                "video_url": video_url,
                "trend_score": trend_score,
                "priority_score": round(priority_score, 3),
                "novelty_score": round(novelty, 3),
                "views": views,
                "likes": likes,
                "comments": comments,
                "published_at": published_at.isoformat() if hasattr(published_at, "isoformat") else str(published_at) if published_at else None,
                "history_count": int(total_history),
            }
        )
    ranked.sort(key=lambda item: (-item["priority_score"], -item["trend_score"], item["title"].lower()))
    return [
        {
            "title": item["title"],
            "category": item["category"],
            "source_platform": item["source_platform"],
            "video_url": item["video_url"],
            "trend_score": item["trend_score"],
            "priority_score": item["priority_score"],
            "novelty_score": item["novelty_score"],
            "views": item["views"],
            "likes": item["likes"],
            "comments": item["comments"],
            "published_at": item["published_at"],
        }
        for item in ranked[:limit]
    ]


def _build_historical_topic_counts(db: Session, days: int = 30) -> Counter[str]:
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(DatasetContent.title, DatasetContent.transcript, DatasetContent.category)
        .filter(DatasetContent.created_at >= cutoff)
        .all()
    )
    counts: Counter[str] = Counter()
    for title, transcript, category in rows:
        text = " ".join(part for part in [title or "", transcript or "", category or ""] if part).strip()
        for token in _topic_keywords_from_text(text):
            counts[token] += 1
    return counts


def _rank_priority_topics(live_scores: Counter[str], historical_counts: Counter[str], limit: int = 10) -> list[Dict[str, object]]:
    ranked: list[Dict[str, object]] = []
    for keyword, score in live_scores.items():
        history = historical_counts.get(keyword, 0)
        priority_score = score + (history * 0.05)
        ranked.append({"keyword": keyword, "score": round(priority_score, 3), "history_count": int(history)})
    ranked.sort(key=lambda item: (-item["score"], item["keyword"]))
    return [{"keyword": item["keyword"], "score": item["score"]} for item in ranked[:limit]]


def _rank_emerging_topics(live_scores: Counter[str], historical_counts: Counter[str], limit: int = 10) -> list[Dict[str, object]]:
    ranked: list[Dict[str, object]] = []
    for keyword, score in live_scores.items():
        history = historical_counts.get(keyword, 0)
        emerging_score = score * (2.0 / (1.0 + history))
        ranked.append({"keyword": keyword, "score": round(emerging_score, 3), "history_count": int(history)})
    ranked.sort(key=lambda item: (-item["score"], item["history_count"], item["keyword"]))
    return [{"keyword": item["keyword"], "score": item["score"]} for item in ranked[:limit]]


def _rows_to_dashboard_trends(rows: list[DatasetContent]) -> list[Dict[str, object]]:
    trends: list[Dict[str, object]] = []
    for row in rows:
        trends.append(
            {
                "title": row.title,
                "category": row.category,
                "source_platform": row.source_platform,
                "video_url": row.video_url,
                "views": int(row.views or 0),
                "likes": int(row.likes or 0),
                "comments": int(row.comments or 0),
                "trend_score": float(row.trend_score or 0.0),
                "published_at": row.published_at.isoformat() if row.published_at else None,
            }
        )
    return trends


def _load_saved_trends(db: Session, source_prefix: str, limit: int) -> list[Dict[str, object]]:
    rows = (
        db.query(DatasetContent)
        .filter(DatasetContent.source_platform.like(f"{source_prefix}_live%"))
        .order_by(DatasetContent.created_at.desc())
        .limit(limit)
        .all()
    )
    if not rows:
        rows = (
            db.query(DatasetContent)
            .filter(DatasetContent.source_platform.like(f"{source_prefix}%"))
            .order_by(DatasetContent.created_at.desc())
            .limit(limit)
            .all()
        )
    return _rows_to_dashboard_trends(rows)


def _load_trending_items(db: Session, source_prefix: str, limit: int) -> list[Dict[str, object]]:
    rows = (
        db.query(TrendingItem)
        .filter(TrendingItem.source.like(f"{source_prefix}%"))
        .order_by(TrendingItem.fetched_at.desc())
        .limit(limit)
        .all()
    )
    items: list[Dict[str, object]] = []
    for row in rows:
        meta = {}
        if row.meta:
            try:
                meta = json.loads(row.meta)
            except Exception:
                meta = {}

        published_at = meta.get("published_at") or row.fetched_at
        if isinstance(published_at, str):
            try:
                published_at = datetime.fromisoformat(published_at)
            except Exception:
                published_at = row.fetched_at

        items.append(
            {
                "title": str(row.keyword or ""),
                "category": meta.get("category") or row.domain or "",
                "source_platform": row.source,
                "video_url": meta.get("video_url") or meta.get("url") or "",
                "views": int(meta.get("views") or 0),
                "likes": int(meta.get("likes") or 0),
                "comments": int(meta.get("comments") or 0),
                "trend_score": float(row.score or 0.0),
                "duration_seconds": int(meta.get("duration_seconds") or 0) if meta.get("duration_seconds") is not None else 0,
                "published_at": published_at.isoformat() if hasattr(published_at, "isoformat") else str(published_at),
                "source": row.source,
            }
        )
    return items


def _build_summary_trends(
    db: Session,
    source_prefix: str,
    region: str,
    trend_mode: str,
    limit: int,
) -> tuple[str, list[Dict[str, object]]]:
    if trend_mode == "live":
        snapshot = load_latest_live_snapshot(db, region=region, limit=limit)
        platform = snapshot.get("platforms", {}).get(source_prefix, {})
        return str(platform.get("mode") or "pending"), [
            dict(item) for item in platform.get("items", [])
        ]

    if trend_mode == "mock":
        if source_prefix == "youtube":
            return get_youtube_trending(region=region, limit=limit, mode="mock")
        if source_prefix == "google":
            return get_google_trending(region=region, limit=limit, mode="mock")
        if source_prefix == "tiktok":
            return get_tiktok_trending(region=region, limit=limit, mode="mock")

    cached_items = _load_trending_items(db=db, source_prefix=source_prefix, limit=limit)
    if cached_items:
        return "live", cached_items

    if source_prefix == "youtube":
        source_mode, items = get_youtube_trending(region=region, limit=limit, mode=trend_mode)
    elif source_prefix == "google":
        source_mode, items = get_google_trending(region=region, limit=limit, mode=trend_mode)
    elif source_prefix == "tiktok":
        source_mode, items = get_tiktok_trending(region=region, limit=limit, mode=trend_mode)
    else:
        return "mock", []

    normalized_items = [_normalize_trend_item(item) for item in items]
    if source_mode == "live" and normalized_items:
        return source_mode, normalized_items

    saved_items = _load_saved_trends(db=db, source_prefix=source_prefix, limit=limit)
    if saved_items:
        return "saved", saved_items
    if normalized_items:
        return source_mode, normalized_items

    return "mock", []


def _build_quick_recommendations(
    db: Session,
    user_id: int,
    live_items: list[Dict[str, object]],
    limit: int = 3,
) -> list[Dict[str, object]]:
    from app.database.models import UserContent

    latest = (
        db.query(UserContent)
        .filter(UserContent.user_id == user_id)
        .order_by(UserContent.created_at.desc())
        .first()
    )
    if not latest:
        return []

    content_text = " ".join(part for part in [latest.title or "", latest.transcript or ""] if part)
    existing_terms = set(_topic_keywords_from_text(content_text))
    candidate_scores: Counter[str] = Counter()
    for item in live_items:
        raw_text = " ".join(
            part for part in [item.get("title", ""), item.get("category", ""), item.get("source_platform", "")] if part
        )
        for token in _topic_keywords_from_text(raw_text):
            if token not in existing_terms:
                candidate_scores[token] += 1
    if not candidate_scores:
        return []

    return [
        {"keyword": keyword, "score": float(score)}
        for keyword, score in candidate_scores.most_common(limit)
    ]


def _extract_simple_terms(text: str) -> list[str]:
    if not text:
        return []
    raw_tokens = re.findall(r"[\u0E00-\u0E7Fa-zA-Z0-9]+", text.lower())
    tokens: list[str] = []
    for token in raw_tokens:
        if len(token) <= 1:
            continue
        if token.isdigit():
            continue
        if token in EN_STOPWORDS or token in THAI_STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def _build_quick_recommendations_from_summary(
    db: Session,
    user_id: int,
    combined_items: list[Dict[str, object]],
    limit: int = 3,
) -> list[Dict[str, object]]:
    from app.database.models import UserContent

    latest = (
        db.query(UserContent)
        .filter(UserContent.user_id == user_id)
        .order_by(UserContent.created_at.desc())
        .first()
    )
    if not latest:
        return []

    user_text = " ".join(part for part in [latest.title or "", latest.transcript or ""] if part)
    existing_terms = set(_extract_simple_terms(user_text))
    candidate_scores: Counter[str] = Counter()
    for item in combined_items:
        candidate_text = " ".join(
            part for part in [
                item.get("title", ""),
                item.get("category", ""),
                item.get("source_platform", ""),
            ]
            if part
        )
        for token in _extract_simple_terms(candidate_text):
            if token not in existing_terms:
                candidate_scores[token] += 1

    if not candidate_scores:
        return []

    recommendations = []
    for keyword, score in candidate_scores.most_common(limit * 2):
        if len(keyword) <= 2:
            continue
        if keyword in GENERIC_RECOMMENDATION_BLACKLIST:
            continue
        recommendations.append({"keyword": keyword, "score": float(score)})
        if len(recommendations) >= limit:
            break

    return recommendations


def _build_recommended_duration(live_items: list[Dict[str, object]]) -> int:
    durations = [
        int(item.get("duration_seconds", 0) or 0)
        for item in live_items
        if item.get("duration_seconds") and int(item.get("duration_seconds", 0) or 0) > 0
    ]
    if durations:
        return int(round(sum(durations) / len(durations)))
    return 60


def _build_platform_summaries_for_summary(
    db: Session,
    combined_items: list[Dict[str, object]],
) -> list[Dict[str, object]]:
    db_counts = {
        source: _safe_scalar(
            db.query(func.count(DatasetContent.dataset_id)).filter(DatasetContent.source_platform.like(f"{source}%"))
        )
        for source in ["youtube", "google", "tiktok"]
    }

    domain_groups: Dict[str, set[str]] = {"youtube": set(), "google": set(), "tiktok": set()}
    counts: Dict[str, int] = {"youtube": 0, "google": 0, "tiktok": 0}
    for item in combined_items:
        source = (item.get("source_platform") or item.get("source") or "").split("_")[0].lower()
        if source in counts:
            counts[source] += 1
            domain_groups[source].add(str(item.get("category") or item.get("domain") or "general"))

    summaries: list[Dict[str, object]] = []
    for source in ["youtube", "google", "tiktok"]:
        total_count = db_counts.get(source, 0) or counts.get(source, 0)
        if total_count == 0 and not domain_groups[source]:
            continue
        summaries.append(
            {
                "source": source,
                "dataset_count": total_count,
                "profile_count": len(domain_groups[source]),
                "domains": sorted(domain_groups[source]) if domain_groups[source] else [],
            }
        )
    return summaries


def build_dashboard_summary(
    db: Session,
    current_user: User,
    region: str,
    trend_mode: str,
    trend_limit: int,
) -> Dict[str, object]:
    youtube_source_mode, youtube_items = _build_summary_trends(
        db=db,
        source_prefix="youtube",
        region=region,
        trend_mode=trend_mode,
        limit=trend_limit,
    )
    google_source_mode, google_items = _build_summary_trends(
        db=db,
        source_prefix="google",
        region=region,
        trend_mode=trend_mode,
        limit=trend_limit,
    )
    tiktok_source_mode, tiktok_items = _build_summary_trends(
        db=db,
        source_prefix="tiktok",
        region=region,
        trend_mode=trend_mode,
        limit=trend_limit,
    )

    combined_items = youtube_items + google_items + tiktok_items
    # Kept as an empty compatibility field. Current rankings are exposed only
    # inside youtube_trends, google_trends, and tiktok_trends because provider
    # ranks and metrics are not comparable across platforms.
    top_trends: list[Dict[str, object]] = []
    quick_recommendations = _build_quick_recommendations_from_summary(db, current_user.user_id, combined_items, limit=3)
    recommended_duration = _build_recommended_duration(combined_items)

    source_distribution = [
        {"source_platform": source, "count": count}
        for source, count in {
            "youtube": _safe_scalar(
                db.query(func.count(DatasetContent.dataset_id)).filter(DatasetContent.source_platform.like("youtube%"))
            ),
            "google": _safe_scalar(
                db.query(func.count(DatasetContent.dataset_id)).filter(DatasetContent.source_platform.like("google%"))
            ),
            "tiktok": _safe_scalar(
                db.query(func.count(DatasetContent.dataset_id)).filter(DatasetContent.source_platform.like("tiktok%"))
            ),
        }.items()
    ]

    platform_summaries = _build_platform_summaries_for_summary(db, combined_items)

    database_analytics = {
        "total_users": _safe_scalar(db.query(func.count(User.user_id))),
        "total_dataset_contents": _safe_scalar(db.query(func.count(DatasetContent.dataset_id))),
        "total_cluster_runs": _safe_scalar(db.query(func.count(ClusterRun.run_id))),
        "my_contents": _safe_scalar(
            db.query(func.count(UserContent.content_id)).filter(UserContent.user_id == current_user.user_id)
        ),
        "my_analysis_results": _safe_scalar(
            db.query(func.count(AnalysisResult.result_id))
            .join(UserContent, UserContent.content_id == AnalysisResult.content_id)
            .filter(UserContent.user_id == current_user.user_id)
        ),
    }

    recent_analyses = []
    rows = (
        db.query(UserContent)
        .filter(UserContent.user_id == current_user.user_id)
        .order_by(UserContent.created_at.desc())
        .limit(3)
        .all()
    )
    for r in rows:
        recent_analyses.append(
            {
                "content_id": r.content_id,
                "title": r.title,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "video_url": r.video_url,
            }
        )

    return {
        "top_trends": top_trends,
        "quick_recommendations": quick_recommendations,
        "recommended_duration": recommended_duration,
        "recent_analyses": recent_analyses,
        "metrics": database_analytics,
        "platform_summaries": platform_summaries,
        "source_distribution": source_distribution,
        "youtube_trends": {
            "mode": youtube_source_mode,
            "region": region,
            "total": len(youtube_items),
            "items": youtube_items,
        },
        "google_trends": {
            "mode": google_source_mode,
            "region": region,
            "total": len(google_items),
            "items": google_items,
        },
        "tiktok_trends": {
            "mode": tiktok_source_mode,
            "region": region,
            "total": len(tiktok_items),
            "items": tiktok_items,
        },
    }


def _build_platform_summaries_from_distribution(source_distribution: list[Dict[str, object]]) -> list[Dict[str, object]]:
    grouped: Dict[str, Dict[str, object]] = {}
    for item in source_distribution:
        source_platform = str(item.get("source_platform") or "unknown")
        count = int(item.get("count") or 0)
        source_key = source_platform.split("_")[0].lower() if source_platform else "unknown"
        group = grouped.setdefault(source_key, {"dataset_count": 0, "domains": set()})
        group["dataset_count"] += count
        group["domains"].add(source_platform)

    return [
        {
            "source": source,
            "dataset_count": group["dataset_count"],
            "profile_count": 0,
            "domains": sorted(group["domains"]),
        }
        for source, group in grouped.items()
    ]


def _build_platform_summaries_from_trending_items(db: Session) -> list[Dict[str, object]]:
    rows = db.query(TrendingItem.source, TrendingItem.domain).all()
    grouped: Dict[str, Dict[str, object]] = {}
    for source, domain in rows:
        if not source:
            continue
        source_key = source.split("_")[0].lower()
        group = grouped.setdefault(source_key, {"dataset_count": 0, "domains": set()})
        group["dataset_count"] += 1
        if domain:
            group["domains"].add(domain)

    return [
        {
            "source": source,
            "dataset_count": group["dataset_count"],
            "profile_count": len(group["domains"]),
            "domains": sorted(group["domains"]),
        }
        for source, group in grouped.items()
    ]


def build_dashboard_overview(
    db: Session,
    current_user: User,
    region: str,
    trend_mode: str,
    trend_limit: int,
) -> Dict[str, object]:
    db_status = "ok"
    db_error = None

    metrics = {
        "total_users": 0,
        "active_users": 0,
        "total_user_contents": 0,
        "total_analysis_results": 0,
        "total_clusters": 0,
        "total_cluster_runs": 0,
        "total_cluster_memberships": 0,
        "total_dataset_contents": 0,
        "total_system_logs": 0,
        "my_contents": 0,
        "my_analysis_results": 0,
    }

    category_distribution: List[Dict[str, object]] = []
    cluster_distribution: List[Dict[str, object]] = []
    top_trends: List[Dict[str, object]] = []
    top_keywords: List[Dict[str, object]] = []
    source_distribution: List[Dict[str, object]] = []
    platform_summaries: List[Dict[str, object]] = []
    platform_comparison: List[Dict[str, object]] = []
    priority_topics: List[Dict[str, object]] = []
    emerging_topics: List[Dict[str, object]] = []
    priority_items: List[Dict[str, object]] = []

    trend_source_mode, trend_items = _build_summary_trends(
        db=db,
        source_prefix="youtube",
        region=region,
        trend_mode=trend_mode,
        limit=trend_limit,
    )
    google_source_mode, google_items = _build_summary_trends(
        db=db,
        source_prefix="google",
        region=region,
        trend_mode=trend_mode,
        limit=trend_limit,
    )
    tiktok_source_mode, tiktok_items = _build_summary_trends(
        db=db,
        source_prefix="tiktok",
        region=region,
        trend_mode=trend_mode,
        limit=trend_limit,
    )

    try:
        metrics["total_users"] = _safe_scalar(db.query(func.count(User.user_id)))
        metrics["active_users"] = _safe_scalar(db.query(func.count(User.user_id)).filter(User.is_active.is_(True)))
        metrics["total_user_contents"] = _safe_scalar(db.query(func.count(UserContent.content_id)))
        metrics["total_analysis_results"] = _safe_scalar(db.query(func.count(AnalysisResult.result_id)))
        metrics["total_clusters"] = _safe_scalar(db.query(func.count(Cluster.cluster_id)))
        metrics["total_cluster_runs"] = _safe_scalar(db.query(func.count(ClusterRun.run_id)))
        metrics["total_cluster_memberships"] = _safe_scalar(db.query(func.count(ClusterMembership.membership_id)))
        metrics["total_dataset_contents"] = _safe_scalar(db.query(func.count(DatasetContent.dataset_id)))
        metrics["total_system_logs"] = _safe_scalar(db.query(func.count(SystemLog.log_id)))
        metrics["my_contents"] = _safe_scalar(
            db.query(func.count(UserContent.content_id)).filter(UserContent.user_id == current_user.user_id)
        )
        metrics["my_analysis_results"] = _safe_scalar(
            db.query(func.count(AnalysisResult.result_id))
            .join(UserContent, UserContent.content_id == AnalysisResult.content_id)
            .filter(UserContent.user_id == current_user.user_id)
        )

        raw_categories = (
            db.query(DatasetContent.category, func.count(DatasetContent.dataset_id))
            .group_by(DatasetContent.category)
            .order_by(func.count(DatasetContent.dataset_id).desc())
            .limit(10)
            .all()
        )
        category_distribution = [
            {"category": category or "uncategorized", "count": int(count)}
            for category, count in raw_categories
        ]
        top_categories = list(category_distribution)

        raw_clusters = (
            db.query(Cluster.cluster_name, func.count(ClusterMembership.membership_id))
            .outerjoin(ClusterMembership, ClusterMembership.cluster_id == Cluster.cluster_id)
            .group_by(Cluster.cluster_id, Cluster.cluster_name)
            .order_by(func.count(ClusterMembership.membership_id).desc())
            .limit(10)
            .all()
        )
        cluster_distribution = [
            {"cluster_name": cluster_name, "count": int(count)}
            for cluster_name, count in raw_clusters
        ]

        raw_top_trends = (
            db.query(DatasetContent)
            .order_by(DatasetContent.trend_score.desc(), DatasetContent.views.desc(), DatasetContent.created_at.desc())
            .limit(10)
            .all()
        )
        top_trends = [
            {
                "dataset_id": row.dataset_id,
                "title": row.title,
                "category": row.category,
                "source_platform": row.source_platform,
                "video_url": row.video_url,
                "views": int(row.views or 0),
                "likes": int(row.likes or 0),
                "comments": int(row.comments or 0),
                "trend_score": float(row.trend_score or 0),
                "published_at": row.published_at.isoformat() if row.published_at else None,
            }
            for row in raw_top_trends
        ]

        raw_sources = (
            db.query(DatasetContent.source_platform, func.count(DatasetContent.dataset_id))
            .group_by(DatasetContent.source_platform)
            .order_by(func.count(DatasetContent.dataset_id).desc())
            .all()
        )
        source_distribution = [
            {"source_platform": source_platform or "unknown", "count": int(count)}
            for source_platform, count in raw_sources
        ]

        keyword_counts: Counter[str] = Counter()
        for row in raw_top_trends:
            text = " ".join(part for part in [row.title or "", row.transcript or "", row.category or ""] if part).strip()
            if not text:
                continue
            keyword_counts.update(filter_tokens(tokenize_text(text)))
        top_keywords = [
            {"keyword": keyword, "count": int(count)}
            for keyword, count in keyword_counts.most_common(10)
        ]

        youtube_profiles = build_dataset_profiles(db, source_prefix="youtube", limit=100)
        google_profiles = build_dataset_profiles(db, source_prefix="google", limit=100)
        tiktok_profiles = build_dataset_profiles(db, source_prefix="tiktok", limit=100)
        platform_summaries = [
            {
                "source": "youtube",
                "dataset_count": _safe_scalar(
                    db.query(func.count(DatasetContent.dataset_id)).filter(DatasetContent.source_platform.like("youtube%"))
                ),
                "profile_count": len(youtube_profiles),
                "domains": [profile["domain"] for profile in youtube_profiles],
            },
            {
                "source": "google",
                "dataset_count": _safe_scalar(
                    db.query(func.count(DatasetContent.dataset_id)).filter(DatasetContent.source_platform.like("google%"))
                ),
                "profile_count": len(google_profiles),
                "domains": [profile["domain"] for profile in google_profiles],
            },
            {
                "source": "tiktok",
                "dataset_count": _safe_scalar(
                    db.query(func.count(DatasetContent.dataset_id)).filter(DatasetContent.source_platform.like("tiktok%"))
                ),
                "profile_count": len(tiktok_profiles),
                "domains": [profile["domain"] for profile in tiktok_profiles],
            },
        ]

        if not platform_summaries and source_distribution:
            platform_summaries = _build_platform_summaries_from_distribution(source_distribution)

        if not platform_summaries or all(item["dataset_count"] == 0 for item in platform_summaries):
            trending_platforms = _build_platform_summaries_from_trending_items(db)
            if trending_platforms:
                for trending_platform in trending_platforms:
                    match_index = next(
                        (index for index, item in enumerate(platform_summaries) if item["source"] == trending_platform["source"]),
                        None,
                    )
                    if match_index is not None:
                        existing = platform_summaries[match_index]
                        if existing["dataset_count"] == 0:
                            existing["dataset_count"] = trending_platform["dataset_count"]
                            existing["profile_count"] = trending_platform["profile_count"]
                            existing["domains"] = trending_platform["domains"]
                    else:
                        platform_summaries.append(trending_platform)

        comparison = compare_dataset_profiles(db, left_source="youtube", right_source="google", limit=100)
        platform_comparison = [
            {
                "domain": item["domain"],
                "youtube_sample_size": int(item["left_sample_size"]),
                "google_sample_size": int(item["right_sample_size"]),
                "youtube_duration": item["left_duration"]["recommended_range"],
                "google_duration": item["right_duration"]["recommended_range"],
            }
            for item in comparison["comparisons"]
        ]

        live_topic_scores = _build_topic_scores_from_trends(trend_items + google_items + tiktok_items)
        historical_counts = _build_historical_topic_counts(db)
        priority_topics = _rank_priority_topics(live_topic_scores, historical_counts, limit=10)
        emerging_topics = _rank_emerging_topics(live_topic_scores, historical_counts, limit=10)
        priority_items = _rank_priority_items(trend_items + google_items + tiktok_items, historical_counts, limit=trend_limit)
    except SQLAlchemyError as exc:
        db_status = "degraded"
        db_error = exc.__class__.__name__
        top_categories = []
    else:
        top_categories = list(category_distribution)

    return {
        "db_status": db_status,
        "db_error": db_error,
        "user_role": current_user.role,
        "metrics": metrics,
        "category_distribution": category_distribution,
        "cluster_distribution": cluster_distribution,
        "top_trends": top_trends,
        "top_categories": top_categories,
        "top_keywords": top_keywords,
        "source_distribution": source_distribution,
        "platform_summaries": platform_summaries,
        "platform_comparison": platform_comparison,
        "priority_topics": priority_topics,
        "emerging_topics": emerging_topics,
        "priority_items": priority_items,
        "youtube_trends": {
            "mode": trend_source_mode,
            "region": region,
            "total": len(trend_items),
            "items": trend_items,
        },
        "google_trends": {
            "mode": google_source_mode,
            "region": region,
            "total": len(google_items),
            "items": google_items,
        },
        "tiktok_trends": {
            "mode": tiktok_source_mode,
            "region": region,
            "total": len(tiktok_items),
            "items": tiktok_items,
        },
    }


def build_dashboard_topic_insights(
    db: Session,
    current_user: User,
    region: str,
    trend_mode: str,
    trend_limit: int,
) -> Dict[str, object]:
    trend_source_mode, trend_items = _build_summary_trends(
        db=db,
        source_prefix="youtube",
        region=region,
        trend_mode=trend_mode,
        limit=trend_limit,
    )
    google_source_mode, google_items = _build_summary_trends(
        db=db,
        source_prefix="google",
        region=region,
        trend_mode=trend_mode,
        limit=trend_limit,
    )
    tiktok_source_mode, tiktok_items = _build_summary_trends(
        db=db,
        source_prefix="tiktok",
        region=region,
        trend_mode=trend_mode,
        limit=trend_limit,
    )

    live_topic_scores = _build_topic_scores_from_trends(trend_items + google_items + tiktok_items)
    historical_counts = _build_historical_topic_counts(db)
    return {
        "priority_items": _rank_priority_items(trend_items + google_items + tiktok_items, historical_counts, limit=trend_limit),
        "emerging_topics": _rank_emerging_topics(live_topic_scores, historical_counts, limit=trend_limit),
        "youtube_trends": {
            "mode": trend_source_mode,
            "region": region,
            "total": len(trend_items),
            "items": trend_items,
        },
        "google_trends": {
            "mode": google_source_mode,
            "region": region,
            "total": len(google_items),
            "items": google_items,
        },
        "tiktok_trends": {
            "mode": tiktok_source_mode,
            "region": region,
            "total": len(tiktok_items),
            "items": tiktok_items,
        },
    }
