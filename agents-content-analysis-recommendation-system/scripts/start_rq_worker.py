"""Start an RQ worker for Content AI background jobs.

Usage:
  python scripts/start_rq_worker.py --redis redis://localhost:6379/0 --queue default

The API must use the same Redis URL when admin setting ``job_backend`` is
``rq``. For local demos, the default in-process worker is simpler and does not
need this script.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _default_redis_url() -> str:
    value = os.getenv("REDIS_URL")
    if value:
        return value
    try:
        from app.services.admin_settings import get_admin_config
        from app.database.db import SessionLocal

        db = SessionLocal()
        try:
            config = get_admin_config(db)
            redis_url = getattr(config, "redis_url", None)
            if redis_url:
                return redis_url
        finally:
            db.close()
    except Exception:
        pass
    return "redis://localhost:6379/0"


def main() -> None:
    parser = argparse.ArgumentParser(description="Start an RQ worker.")
    parser.add_argument("--redis", default=_default_redis_url())
    parser.add_argument("--queue", default="default")
    args = parser.parse_args()

    try:
        import redis
        from rq import Queue, Worker
    except ImportError as exc:
        raise SystemExit(
            "Missing dependencies. Install them with: pip install rq redis"
        ) from exc

    connection = redis.from_url(args.redis)
    worker = Worker([Queue(args.queue, connection=connection)], connection=connection)
    print(f"Starting RQ worker queue={args.queue} redis={args.redis}")
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
