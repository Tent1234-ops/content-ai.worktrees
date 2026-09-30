from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from app.core.config import settings
from app.database.db import Base, SessionLocal, engine
from app.database.migrations import (
    migrate_phase13_taxonomy_schema,
    migrate_view_metric_schema,
    migrate_youtube_cc_dataset_schema,
)
from app.services.dataset_contract import (
    DEFAULT_COLLECTION_LANGUAGES,
    DEFAULT_YOUTUBE_PUBLIC_DATASET_VERSION,
)
from app.services.taxonomy import ACTIVE_LEAF_KEYS, sync_taxonomy_registry
from app.services.youtube_cc_dataset import (
    DEFAULT_BLOCKED_RESUME_COOLDOWN_HOURS,
    DEFAULT_MAX_TRANSCRIPT_ATTEMPTS_PER_EXECUTION,
    DEFAULT_RESUME_COOLDOWN_MINUTES,
    DEFAULT_TRANSCRIPT_DELAY_SECONDS,
    DEFAULT_TRANSCRIPT_JITTER_SECONDS,
    YouTubeCollectionResumeCooldownError,
    YouTubeCCDatasetError,
    YouTubeQuotaExceededError,
    YouTubeTranscriptProviderBlockedError,
    collect_youtube_cc_candidates,
    repair_quota_waiting_run_statuses,
    resume_youtube_cc_collection,
)


def _csv_values(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Collect real public YouTube videos with public captions for an "
            "academic, non-redistributed dataset. Both Standard YouTube and "
            "Creative Commons licenses are recorded. "
            "Source video duration is unrestricted; model text uses the first "
            "300 transcript seconds. The generated review CSV contains no "
            "automatic approvals."
        )
    )
    parser.add_argument(
        "--dataset-version", default=DEFAULT_YOUTUBE_PUBLIC_DATASET_VERSION
    )
    parser.add_argument(
        "--leaves",
        default=",".join(ACTIVE_LEAF_KEYS),
        help="Comma-separated taxonomy leaves",
    )
    parser.add_argument(
        "--languages",
        default=",".join(DEFAULT_COLLECTION_LANGUAGES),
        help="Transcript languages to collect (Thai-only by default)",
    )
    parser.add_argument("--target-per-leaf", type=int, default=50)
    parser.add_argument(
        "--min-thai-per-leaf",
        type=int,
        default=None,
        help=(
            "Minimum Thai transcripts per leaf; defaults to the full target in "
            "Thai-only mode, or 40%% when multiple languages are selected"
        ),
    )
    parser.add_argument(
        "--performance-per-leaf",
        type=int,
        default=None,
        help=(
            "Rows per leaf discovered with order=viewCount for recommendation evidence; "
            "defaults to 30%% of --target-per-leaf"
        ),
    )
    parser.add_argument("--region", default=settings.youtube_region)
    parser.add_argument(
        "--max-pages-per-query",
        type=int,
        default=1,
        help="Page budget per query for this execution (safe default: 1)",
    )
    parser.add_argument(
        "--transcript-delay-seconds",
        type=float,
        default=DEFAULT_TRANSCRIPT_DELAY_SECONDS,
        help=(
            "Base delay before each public transcript attempt "
            f"(default: {DEFAULT_TRANSCRIPT_DELAY_SECONDS:g})"
        ),
    )
    parser.add_argument(
        "--transcript-jitter-seconds",
        type=float,
        default=DEFAULT_TRANSCRIPT_JITTER_SECONDS,
        help=(
            "Random extra delay before each transcript attempt "
            f"(default: up to {DEFAULT_TRANSCRIPT_JITTER_SECONDS:g})"
        ),
    )
    parser.add_argument(
        "--max-transcript-attempts",
        type=int,
        default=DEFAULT_MAX_TRANSCRIPT_ATTEMPTS_PER_EXECUTION,
        help=(
            "Checkpoint and pause after this many transcript attempts in one "
            "execution "
            f"(default: {DEFAULT_MAX_TRANSCRIPT_ATTEMPTS_PER_EXECUTION})"
        ),
    )
    parser.add_argument(
        "--resume-cooldown-minutes",
        type=float,
        default=DEFAULT_RESUME_COOLDOWN_MINUTES,
        help=(
            "Minimum wait between pacing-paused executions "
            f"(default: {DEFAULT_RESUME_COOLDOWN_MINUTES:g} minutes)"
        ),
    )
    parser.add_argument(
        "--blocked-resume-cooldown-hours",
        type=float,
        default=DEFAULT_BLOCKED_RESUME_COOLDOWN_HOURS,
        help=(
            "Minimum wait after an explicit transcript-provider block "
            f"(default: {DEFAULT_BLOCKED_RESUME_COOLDOWN_HOURS:g} hours)"
        ),
    )
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Optional output directory; defaults to data/raw/youtube_public/<version>",
    )
    parser.add_argument(
        "--resume-run-id",
        type=int,
        help=(
            "Resume an existing unfinished run from its saved page tokens. "
            "Runs with human review events are immutable and cannot be resumed."
        ),
    )
    return parser.parse_args()


def _print_progress(manifest: dict) -> None:
    progress = manifest.get("progress") or {}
    leaf_parts = []
    for leaf in progress.get("by_leaf") or []:
        languages = leaf.get("language_counts") or {}
        leaf_parts.append(
            f"{leaf.get('leaf_key')} {leaf.get('accepted', 0)}/{leaf.get('target', 0)} "
            f"(TH {languages.get('th', 0)}/{leaf.get('thai_minimum', 0)}, "
            f"channels {leaf.get('unique_channels', 0)})"
        )
    print(
        f"[run {manifest.get('collection_run_id')}] {manifest.get('status')} | "
        f"{progress.get('accepted_total', 0)}/{progress.get('target_total', 0)} "
        f"({progress.get('percent', 0)}%) | "
        + "; ".join(leaf_parts),
        flush=True,
    )


def main() -> int:
    args = parse_args()
    if not settings.youtube_api_key:
        print("ERROR: YOUTUBE_API_KEY is not configured in .env", file=sys.stderr)
        return 1

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S%f")
    raw_dir = (
        args.output_dir
        or ROOT / "data" / "raw" / "youtube_public" / args.dataset_version
    )
    candidate_path = raw_dir / f"candidates-{stamp}.jsonl"
    review_path = (
        ROOT
        / "data"
        / "reviews"
        / "youtube_public"
        / args.dataset_version
        / f"review-{stamp}.csv"
    )
    manifest_path = (
        ROOT
        / "data"
        / "manifests"
        / f"youtube-public-{args.dataset_version}-{stamp}.json"
    )

    Base.metadata.create_all(bind=engine)
    migrate_phase13_taxonomy_schema(engine)
    migrate_youtube_cc_dataset_schema(engine)
    migrate_view_metric_schema(engine)
    db = SessionLocal()
    try:
        sync_taxonomy_registry(db)
        repair_quota_waiting_run_statuses(db)
        if args.resume_run_id is not None:
            result = resume_youtube_cc_collection(
                db,
                collection_run_id=args.resume_run_id,
                api_key=settings.youtube_api_key,
                max_pages_per_query=args.max_pages_per_query,
                timeout_seconds=args.timeout,
                progress_callback=_print_progress,
                transcript_delay_seconds=args.transcript_delay_seconds,
                transcript_jitter_seconds=args.transcript_jitter_seconds,
                max_transcript_attempts_per_execution=(
                    args.max_transcript_attempts
                ),
                resume_cooldown_minutes=args.resume_cooldown_minutes,
                blocked_resume_cooldown_hours=(
                    args.blocked_resume_cooldown_hours
                ),
            )
        else:
            result = collect_youtube_cc_candidates(
                db,
                api_key=settings.youtube_api_key,
                candidate_path=candidate_path,
                review_path=review_path,
                manifest_path=manifest_path,
                dataset_version=args.dataset_version,
                leaf_keys=_csv_values(args.leaves),
                target_per_leaf=args.target_per_leaf,
                performance_target_per_leaf=args.performance_per_leaf,
                languages=_csv_values(args.languages),
                min_thai_per_leaf=args.min_thai_per_leaf,
                region_code=args.region,
                max_pages_per_query=args.max_pages_per_query,
                timeout_seconds=args.timeout,
                progress_callback=_print_progress,
                transcript_delay_seconds=args.transcript_delay_seconds,
                transcript_jitter_seconds=args.transcript_jitter_seconds,
                max_transcript_attempts_per_execution=(
                    args.max_transcript_attempts
                ),
                resume_cooldown_minutes=args.resume_cooldown_minutes,
                blocked_resume_cooldown_hours=(
                    args.blocked_resume_cooldown_hours
                ),
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get("status") == "pacing_paused":
            next_resume_at = (result.get("pacing") or {}).get("next_resume_at")
            print(
                "\nPacing pause: wait at least "
                f"{args.resume_cooldown_minutes:g} minutes before resuming this run."
            )
            if next_resume_at:
                print(f"Next guarded resume (UTC): {next_resume_at}")
        result_review_path = (
            result.get("human_review_template") or {}
        ).get("path", review_path)
        print(f"\nHuman review file: {result_review_path}")
        print("Fill decision/reviewed_leaf_key/quality/reviewer/reviewed_at before import.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except YouTubeCollectionResumeCooldownError as exc:
        retry_local = exc.retry_at.astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
        remaining_minutes = max(1, round(exc.remaining_seconds / 60))
        print(
            "COOLDOWN_ACTIVE: no provider request was sent. "
            f"Wait about {remaining_minutes} more minute(s); "
            f"next guarded resume is {retry_local} local time.\n{exc}",
            file=sys.stderr,
        )
        raise SystemExit(4)
    except YouTubeQuotaExceededError as exc:
        print(
            "QUOTA_WAITING: YouTube search quota is exhausted. "
            "This run was checkpointed and can be resumed after reset.\n"
            f"{exc}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    except YouTubeTranscriptProviderBlockedError as exc:
        print(
            "TRANSCRIPT_WAITING: YouTube blocked transcript requests from this IP. "
            "The run was checkpointed; resume it after the block clears or from a "
            "permitted network.\n"
            f"{exc}",
            file=sys.stderr,
        )
        raise SystemExit(3)
    except YouTubeCCDatasetError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
