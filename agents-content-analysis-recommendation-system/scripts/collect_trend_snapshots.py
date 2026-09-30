"""One scheduler check. No web server, login token, or AI model is required."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--status", action="store_true", help="Read settings without collecting")
    mode.add_argument("--configure-daily", action="store_true", help="Save 14:00-23:00 Asia/Bangkok (10 rounds)")
    args = parser.parse_args()

    from app.database.db import Base, SessionLocal, engine
    from app.database import models  # Register metadata before creating missing tables.
    from app.database.migrations import migrate_scope_completion_schema, migrate_trend_scheduler_schema, migrate_reference_statistics_schema
    from app.services.trend_settings import TrendScheduleParameters, save_trend_schedule, trend_schedule

    Base.metadata.create_all(engine)
    migrate_scope_completion_schema(engine)
    migrate_trend_scheduler_schema(engine)
    migrate_reference_statistics_schema(engine)
    if args.status or args.configure_daily:
        with SessionLocal() as db:
            if args.configure_daily:
                result = save_trend_schedule(db, TrendScheduleParameters(
                    enabled=True, schedule_mode="hourly_window", start_hour=14, end_hour=23,
                    global_interval_seconds=3600, category_interval_seconds=3600,
                ), user_id=None)
            else:
                result = trend_schedule(db)
    else:
        from app.services.trend_scheduler import collect_due
        from app.services.reference_statistics import refresh_reference_statistics
        from app.services.trending_fetcher import (
            refresh_global_live_trends_job, refresh_youtube_category_live_trends_job,
        )
        result = collect_due(session_factory=SessionLocal, actor="task_scheduler",
            global_fetch=lambda: refresh_global_live_trends_job(sources=["youtube", "google"]),
            category_fetch=refresh_youtube_category_live_trends_job,
            reference_fetch=lambda: refresh_reference_statistics(actor="task_scheduler"))
        from app.services.trend_topic_processing import drain_topic_jobs
        result["topic_processing"] = drain_topic_jobs(SessionLocal, max_jobs=100)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("status") in {"failed", "partial"} else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Trend collector failed ({type(exc).__name__}). Check database connectivity and System Logs.",
              file=sys.stderr)
        raise SystemExit(1)
