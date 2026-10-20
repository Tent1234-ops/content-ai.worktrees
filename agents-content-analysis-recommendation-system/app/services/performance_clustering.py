"""Descriptive KPI clusters and shared-space transcript similarity, not prediction."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from numbers import Integral

import numpy as np
import sklearn
from fastapi import HTTPException
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from app.core.datetime_utils import utc_isoformat
from app.services.actionable_recommendations import _aliases, template_catalog
from app.services.contents import get_user_content_detail
from app.services.dataset_eligibility import reference_transcript_rows
from app.services.nlp import filter_tokens, tokenize_text
from app.services.recommendation_evidence import fingerprint, locate_terms, text_hash
from app.services.topic_comparisons import _confirmed_format, _load_observations
from app.services.view_metrics import YOUTUBE_PLAY_START_VIEW_V2, YOUTUBE_QUALIFIED_VIEW_V1
from app.services.performance_clustering_topics import saved_topic_cohort
from app.services.embedding_centroid import (
    compare_text_centroids, METHOD as TEXT_CENTROID_METHOD, POLICY as EMBEDDING_POLICY,
)


POLICY = {
    "version": "performance-clustering-v1", "k": 2, "random_state": 42, "n_init": 10,
    "features": ["views", "likes"], "transform": "log1p_then_standard_scaler",
    "naming_rule": "0.5 * centroid_z_log_views + 0.5 * centroid_z_log_likes",
    "minimum_references": 6, "minimum_cluster_size": 2, "minimum_tokens": 10,
    "minimum_unique_tokens": 3, "statistics_max_age_hours": 24,
    "top_k": 5, "minimum_similarity": 0.10, "minimum_similarity_margin": 0.03,
    "similarity_aggregation": "mean_top_k_same_k_for_both_groups",
    "vectorizer_fit": "reference_transcripts_only", "max_features": 12000,
    "similarity_thresholds_are": "unvalidated_descriptive_heuristics_not_classifier_thresholds",
}
LIMITATION = (
    "Low/High เปรียบเทียบเฉพาะคลิปอ้างอิงที่คัดเก็บและมียอดวิวถึงขั้นต่ำ "
    "ใช้ยอดสะสม ณ วันเก็บสถิติ ไม่ได้ควบคุมอายุคลิป รูปแบบ หรือขนาดช่อง "
    "คะแนนความคล้ายไม่ใช่โอกาสได้ยอดวิวสูง และไม่รับประกันผลหลังปรับคลิป"
)


def _tokens(text):
    return filter_tokens(tokenize_text(text or ""))


def _usable(tokens):
    return len(tokens) >= POLICY["minimum_tokens"] and len(set(tokens)) >= POLICY["minimum_unique_tokens"]


def _count(value):
    return isinstance(value, Integral) and not isinstance(value, bool) and 0 <= value <= 2**63 - 1


def name_centroids(centroids):
    """An exactly balanced views/likes tradeoff has no defensible Low/High order."""
    scores = np.asarray(centroids, dtype=float).mean(axis=1)
    if not np.isfinite(scores).all() or abs(scores[0] - scores[1]) <= 1e-10:
        return None
    high = int(np.argmax(scores))
    return {high: "high", 1 - high: "low"}


def _empty(category, minimum_views, now):
    return {
        "schema_version": POLICY["version"], "category": category,
        "as_of": utc_isoformat(now), "data_basis": "current_reference_data_not_saved_analysis_snapshot",
        "reference_count": 0, "eligible_count": 0, "minimum_views": minimum_views,
        "excluded_counts": {}, "channel_count": 0, "policy": dict(POLICY),
        "clustering": {"status": "insufficient_evidence", "reason": "not_enough_references",
                       "clusters": [], "features": ["views", "likes"], "k": 2},
        "content_similarity": {"status": "insufficient_evidence", "reason": "clustering_unavailable",
            "low_score": None, "high_score": None, "closest_group": None, "k_used": 0,
            "method": "tfidf_cosine_similarity", "supporting_dataset_ids": {}},
        "reference_videos": [], "recommendations": [], "high_keywords": [],
        "shared_keywords": [], "missing_keywords": [], "limitation": LIMITATION,
    }


def _topic_advice(category, text, records, labels, similarities):
    advice = []
    high = [i for i, level in enumerate(labels) if level == "high"]
    for template in template_catalog()["categories"].get(category, []):
        aliases = _aliases(template, category)
        matches = [(i, locate_terms(records[i]["transcript"], aliases)) for i in high]
        matches = [(i, hits) for i, hits in matches if hits]
        channels = {records[i]["channel_id"] for i, _ in matches}
        if len(matches) < 2 or len(channels) < 2:
            continue
        shared = bool(locate_terms(text, aliases))
        matches.sort(key=lambda pair: (-similarities[pair[0]], records[pair[0]]["dataset_id"]))
        advice.append({
            "topic": template["key"], "title": template["title"],
            "kind": "shared" if shared else "not_detected",
            "message": ("พบประเด็นนี้ในคลิปของคุณและคลิปกลุ่ม High สามารถใช้คลิปอ้างอิงประกอบการลงรายละเอียด"
                        if shared else "ยังไม่ตรวจพบประเด็นนี้ในข้อความของคุณ ลองพิจารณาเพิ่มเมื่อเกี่ยวข้องกับสิ่งที่รีวิวจริง"),
            "support_count": len(matches), "channel_count": len(channels),
            "references": [{"dataset_id": records[i]["dataset_id"],
                            "quote": hits[0]["quote"], "matched_text": hits[0]["matched_text"]}
                           for i, hits in matches[:3]],
        })
    return sorted(advice, key=lambda item: (-item["support_count"], item["topic"]))[:6]


def cluster_and_compare(records, *, user_transcript, category, minimum_views=25000,
                        now=None, input_available=True, comparison_method="embedding_centroid"):
    """Pure calculation; records contain reference KPIs only, never user KPIs."""
    if comparison_method not in {"tfidf", "embedding_centroid"}:
        raise ValueError("Unknown comparison_method")
    now = now or datetime.utcnow()
    result = _empty(category, minimum_views, now)
    if comparison_method == "embedding_centroid":
        result["policy"]["comparison_method"] = "embedding_centroid"
        result["policy"]["embedding"] = dict(EMBEDDING_POLICY)
        for key in ("top_k", "minimum_similarity", "minimum_similarity_margin",
                    "similarity_aggregation", "vectorizer_fit", "max_features",
                    "similarity_thresholds_are"):
            result["policy"].pop(key, None)
        result["content_similarity"]["method"] = TEXT_CENTROID_METHOD
    result["reference_count"] = len(records)
    eligible, tokens, exclusions = [], [], Counter()
    videos, documents = set(), set()
    for row in sorted(records, key=lambda r: r["dataset_id"]):
        words = _tokens(row.get("transcript", ""))
        reason = row.get("exclusion_reason")
        if not reason and (not _count(row.get("views")) or not _count(row.get("likes"))):
            reason = "missing_or_invalid_kpi"
        if not reason and (row.get("transcript_scope") != "full_video" or not _usable(words)):
            reason = "insufficient_reference_transcript"
        digest = text_hash(" ".join(words))
        if not reason and (row["video_id"] in videos or digest in documents):
            reason = "duplicate_video_or_transcript"
        if not reason and row["views"] < minimum_views:
            reason = "below_minimum_views"
        if reason:
            exclusions[reason] += 1
            continue
        videos.add(row["video_id"])
        documents.add(digest)
        eligible.append(row)
        tokens.append(words)
    versions = Counter(r["view_metric_version"] for r in eligible)
    if versions:
        # Select one comparable metric definition without consulting the user's text.
        version = sorted(versions, key=lambda key: (-versions[key], key))[0]
        keep = [i for i, row in enumerate(eligible) if row["view_metric_version"] == version]
        exclusions["incompatible_view_metric"] += len(eligible) - len(keep)
        eligible, tokens = [eligible[i] for i in keep], [tokens[i] for i in keep]
        result["view_metric_version"] = version
    result.update(eligible_count=len(eligible), excluded_counts={k: v for k, v in exclusions.items() if v},
                  channel_count=len({r["channel_id"] for r in eligible}))
    result["data_fingerprint"] = fingerprint({"policy": result["policy"], "comparison_method": comparison_method, "minimum_views": minimum_views,
        "references": [{k: v for k, v in r.items() if k != "transcript"} for r in eligible],
        "transcript_hashes": [text_hash(r["transcript"]) for r in eligible],
        "user_transcript_sha256": text_hash(user_transcript), "sklearn": sklearn.__version__})
    result["format_counts"] = dict(Counter(r.get("format", "unknown") for r in eligible))
    if len(eligible) < POLICY["minimum_references"]:
        return result
    raw = np.asarray([[r["views"], r["likes"]] for r in eligible], dtype=float)
    logged = np.log1p(raw)
    if len(np.unique(logged, axis=0)) < 2:
        result["clustering"]["reason"] = "identical_kpi_points"
        return result
    scaler = StandardScaler()
    scaled = scaler.fit_transform(logged)
    with threadpool_limits(limits=1):
        fitted = KMeans(n_clusters=2, random_state=42, n_init=10).fit(scaled)
    counts = np.bincount(fitted.labels_, minlength=2)
    if min(counts) < POLICY["minimum_cluster_size"]:
        result["clustering"]["reason"] = "cluster_too_small"
        return result
    names = name_centroids(fitted.cluster_centers_)
    if names is None:
        result["clustering"].update(status="inconclusive", reason="centroid_order_tie")
        return result
    levels = [names[int(label)] for label in fitted.labels_]
    inverse = np.expm1(scaler.inverse_transform(fitted.cluster_centers_))
    clusters = []
    for cluster_id, level in sorted(names.items(), key=lambda pair: pair[1] == "high"):
        indices = np.flatnonzero(fitted.labels_ == cluster_id)
        values = raw[indices]
        clusters.append({"cluster_id": cluster_id, "performance_level": level,
            "video_count": len(indices), "average_views": float(values[:, 0].mean()),
            "median_views": float(np.median(values[:, 0])), "average_likes": float(values[:, 1].mean()),
            "median_likes": float(np.median(values[:, 1])),
            "centroid": {"scaled_log_views": float(fitted.cluster_centers_[cluster_id, 0]),
                         "scaled_log_likes": float(fitted.cluster_centers_[cluster_id, 1]),
                         "inverse_views": float(inverse[cluster_id, 0]),
                         "inverse_likes": float(inverse[cluster_id, 1]),
                         "performance_score": float(fitted.cluster_centers_[cluster_id].mean())},
            "dataset_ids": [eligible[i]["dataset_id"] for i in indices]})
    result["clustering"].update(status="ready", reason=None, clusters=clusters,
        scaler_mean=scaler.mean_.tolist(), scaler_scale=scaler.scale_.tolist(),
        inertia=float(fitted.inertia_), sklearn_version=sklearn.__version__)
    result["reference_videos"] = [dict(
        {k: v for k, v in row.items() if k not in {"transcript", "exclusion_reason"}},
        cluster_id=int(fitted.labels_[i]), performance_level=levels[i], similarity=None)
        for i, row in enumerate(eligible)]
    user_tokens = _tokens(user_transcript)
    similarity = result["content_similarity"]
    if not input_available or not _usable(user_tokens):
        similarity["reason"] = "insufficient_user_transcript"
        return result
    if comparison_method == "embedding_centroid":
        # KPI K-Means remains unchanged. Compare semantic text centroids in an
        # entirely separate feature space, without using user Views/Likes.
        compared = compare_text_centroids(eligible, levels, user_transcript)
        reference_scores = compared.pop("reference_scores")
        similarity.update(compared)
        for row, score in zip(result["reference_videos"], reference_scores):
            row["similarity"] = score
        if similarity["status"] == "ready":
            result["recommendations"] = _topic_advice(
                category, user_transcript, eligible, levels, reference_scores)
        return result

    vectorizer = TfidfVectorizer(tokenizer=str.split, token_pattern=None, lowercase=False,
        ngram_range=(1, 2), max_features=POLICY["max_features"], sublinear_tf=True)
    try:
        matrix = vectorizer.fit_transform([" ".join(words) for words in tokens])
        user_vector = vectorizer.transform([" ".join(user_tokens)])
    except ValueError:
        similarity["reason"] = "empty_vocabulary"
        return result
    if user_vector.nnz == 0:
        similarity["reason"] = "no_shared_features"
        return result
    scores = cosine_similarity(user_vector, matrix).ravel().clip(0, 1)
    k = min(POLICY["top_k"], int(counts.min()))
    group_scores = {}
    for level in ("low", "high"):
        indices = [i for i, name in enumerate(levels) if name == level and matrix[i].nnz]
        if len(indices) < k:
            similarity["reason"] = "group_without_comparable_features"
            return result
        indices.sort(key=lambda i: (-scores[i], eligible[i]["dataset_id"]))
        selected = indices[:k]
        group_scores[level] = float(scores[selected].mean())
        similarity["supporting_dataset_ids"][level] = [eligible[i]["dataset_id"] for i in selected]
    similarity.update(low_score=group_scores["low"], high_score=group_scores["high"],
                      k_used=k, feature_count=matrix.shape[1])
    for i, row in enumerate(result["reference_videos"]):
        row["similarity"] = float(scores[i])
    if max(group_scores.values()) < POLICY["minimum_similarity"]:
        similarity["reason"] = "low_similarity"
        return result
    if abs(group_scores["high"] - group_scores["low"]) < POLICY["minimum_similarity_margin"]:
        similarity.update(status="inconclusive", reason="similar_scores")
        return result
    similarity.update(status="ready", reason=None, closest_group=max(group_scores, key=group_scores.get))
    high_indices = [i for i, level in enumerate(levels) if level == "high"]
    terms = vectorizer.get_feature_names_out()
    weights = np.asarray(matrix[high_indices].mean(axis=0)).ravel()
    top_terms = sorted(range(len(terms)), key=lambda i: (-weights[i], terms[i]))
    keywords = [{"term": str(terms[i]), "dataset_ids": [eligible[j]["dataset_id"]
                 for j in high_indices if matrix[j, i] > 0], "shared": bool(user_vector[0, i])}
                for i in top_terms[:12] if weights[i] > 0]
    result["high_keywords"] = keywords
    result["shared_keywords"] = [item["term"] for item in keywords if item["shared"]]
    result["missing_keywords"] = [item["term"] for item in keywords if not item["shared"]]
    result["recommendations"] = _topic_advice(category, user_transcript, eligible, levels, scores)
    return result


def performance_for_content(db, *, user_id, content_id, minimum_views, now=None,
                            topic_id=None, group_index=None, comparison_method="embedding_centroid"):
    now = now or datetime.utcnow()
    content = get_user_content_detail(db, user_id=user_id, content_id=content_id)
    if content is None:
        raise HTTPException(status_code=404, detail="Content not found")
    recommendation = content.get("recommendation") or {}
    classification = recommendation.get("classification") or {}
    category = classification.get("taxonomy_leaf_key") or classification.get("domain") or "unknown"
    context = (recommendation.get("evidence_bundle") or {}).get("input") or {}
    accepted = (classification.get("acceptance") or {}).get("accepted")
    if topic_id is not None:
        if (category not in {"phone", "camera", "laptop"} or
                classification.get("is_unknown") is not False or accepted is not True):
            raise HTTPException(status_code=422, detail="Classification is not accepted")
        # Never substitute a whole-category cohort when the requested saved topic
        # cohort is missing, invalid, or contains too few KPI-complete videos.
        cohort = saved_topic_cohort(recommendation.get("evidence_bundle") or {},
                                   category, topic_id, group_index if group_index is not None else 0)
        if cohort is None:
            raise HTTPException(status_code=422, detail="Saved topic/group evidence is unavailable or invalid")
        allowed = {r["dataset_id"]: r for r in cohort["passing_records"]}
        rows = reference_transcript_rows(db, domain=category, now=now)
        by_id = {row.dataset_id: row for row in rows if row.dataset_id in allowed}
        records = []
        for saved in cohort["passing_records"]:
            row = by_id.get(saved["dataset_id"])
            observation = saved["latest_observation"]
            reason = None
            if row is None or row.source_youtube_id != saved["video_id"]:
                reason = "saved_reference_unavailable"
            elif text_hash(row.transcript) != row.transcript_sha256 or row.transcript_sha256 != saved["transcript_sha256"]:
                reason = "transcript_hash_mismatch"
            records.append({
                "dataset_id": saved["dataset_id"], "video_id": saved["video_id"],
                "channel_id": saved["channel_id"], "channel_title": saved.get("channel_title"),
                "title": row.title if row is not None else saved["video_id"],
                "url": saved.get("url") or f'https://www.youtube.com/watch?v={saved["video_id"]}',
                "published_at": saved["published_at"], "format": cohort["format"],
                "transcript": row.transcript if row is not None else "",
                "transcript_scope": row.transcript_scope if row is not None else "",
                "views": observation["views"], "likes": observation.get("likes"),
                "statistics_captured_at": observation["observed_at"],
                "observation_id": observation["observation_id"],
                "view_metric_version": observation["view_metric_version"],
                "exclusion_reason": reason,
            })
        result = cluster_and_compare(records,
            user_transcript=content.get("raw_transcript") or content.get("transcript") or "",
            category=category, minimum_views=cohort["threshold_views"] + 1, now=now,
            input_available=context.get("availability") == "available",
            comparison_method=comparison_method)
        # The original rule is strictly greater than the frozen benchmark.
        result["minimum_views"] = cohort["threshold_views"]
        result["selection"] = {
            "mode": "saved_topic_group_passing_only",
            "topic_id": topic_id, "topic_title": cohort["topic_title"],
            "group_index": cohort["group_index"], "format": cohort["format"],
            "age_group": cohort["age_group"], "as_of": cohort["as_of"],
            "threshold_views": cohort["threshold_views"],
            "comparison_rule": "views_strictly_greater_than_frozen_benchmark",
            "topic_sample_size": cohort["sample_size"],
            "passing_count": cohort["passing_count"],
        }
        result.update(content_id=content_id, analysis_id=content.get("analysis_id"))
        return result
    if category not in {"phone", "camera", "laptop"} or classification.get("is_unknown") is not False or accepted is not True:
        result = _empty(category, minimum_views, now)
        result["clustering"].update(status="withheld", reason="classification_not_accepted")
    else:
        rows = reference_transcript_rows(db, domain=category, now=now)
        observations = _load_observations(db, [r.dataset_id for r in rows], now)
        records = []
        for row in rows:
            history = [o for o in observations.get(row.dataset_id, []) if o.video_id == row.source_youtube_id]
            latest = history[-1] if history else None
            reason = None
            if latest is None or latest.observed_at < now - timedelta(hours=POLICY["statistics_max_age_hours"]):
                reason = "no_recent_statistics"
            elif latest.status not in {"complete", "partial"}:
                reason = "latest_statistics_unavailable"
            elif latest.view_metric_version not in {YOUTUBE_PLAY_START_VIEW_V2, YOUTUBE_QUALIFIED_VIEW_V1}:
                reason = "unknown_view_metric"
            elif latest.observed_at < row.published_at:
                reason = "statistics_before_publication"
            elif text_hash(row.transcript) != row.transcript_sha256:
                reason = "transcript_hash_mismatch"
            records.append({"dataset_id": row.dataset_id, "video_id": row.source_youtube_id,
                "title": row.title, "channel_id": row.source_channel_id, "channel_title": row.source_creator,
                "url": f"https://www.youtube.com/watch?v={row.source_youtube_id}",
                "published_at": utc_isoformat(row.published_at), "format": _confirmed_format(row)[0],
                "transcript": row.transcript, "transcript_scope": row.transcript_scope,
                "transcript_sha256": row.transcript_sha256,
                "views": latest.views if latest else None, "likes": latest.likes if latest else None,
                "statistics_captured_at": utc_isoformat(latest.observed_at) if latest else None,
                "observation_id": latest.observation_id if latest else None,
                "view_metric_version": latest.view_metric_version if latest else None,
                "exclusion_reason": reason})
        result = cluster_and_compare(records, user_transcript=content.get("raw_transcript") or content.get("transcript") or "",
            category=category, minimum_views=minimum_views, now=now,
            input_available=context.get("availability") == "available",
            comparison_method=comparison_method)
    result.update(content_id=content_id, analysis_id=content.get("analysis_id"))
    return result
