import os
import shutil
import uuid
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.deps import require_roles
from app.core.datetime_utils import utc_isoformat
from app.database.db import SessionLocal, get_db
from sqlalchemy.orm import Session
from app.database.models import AnalysisResult, ClipRevisionComparison, User, UserContent
from app.services.analysis_settings import capture_analysis_settings, get_analysis_settings
from app.services.ai_pipeline import analyze_video as pipeline_analyze
from app.services.classification import classify_text_domain
from app.services.jobs import enqueue, update_current_job
from app.services.media_validation import (
    MediaValidationError,
    probe_media_duration_seconds,
    validate_user_upload_duration,
)
from app.services.nlp import normalize_text_for_nlp
from app.services.persistence import save_video_analysis_result
from app.services.recommendation import (
    build_classified_user_signal_snapshot,
    build_recommendation_from_analysis_data,
)
from app.services.taxonomy import normalize_taxonomy_leaf
from app.services.recommendation_evidence import fingerprint, user_context
from app.services.outcome_evidence import attach_outcome_evidence_explanations
from app.services.outcome_inference import assess_outcome
from app.services.revision_comparisons import (
    build_revision_comparison,
    create_revision_job,
    get_revision_job,
    prepare_retry,
    revision_job_response,
    update_revision_job,
    claim_revision_job,
)

router = APIRouter()


def _save_upload(file: UploadFile) -> str:
    os.makedirs("videos", exist_ok=True)
    safe_name = Path(file.filename or "upload.mp4").name
    file_path = os.path.join("videos", f"{uuid.uuid4().hex}_{safe_name}")
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return file_path


def _save_validated_upload(file: UploadFile, *, max_duration_seconds: int = 300) -> str:
    file_path = _save_upload(file)
    try:
        validate_user_upload_duration(file_path, max_duration_seconds=max_duration_seconds)
    except MediaValidationError as exc:
        Path(file_path).unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return file_path


def _file_sha256(file_path: str) -> str:
    digest = hashlib.sha256()
    with open(file_path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verified_outcome_input_metadata(
    file_path: str, *, confirmed_format: str | None, reference_age_context: str | None,
) -> dict:
    confirmed_format = str(confirmed_format or "").strip()
    reference_age_context = str(reference_age_context or "").strip()
    if not confirmed_format and not reference_age_context:
        return {}
    if confirmed_format not in {"short_form", "long_form"}:
        raise HTTPException(422, "confirmed_format must be short_form or long_form")
    if not re.fullmatch(r"[a-z0-9_]{3,40}", reference_age_context):
        raise HTTPException(422, "reference_age_context is required and invalid")
    try:
        duration = probe_media_duration_seconds(file_path)
    except MediaValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "confirmed_format": confirmed_format,
        "confirmed_format_provenance": "creator_upload_declaration",
        "duration_seconds": duration,
        "reference_age_context": reference_age_context,
        "reference_age_context_provenance": "explicit_requested_reference_context",
    }


def _outcome_evidence_links(recommendation: dict) -> tuple[list[str], list[dict]]:
    actions = (recommendation.get("actionable_recommendations") or {}).get("items", [])
    topic_ids = [
        str(item.get("evidence_topic_id")) for item in actions
        if isinstance(item, dict) and item.get("evidence_topic_id")
    ]
    comparisons = {
        str(item.get("evidence_topic_id")): item
        for item in ((recommendation.get("evidence_bundle") or {})
                     .get("topic_comparisons") or {}).get("items", [])
        if isinstance(item, dict) and item.get("evidence_topic_id")
    }
    pointers = []
    for item in actions:
        if not isinstance(item, dict) or not item.get("evidence_topic_id"):
            continue
        topic_id = str(item["evidence_topic_id"])
        pointers.append({
            "evidence_topic_id": topic_id,
            "canonical_topic": item.get("template_key"),
            "supporting_dataset_row_ids": list(item.get("supporting_dataset_row_ids") or []),
            "comparison_data_fingerprint": (comparisons.get(topic_id) or {}).get("data_fingerprint"),
        })
    return list(dict.fromkeys(topic_ids)), pointers


def _build_recommendation(db, *, filename: str, result: dict, settings_snapshot: dict | None = None,
                          evidence_as_of=None) -> tuple[dict, dict]:
    update_current_job(stage="classifying", progress=62, message="Classifying clip type")
    raw_transcript = str(
        result.get("raw_transcript")
        or result.get("transcript")
        or ""
    )
    cleaned_transcript = str(
        result.get("cleaned_transcript")
        or normalize_text_for_nlp(raw_transcript)
    )
    result["raw_transcript"] = raw_transcript
    result["cleaned_transcript"] = cleaned_transcript
    analysis = result.get("analysis", {})
    stt_meta = analysis.get("stt_meta", {})
    filename_fallback = stt_meta.get("transcript_source") == "fallback_filename"
    classification_transcript = "" if filename_fallback else cleaned_transcript
    hook_transcript = (
        ""
        if filename_fallback
        else str(
            analysis.get("hook_cleaned_transcript")
            or analysis.get("hook_transcript")
            or ""
        )
    )
    classification = classify_text_domain(
        db,
        title=None,
        text=classification_transcript,
        source_prefix="youtube",
        profile_limit=80,
        require_active_model=True,
        **({"model_snapshot": settings_snapshot["classification_model"]} if settings_snapshot else {}),
    )
    if filename_fallback:
        classification["input_source"] = "filename_fallback"
        classification["warning"] = stt_meta.get("warning") or (
            "Speech-to-text failed; the filename was not used for classification."
        )
    selected_domain = normalize_taxonomy_leaf(
        str(classification.get("taxonomy_leaf_key") or classification.get("domain"))
    )
    user_signals = build_classified_user_signal_snapshot(
        text=classification_transcript,
        hook_text=hook_transcript,
        taxonomy_leaf_key=selected_domain,
        max_keywords=10,
    )
    nlp_result = user_signals["nlp_result"]
    user_keywords = list(user_signals["user_keywords"])
    hook_terms = list(user_signals["hook_terms"])

    for legacy_key in (
        "product",
        "features",
        "entity_keywords",
        "context_keywords",
        "analysis_quality",
    ):
        analysis.pop(legacy_key, None)
    analysis["domain"] = selected_domain
    analysis["domain_source"] = str(classification.get("method") or "unknown")
    analysis["taxonomy_leaf_key"] = selected_domain
    analysis["category_level_1"] = classification.get("category_level_1")
    analysis["category_level_2"] = classification.get("category_level_2")
    analysis["category_level_3"] = classification.get("category_level_3")
    analysis["classification_confidence"] = float(
        classification.get("confidence") or 0.0
    )
    analysis["top_keywords"] = list(nlp_result.get("top_keywords", []))
    analysis["all_keywords"] = list(user_signals["content_keywords"])
    analysis["content_keywords"] = list(user_signals["content_keywords"])
    # Hook terms are observed in the uploaded clip; hook keywords are suggestions.
    analysis.pop("hook_keywords", None)
    analysis["hook_terms"] = list(user_signals["hook_terms"])
    analysis["comparable_keywords"] = list(user_signals["comparable_keywords"])
    analysis["comparable_keyword_evidence"] = list(
        user_signals["comparable_keyword_evidence"]
    )
    analysis["comparison_dimensions"] = list(
        user_signals["comparison_dimensions"]
    )
    analysis["dimension_status"] = list(user_signals["dimension_status"])

    update_current_job(stage="recommending", progress=76, message="Comparing with high-engagement dataset")
    recommendation = build_recommendation_from_analysis_data(
        db,
        as_of=evidence_as_of,
        domain=selected_domain,
        user_keywords=user_keywords,
        dimension_status=list(user_signals["dimension_status"]),
        hook_terms=hook_terms,
        transcript=classification_transcript,
        source_prefix="youtube",
        profile_limit=80,
        evidence_context=user_context(
            transcript=classification_transcript, raw_transcript=raw_transcript,
            stt_meta=stt_meta, segments=result.get("transcript_segments"),
            classification=classification, analysis_settings=settings_snapshot),
    )
    recommendation["classification"] = classification
    recommendation["content_keywords"] = list(user_signals["content_keywords"])[:12]
    recommendation["hook_terms"] = hook_terms[:8]
    recommendation["comparable_keywords"] = list(
        user_signals["comparable_keywords"]
    )
    recommendation["comparable_keyword_evidence"] = list(
        user_signals["comparable_keyword_evidence"]
    )
    recommendation["keyword_sets"] = {
        "content": recommendation["content_keywords"],
        "hook": recommendation["hook_terms"],
        "comparable": recommendation["comparable_keywords"],
    }
    if isinstance(recommendation.get("evidence"), dict):
        recommendation["evidence"]["transcript_source"] = stt_meta.get("transcript_source") or "unknown"
        recommendation["evidence"]["transcript_scope"] = stt_meta.get("transcript_scope") or "unknown"
        recommendation["evidence"]["hook_seconds_analyzed"] = stt_meta.get("hook_seconds_analyzed")
        recommendation["evidence"]["stt_fallback_reason"] = stt_meta.get("fallback_reason")
        recommendation["evidence"]["warning"] = stt_meta.get("warning")
    evidence_topic_ids, evidence_pointers = _outcome_evidence_links(recommendation)
    evidence_input = (recommendation.get("evidence_bundle") or {}).get("input") or {}
    outcome_assessment = assess_outcome(
        db,
        category=selected_domain,
        classification=classification,
        evidence_context=evidence_input,
        # This context must come from verified upload metadata.  Duration alone
        # is deliberately not used to infer Shorts/long-form format.
        input_metadata=result.get("outcome_context") if isinstance(result.get("outcome_context"), dict) else {},
        evidence_topic_ids=evidence_topic_ids,
        evidence_pointers=evidence_pointers,
    )
    attach_outcome_evidence_explanations(recommendation, outcome_assessment)
    result["outcome_assessment"] = outcome_assessment
    return recommendation, nlp_result


def analyze_video_job(file_path: str, filename: str, user_id: int | None = None, *,
                      settings_snapshot: dict | None = None,
                      outcome_input_metadata: dict | None = None) -> dict:
    db = SessionLocal()
    try:
        settings_snapshot = settings_snapshot or capture_analysis_settings(db)
        update_current_job(stage="extracting_audio", progress=18, message="Preparing full video audio")
        result = pipeline_analyze(
            file_path,
            display_name=filename,
            hook_duration_seconds=settings_snapshot["hook_duration_seconds"],
            asr_model_size=settings_snapshot["asr_model"],
        )
        result["analysis_settings"] = settings_snapshot
        result["outcome_context"] = dict(outcome_input_metadata or {})
        update_current_job(stage="classifying", progress=62, message="Classifying clip type")
        recommendation, _nlp_result = _build_recommendation(db, filename=filename, result=result, settings_snapshot=settings_snapshot)
        result["recommendation"] = recommendation
        return result
    finally:
        db.close()


def analyze_and_save_video_job(file_path: str, filename: str, user_id: int, *,
                               settings_snapshot: dict | None = None,
                               outcome_input_metadata: dict | None = None) -> dict:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        if user is None:
            raise RuntimeError("User not found for analysis job.")

        settings_snapshot = settings_snapshot or capture_analysis_settings(db)
        update_current_job(stage="extracting_audio", progress=18, message="Preparing full video audio")
        result = pipeline_analyze(
            file_path,
            display_name=filename,
            hook_duration_seconds=settings_snapshot["hook_duration_seconds"],
            asr_model_size=settings_snapshot["asr_model"],
        )
        result["analysis_settings"] = settings_snapshot
        result["outcome_context"] = dict(outcome_input_metadata or {})
        transcript = str(result.get("transcript") or "")
        raw_transcript = str(result.get("raw_transcript") or transcript)
        cleaned_transcript = str(
            result.get("cleaned_transcript")
            or normalize_text_for_nlp(raw_transcript)
        )
        recommendation, nlp_result = _build_recommendation(db, filename=filename, result=result, settings_snapshot=settings_snapshot)
        update_current_job(stage="saving", progress=90, message="Saving analysis to My Ideas")
        saved = save_video_analysis_result(
            db,
            user=user,
            filename=filename,
            file_path=file_path,
            transcript=transcript,
            raw_transcript=raw_transcript,
            cleaned_transcript=cleaned_transcript,
            analysis_payload=result,
            nlp_result=nlp_result,
            recommendation_payload=recommendation,
        )
        return {
            "content_id": saved["content_id"],
            "title": saved["title"],
            "transcript": transcript,
            "raw_transcript": raw_transcript,
            "cleaned_transcript": cleaned_transcript,
            "saved": True,
            "saved_keywords": saved["saved_keywords"],
            "recommended_keywords": saved["recommended_keywords"],
            "recommended_duration": saved["recommended_duration"],
            "recommendation": recommendation,
            "analysis": result,
            "analysis_settings": settings_snapshot,
            "nlp_result": nlp_result,
        }
    finally:
        db.close()


def analyze_revision_video_job(comparison_id: int, *, expected_job_id: str | None = None) -> dict:
    """Run the existing pipeline once, then commit child result and comparison together."""
    db = SessionLocal()
    claimed = False
    try:
        row = claim_revision_job(db, comparison_id, expected_job_id=expected_job_id)
        if row.status == "completed":
            return revision_job_response(db, row)["result"]
        claimed = True
        expected_job_id = row.job_id
        user = db.query(User).filter_by(user_id=row.user_id, is_active=True).first()
        if user is None:
            raise RuntimeError("บัญชีผู้ใช้ไม่พร้อมสำหรับการบันทึกผล")
        if db.get(AnalysisResult, row.parent_analysis_id) is None:
            raise RuntimeError("ผลวิเคราะห์ต้นฉบับถูกลบระหว่างประมวลผล")
        if not os.path.isfile(row.file_path) or _file_sha256(row.file_path) != row.file_sha256:
            raise RuntimeError("ไฟล์ฉบับแก้ไขไม่ตรงกับไฟล์ที่รับเข้าระบบ")
        settings_snapshot = json.loads(row.settings_snapshot_json)
        plan_snapshot = json.loads(row.plan_snapshot_json)
        if fingerprint(plan_snapshot) != row.snapshot_sha256:
            raise RuntimeError("ข้อมูลแผนที่รับเข้าระบบเปลี่ยนแปลง กรุณาอัปโหลดใหม่")
        update_current_job(stage="extracting_audio", progress=18, message="Preparing revised clip audio")
        result = pipeline_analyze(
            row.file_path,
            display_name=row.original_filename,
            hook_duration_seconds=settings_snapshot["hook_duration_seconds"],
            asr_model_size=settings_snapshot["asr_model"],
        )
        result["analysis_settings"] = settings_snapshot
        parent_outcome = plan_snapshot.get("parent_outcome_assessment") or {}
        parent_outcome_context = parent_outcome.get("context") or {}
        if parent_outcome.get("status") == "available" and parent_outcome_context:
            try:
                revised_duration = probe_media_duration_seconds(row.file_path)
            except MediaValidationError:
                revised_duration = None
            if revised_duration is not None:
                result["outcome_context"] = {
                    "confirmed_format": parent_outcome_context.get("confirmed_format"),
                    "confirmed_format_provenance": "frozen_parent_revision_context",
                    "duration_seconds": revised_duration,
                    "reference_age_context": parent_outcome_context.get("frozen_age_context"),
                    "reference_age_context_provenance": "frozen_parent_revision_context",
                }
        transcript = str(result.get("transcript") or "")
        raw_transcript = str(result.get("raw_transcript") or transcript)
        cleaned_transcript = str(
            result.get("cleaned_transcript") or normalize_text_for_nlp(raw_transcript)
        )
        recommendation, nlp_result = _build_recommendation(
            db,
            filename=row.original_filename,
            result=result,
            settings_snapshot=settings_snapshot,
        )
        comparison = build_revision_comparison(plan_snapshot, recommendation)
        update_revision_job(
            db,
            comparison_id,
            expected_job_id=expected_job_id,
            status="running",
            stage="saving",
            progress=90,
        )
        update_current_job(stage="saving", progress=90, message="Saving revised analysis and comparison")
        saved = save_video_analysis_result(
            db,
            user=user,
            filename=row.original_filename,
            file_path=row.file_path,
            transcript=transcript,
            raw_transcript=raw_transcript,
            cleaned_transcript=cleaned_transcript,
            analysis_payload=result,
            nlp_result=nlp_result,
            recommendation_payload=recommendation,
            commit=False,
        )
        db.expire_all()
        active_user = db.query(User).filter_by(user_id=row.user_id, is_active=True).first()
        parent = db.query(UserContent).filter_by(
            content_id=row.parent_content_id, user_id=row.user_id
        ).first()
        row = db.get(ClipRevisionComparison, comparison_id)
        if (active_user is None or parent is None or row is None or
                row.job_id != expected_job_id or row.status != "running"):
            db.rollback()
            raise RuntimeError("บัญชีหรือผลต้นฉบับถูกปิดก่อนบันทึกผล")
        child = db.get(UserContent, saved["content_id"])
        comparison["child"].update(
            {
                "content_id": saved["content_id"],
                "analysis_id": saved["analysis_id"],
                "title": child.title,
                "created_at": utc_isoformat(child.created_at),
            }
        )
        row.child_content_id = saved["content_id"]
        row.child_analysis_id = saved["analysis_id"]
        row.comparison_result_json = json.dumps(comparison, ensure_ascii=False)
        row.status = "completed"
        row.stage = "completed"
        row.progress = 100
        row.completed_at = datetime.utcnow()
        row.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
        return revision_job_response(db, row)["result"]
    except Exception as exc:
        db.rollback()
        row = db.get(ClipRevisionComparison, comparison_id)
        if claimed and row is not None and row.job_id == expected_job_id and row.status == "running":
            row.status = "failed"
            row.stage = "failed"
            row.error_code = exc.__class__.__name__
            row.error_message = str(exc)[:500] if isinstance(exc, RuntimeError) else "ประมวลผลฉบับแก้ไขไม่สำเร็จ กรุณาลองใหม่"
            row.updated_at = datetime.utcnow()
            db.commit()
            safe_message = row.error_message
        else:
            safe_message = "งานถูกยกเลิกเพราะต้นฉบับหรือบัญชีไม่พร้อมใช้งาน"
        raise RuntimeError(safe_message) from None
    finally:
        db.close()


@router.get("/analyze/settings")
def read_upload_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "user")),
):
    return get_analysis_settings(db)


def _capture_upload_settings(db: Session) -> dict:
    try:
        return capture_analysis_settings(db)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/analyze")
async def analyze(
    file: UploadFile = File(...),
    confirmed_format: str | None = Form(default=None),
    reference_age_context: str | None = Form(default=None),
    current_user: User = Depends(require_roles("admin", "user")),
    db: Session = Depends(get_db),
):
    print(f"[analyze] received upload: {file.filename}", flush=True)
    settings_snapshot = _capture_upload_settings(db)
    file_path = _save_validated_upload(file, max_duration_seconds=settings_snapshot["upload_max_duration_seconds"])
    filename = Path(file.filename or file_path).name
    try:
        outcome_input_metadata = _verified_outcome_input_metadata(
            file_path, confirmed_format=confirmed_format,
            reference_age_context=reference_age_context,
        )
    except HTTPException:
        Path(file_path).unlink(missing_ok=True)
        raise
    job_id = enqueue(analyze_video_job, file_path, filename, current_user.user_id,
                     settings_snapshot=settings_snapshot,
                     outcome_input_metadata=outcome_input_metadata,
                     _owner_user_id=current_user.user_id)
    return {"job_id": job_id}


@router.post("/analyze/save")
async def analyze_and_save(
    file: UploadFile = File(...),
    confirmed_format: str | None = Form(default=None),
    reference_age_context: str | None = Form(default=None),
    current_user: User = Depends(require_roles("admin", "user")),
    db: Session = Depends(get_db),
):
    print(f"[analyze/save] received upload: {file.filename}", flush=True)
    settings_snapshot = _capture_upload_settings(db)
    file_path = _save_validated_upload(file, max_duration_seconds=settings_snapshot["upload_max_duration_seconds"])
    filename = Path(file.filename or file_path).name
    try:
        outcome_input_metadata = _verified_outcome_input_metadata(
            file_path, confirmed_format=confirmed_format,
            reference_age_context=reference_age_context,
        )
    except HTTPException:
        Path(file_path).unlink(missing_ok=True)
        raise
    print(f"[analyze/save] saved file to {file_path}, enqueueing analysis+save job", flush=True)
    job_id = enqueue(analyze_and_save_video_job, file_path, filename, current_user.user_id,
                     settings_snapshot=settings_snapshot,
                     outcome_input_metadata=outcome_input_metadata,
                     _owner_user_id=current_user.user_id)
    return {"job_id": job_id}


@router.post("/analyze/revision")
async def analyze_revision(
    file: UploadFile = File(...),
    parent_content_id: int = Form(...),
    parent_analysis_id: int = Form(...),
    parent_recommendation_fingerprint: str = Form(...),
    expected_plan_revision: int = Form(...),
    client_request_id: str = Form(...),
    current_user: User = Depends(require_roles("admin", "user")),
    db: Session = Depends(get_db),
):
    if not re.fullmatch(r"[A-Za-z0-9._:-]{8,100}", client_request_id):
        raise HTTPException(422, "client_request_id ไม่ถูกต้อง")
    if not re.fullmatch(r"[0-9a-f]{64}", parent_recommendation_fingerprint):
        raise HTTPException(422, "recommendation fingerprint ไม่ถูกต้อง")
    if expected_plan_revision <= 0:
        raise HTTPException(409, "กรุณาบันทึกแผนก่อนอัปโหลดฉบับแก้ไข")
    settings_snapshot = _capture_upload_settings(db)
    file_path = _save_validated_upload(
        file,
        max_duration_seconds=settings_snapshot["upload_max_duration_seconds"],
    )
    filename = Path(file.filename or file_path).name
    try:
        row, created = create_revision_job(
            db,
            user_id=current_user.user_id,
            parent_content_id=parent_content_id,
            parent_analysis_id=parent_analysis_id,
            parent_fingerprint=parent_recommendation_fingerprint,
            expected_plan_revision=expected_plan_revision,
            client_request_id=client_request_id,
            file_sha256=_file_sha256(file_path),
            file_path=file_path,
            filename=filename,
            settings_snapshot=settings_snapshot,
        )
        if not created:
            if Path(file_path).resolve() != Path(row.file_path).resolve():
                Path(file_path).unlink(missing_ok=True)
            return revision_job_response(db, row)
        try:
            enqueue(
                analyze_revision_video_job,
                row.comparison_id,
                expected_job_id=row.job_id,
                _job_id=row.job_id,
                _owner_user_id=current_user.user_id,
            )
        except Exception:
            update_revision_job(
                db,
                row.comparison_id,
                status="failed",
                stage="failed",
                error_code="enqueue_failed",
                error_message="ส่งงานวิเคราะห์ไม่สำเร็จ กรุณากดลองใหม่",
            )
            raise HTTPException(503, "ส่งงานวิเคราะห์ไม่สำเร็จ กรุณากดลองใหม่")
        return revision_job_response(db, row)
    except Exception:
        if 'row' not in locals() or not created:
            Path(file_path).unlink(missing_ok=True)
        raise


@router.get("/revision-jobs/{job_id}")
def read_revision_job(
    job_id: str,
    current_user: User = Depends(require_roles("admin", "user")),
    db: Session = Depends(get_db),
):
    return revision_job_response(
        db, get_revision_job(db, user_id=current_user.user_id, job_id=job_id)
    )


@router.post("/revision-jobs/{job_id}/retry")
def retry_revision_job(
    job_id: str,
    current_user: User = Depends(require_roles("admin", "user")),
    db: Session = Depends(get_db),
):
    row = prepare_retry(db, user_id=current_user.user_id, job_id=job_id)
    try:
        enqueue(
            analyze_revision_video_job,
            row.comparison_id,
            expected_job_id=row.job_id,
            _job_id=row.job_id,
            _owner_user_id=current_user.user_id,
        )
    except Exception:
        update_revision_job(
            db,
            row.comparison_id,
            status="failed",
            stage="failed",
            error_code="enqueue_failed",
            error_message="ส่งงานวิเคราะห์ใหม่ไม่สำเร็จ",
        )
        raise HTTPException(503, "ส่งงานวิเคราะห์ใหม่ไม่สำเร็จ")
    return revision_job_response(db, row)
