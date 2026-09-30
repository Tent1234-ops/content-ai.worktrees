"""Register approved rules, backfill real observations, or drain persistent topic jobs."""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ["CONTENT_AI_SKIP_DB_BOOTSTRAP"] = "1"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, help="Register a human-approved catalog; no candidate auto-approval")
    parser.add_argument("--activate", action="store_true", help="Activate registered rules and queue all retained observations")
    parser.add_argument("--backfill", action="store_true", help="Queue only source snapshots that actually exist")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--region", default="TH")
    parser.add_argument("--max-jobs", type=int, default=100)
    parser.add_argument("--status", action="store_true", help="Read queue state only")
    args = parser.parse_args()
    if not 1 <= args.days <= 90 or not 0 <= args.max_jobs <= 100000:
        parser.error("Use 1-90 days and 0-100000 jobs")
    if args.status and (args.activate or args.catalog or args.backfill):
        parser.error("--status cannot be combined with mutations")
    from sqlalchemy import func
    from app.database.db import Base, SessionLocal, engine
    from app.database.models import TrendTopicConfig, TrendTopicJob, TrendTopicObservation
    from app.services.trend_topic_store import active_version, activate_version, backfill_topic_observations, register_version
    from app.services.trend_topic_processing import drain_topic_jobs

    if not args.status:
        Base.metadata.create_all(engine)
    output = {}
    with SessionLocal() as db:
        if not args.status:
            catalog = json.loads(args.catalog.read_text(encoding="utf-8")) if args.catalog else None
            version = register_version(db, catalog) if args.catalog or args.activate else active_version(db)
            output["registered_version"] = version.version_id
            if args.activate:
                output["enqueued"] = activate_version(db, version.version_id)
            if args.backfill:
                output["backfill"] = backfill_topic_observations(db, region=args.region.upper(), days=args.days,
                                                                 version_id=version.version_id)
            db.commit()
    if not args.status:
        output["worker"] = drain_topic_jobs(SessionLocal, max_jobs=args.max_jobs)
    with SessionLocal() as db:
        config = db.get(TrendTopicConfig, 1)
        output["active_version"] = config.active_version_id if config else None
        output["observations"] = db.query(TrendTopicObservation).count()
        output["jobs"] = dict(db.query(TrendTopicJob.status, func.count()).group_by(TrendTopicJob.status).all())
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 1 if output.get("worker", {}).get("statuses", {}).get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
