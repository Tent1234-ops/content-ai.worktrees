import json
from typing import Any

from sqlalchemy.orm import Session

from app.database.models import AnalysisResult, ClipRevisionComparison, Recommendation, UserContent
from app.services.saved_recommendations import stored_recommendation
from app.services.recommendation_evidence import fingerprint


def _latest_analysis(content: UserContent) -> AnalysisResult | None:
    rows = sorted(content.analysis_results, key=lambda item: (item.created_at, item.result_id), reverse=True)
    return rows[0] if rows else None


def _latest_recommendation(content: UserContent) -> Recommendation | None:
    rows = sorted(content.recommendations, key=lambda item: item.created_at, reverse=True)
    return rows[0] if rows else None


def _parse_json_text(raw_text: str | None) -> dict[str, Any]:
    if not isinstance(raw_text, str) or not raw_text:
        return {}
    try:
        data = json.loads(raw_text)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _preview_text(text: str | None, max_length: int = 120) -> str | None:
    if not text:
        return None
    return text[:max_length] + "..." if len(text) > max_length else text


def serialize_content_history_item(content: UserContent) -> dict[str, Any]:
    analysis_row = _latest_analysis(content)
    recommendation_row = _latest_recommendation(content)

    analysis_summary = _parse_json_text(analysis_row.summary if analysis_row else None)
    recommendation_summary = _parse_json_text(recommendation_row.recommended_keywords if recommendation_row else None)
    recommendation_payload = analysis_summary.get("recommendation", {})

    missing_keywords = recommendation_summary.get("missing_keywords", [])
    hook_keywords = recommendation_summary.get("hook_keywords", [])

    return {
        "content_id": content.content_id,
        "title": content.title,
        "created_at": content.created_at,
        "video_url": content.video_url,
        "transcript_preview": _preview_text(
            content.cleaned_transcript or content.transcript
        ),
        "domain": recommendation_summary.get("domain")
        or recommendation_payload.get("domain")
        or analysis_summary.get("ai_analysis", {}).get("analysis", {}).get("domain"),
        "recommended_duration": recommendation_row.recommended_duration if recommendation_row else None,
        "recommended_keywords": [
            item["keyword"] if isinstance(item, dict) else str(item)
            for item in missing_keywords[:5]
        ],
        "hook_keywords": [
            item["keyword"] if isinstance(item, dict) else str(item)
            for item in hook_keywords[:5]
        ],
    }


def list_user_contents(db: Session, *, user_id: int, limit: int = 20, offset: int = 0) -> tuple[int, list[dict[str, Any]]]:
    query = db.query(UserContent).filter(UserContent.user_id == user_id)
    total = query.count()
    rows = query.order_by(UserContent.created_at.desc()).offset(offset).limit(limit).all()
    return total, [serialize_content_history_item(row) for row in rows]


def get_user_content_detail(db: Session, *, user_id: int, content_id: int) -> dict[str, Any] | None:
    content = (
        db.query(UserContent)
        .filter(UserContent.user_id == user_id, UserContent.content_id == content_id)
        .first()
    )
    if content is None:
        return None

    analysis_row = _latest_analysis(content)
    analysis_summary = _parse_json_text(analysis_row.summary if analysis_row else None)
    recommendation_payload = stored_recommendation(content, analysis_row)
    revision_row = (
        db.query(ClipRevisionComparison)
        .filter_by(user_id=user_id, child_content_id=content_id, status="completed")
        .order_by(ClipRevisionComparison.completed_at.desc())
        .first()
    )
    revision_comparison = None
    if revision_row is not None:
        parsed_comparison = _parse_json_text(
            getattr(revision_row, "comparison_result_json", None)
        )
        revision_comparison = parsed_comparison or None
    return {
        "content_id": content.content_id,
        "analysis_id": analysis_row.result_id if analysis_row else None,
        "recommendation_fingerprint": fingerprint(recommendation_payload),
        "title": content.title,
        "created_at": content.created_at,
        "video_url": content.video_url,
        "transcript": content.cleaned_transcript or content.transcript,
        "raw_transcript": content.raw_transcript or content.transcript,
        "cleaned_transcript": content.cleaned_transcript or content.transcript,
        "analysis": analysis_summary.get("ai_analysis", {}),
        "nlp_result": analysis_summary.get("nlp_result", {}),
        "recommendation": recommendation_payload,
        "revision_comparison": revision_comparison,
    }
