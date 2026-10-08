import asyncio
import importlib
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.database.db import Base, DB_BOOTSTRAP_ERROR, SessionLocal, engine
from app.database.migrations import (
    archive_phase10_notification_tables,
    migrate_analysis_payload_schema,
    migrate_analysis_settings_schema,
    migrate_scope_completion_schema,
    migrate_trend_scheduler_schema,
    migrate_training_requestor_schema,
    migrate_reference_statistics_schema,
    migrate_outcome_statistics_schema,
    migrate_classification_split_strategy,
    migrate_phase13_taxonomy_schema,
    migrate_phase19_transcript_schema,
    migrate_trend_scope_schema,
    migrate_view_metric_schema,
    migrate_youtube_cc_dataset_schema,
)
from app.routes import admin, admin_scanner, analyze, auth, classification, clustering, contents, dashboard, dataset_review, datasets, nlp, recommendation, trends, notifications, follows
from app.routes import model_management
from app.routes import user_management
from app.routes import trend_topics
from app.services.trending_fetcher import start_trending_fetcher, stop_trending_fetcher
from app.services.live_trend_snapshots import get_live_provider_health
from app.services.trend_history import backfill_retained_history
from app.services.trend_topic_processing import start_topic_worker, stop_topic_worker
from app.services.trend_topic_store import active_version
from app.services.taxonomy import sync_taxonomy_registry
from app.services.admin_settings import get_or_create_admin_config
from app.services.youtube_cc_dataset import repair_quota_waiting_run_statuses
from app.services.revision_comparisons import mark_inprocess_jobs_interrupted
from models.speech_to_text import check_model_readiness

app = FastAPI(title=settings.app_name, version=settings.app_version)
app.include_router(model_management.router)
app.include_router(user_management.router)
app.include_router(trend_topics.router)
asr_model_status = check_model_readiness()

def preload_ai_models():
    modules = [
        "models.speech_to_text",
        "models.keyword_ai",
        "models.keyword_ranker",
        "models.semantic_keyword",
        "models.blip_caption",
        "models.scene_detect",
        "models.frame_extract",
    ]
    print("Starting AI model preload...", flush=True)
    for module_name in modules:
        try:
            print(f"Preloading {module_name}...", flush=True)
            importlib.import_module(module_name)
        except Exception as exc:
            print(f"Warning: failed to preload {module_name}: {exc}", flush=True)
    print("AI model preload complete.", flush=True)


@app.on_event("startup")
async def startup_event():
    global asr_model_status
    with SessionLocal() as db:
        mark_inprocess_jobs_interrupted(db)
        asr_model_status = check_model_readiness(get_or_create_admin_config(db).asr_model_default)
        active_version(db)
        backfill_retained_history(db)
    if not asr_model_status["ready"]:
        message = (
            "Faster Whisper model is not ready. Run "
            f"python scripts/setup_faster_whisper.py --model {asr_model_status['model_size']}"
        )
        print(f"Warning: {message}", flush=True)
        require_ready = os.getenv("ASR_REQUIRE_MODEL_READY", "0").strip().lower()
        if require_ready not in {"0", "false", "no", "off"}:
            raise RuntimeError(message)
    start_trending_fetcher()
    start_topic_worker(SessionLocal)


@app.on_event("shutdown")
async def shutdown_event():
    stop_trending_fetcher()
    stop_topic_worker()


# Configure CORS for the Flutter Web client.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",      # Flutter Web dev
        "http://127.0.0.1:3000",      # Flutter Web dev (localhost)
        "http://localhost:5000",      # Flutter Web alt port
        "http://127.0.0.1:5000",      # Flutter Web alt port
        "http://localhost",           # Flutter Web production
        "http://127.0.0.1",           # Flutter Web production
        "*",                          # Allow all origins (dev only - restrict in production)
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Keep startup simple for Phase 1 so the API is ready after boot.
db_init_status = "ok"
phase11_migration_status = {}
phase13_migration_status = {}
youtube_cc_migration_status = {}
view_metric_migration_status = {}
trend_scope_migration_status = {}
classification_split_migration_status = {}
phase19_transcript_migration_status = {}
analysis_payload_migration_status = {}
analysis_settings_migration_status = {}
taxonomy_seed_status = {}
youtube_quota_repair_status = {}
try:
    phase11_migration_status = archive_phase10_notification_tables(engine)
    Base.metadata.create_all(bind=engine)
    phase13_migration_status = migrate_phase13_taxonomy_schema(engine)
    youtube_cc_migration_status = migrate_youtube_cc_dataset_schema(engine)
    view_metric_migration_status = migrate_view_metric_schema(engine)
    trend_scope_migration_status = migrate_trend_scope_schema(engine)
    classification_split_migration_status = migrate_classification_split_strategy(
        engine
    )
    phase19_transcript_migration_status = migrate_phase19_transcript_schema(engine)
    analysis_payload_migration_status = migrate_analysis_payload_schema(engine)
    analysis_settings_migration_status = migrate_analysis_settings_schema(engine)
    migrate_scope_completion_schema(engine)
    migrate_trend_scheduler_schema(engine)
    migrate_training_requestor_schema(engine)
    migrate_reference_statistics_schema(engine)
    migrate_outcome_statistics_schema(engine)
    taxonomy_db = SessionLocal()
    try:
        taxonomy_seed_status = sync_taxonomy_registry(taxonomy_db)
        youtube_quota_repair_status = repair_quota_waiting_run_statuses(
            taxonomy_db
        )
    finally:
        taxonomy_db.close()
except (SQLAlchemyError, Exception) as exc:
    db_init_status = f"degraded: {exc.__class__.__name__}"
if DB_BOOTSTRAP_ERROR:
    db_init_status = f"degraded: {DB_BOOTSTRAP_ERROR}"

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(classification.router)
app.include_router(clustering.router)
app.include_router(contents.router)
app.include_router(dashboard.router)
app.include_router(dataset_review.router)
app.include_router(datasets.router)
app.include_router(nlp.router)
app.include_router(recommendation.router)
app.include_router(trends.router)
app.include_router(analyze.router)
app.include_router(notifications.router)
app.include_router(follows.router)
app.include_router(admin_scanner.router)
# jobs router for background job status
from app.routes import jobs
app.include_router(jobs.router)


@app.get("/", tags=["health"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "status": "ok",
        "db_init": db_init_status,
        "youtube_cc_schema": youtube_cc_migration_status,
        "view_metric_schema": view_metric_migration_status,
        "trend_scope_schema": trend_scope_migration_status,
        "phase19_transcript_schema": phase19_transcript_migration_status,
        "analysis_payload_schema": analysis_payload_migration_status,
        "analysis_settings_schema": analysis_settings_migration_status,
        "taxonomy": taxonomy_seed_status,
    }


@app.get("/health", tags=["health"])
def health():
    db = SessionLocal()
    database = {
        "status": "ok",
        "init": db_init_status,
        "phase11_archived_tables": phase11_migration_status,
        "phase13_schema": phase13_migration_status,
        "youtube_cc_schema": youtube_cc_migration_status,
        "view_metric_schema": view_metric_migration_status,
        "trend_scope_schema": trend_scope_migration_status,
        "phase19_transcript_schema": phase19_transcript_migration_status,
        "analysis_payload_schema": analysis_payload_migration_status,
        "taxonomy": taxonomy_seed_status,
    }
    live_trends = {
        "run_id": None,
        "snapshot_status": "unavailable",
        "generated_at": None,
        "providers": {},
    }
    try:
        db.execute(text("SELECT 1"))
        current_asr_status = check_model_readiness(get_or_create_admin_config(db).asr_model_default)
        live_trends = get_live_provider_health(db, region=settings.youtube_region)
    except Exception as exc:
        current_asr_status = {"status": "unavailable", "ready": False}
        database = {
            "status": "error",
            "init": db_init_status,
            "phase11_archived_tables": phase11_migration_status,
            "phase13_schema": phase13_migration_status,
            "youtube_cc_schema": youtube_cc_migration_status,
            "view_metric_schema": view_metric_migration_status,
            "analysis_payload_schema": analysis_payload_migration_status,
            "taxonomy": taxonomy_seed_status,
            "error": f"{exc.__class__.__name__}: {exc}",
        }
    finally:
        db.close()

    provider_states = [
        str(item.get("status") or "pending")
        for item in live_trends.get("providers", {}).values()
    ]
    if database["status"] != "ok":
        status = "unhealthy"
    elif not provider_states or any(item in {"error", "pending"} for item in provider_states):
        status = "degraded"
    elif not current_asr_status.get("ready"):
        status = "degraded"
    else:
        status = "ok"

    return {
        "status": status,
        "database": database,
        "ai_models": {"faster_whisper": current_asr_status},
        "live_trends": live_trends,
    }
