"""Run a real regression clip through the local API and retain its saved result.

This is workflow evidence, not a new held-out classification evaluation.
No models, dataset rows, or settings are changed. Tokens are never written.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.core.security import create_access_token
from app.database.db import SessionLocal
from app.database.models import User
from app.services.trend_watch_sessions import start_trend_watch_session


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    args = parser.parse_args()
    clip, output = args.clip.resolve(), args.output.resolve()
    if not clip.is_file() or (output.exists() and not args.resume) or args.timeout_seconds <= 0:
        raise SystemExit("Clip must exist, output must be new unless resuming, and timeout must be positive")
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {"captured_at": datetime.now(timezone.utc).isoformat(),
              "evidence_type": "real regression upload, not fresh held-out evaluation",
              "clip": str(clip), "passed": False, "stages": []}
    if args.resume:
        report = json.loads(output.read_text(encoding="utf-8"))
        if report.get("passed") or Path(report["clip"]).resolve() != clip or not report.get("job_id"):
            raise SystemExit("Only the same unfinished clip job may be resumed")
    with SessionLocal() as db:
        admin = db.query(User).filter_by(role="admin", is_active=True).order_by(User.user_id).first()
        if admin is None:
            raise SystemExit("No active admin")
        watch = start_trend_watch_session(db, user=admin, region="TH")
        token = create_access_token(str(admin.user_id), admin.role,
                                    expires_delta=timedelta(hours=1), session_key=watch.session_key)
        headers = {"Authorization": f"Bearer {token}", "X-Trend-Session-Key": watch.session_key}
        report["owner_user_id"] = admin.user_id
    base = args.base_url.rstrip("/")

    def call(method, route, **kwargs):
        response = requests.request(method, base + route, headers=headers, timeout=120, **kwargs)
        response.raise_for_status()
        return response.json()

    def persist():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        if not args.resume:
            report["settings_before"] = call("GET", "/analyze/settings")
            with clip.open("rb") as source:
                job = call("POST", "/analyze/save", files={"file": (clip.name, source, "video/mp4")})
            report["job_id"] = job["job_id"]
        persist()
        deadline = time.monotonic() + args.timeout_seconds
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError("Analysis job still pending; resume the same audit instead of uploading again")
            status = call("GET", f"/jobs/{report['job_id']}")
            stage = status.get("stage") or status.get("status")
            if not report["stages"] or report["stages"][-1]["stage"] != stage:
                report["stages"].append({"stage": stage, "at": datetime.now(timezone.utc).isoformat()})
                print(json.dumps({"stage": stage}), flush=True)
                persist()
            if status["status"] == "completed":
                break
            if status["status"] in {"failed", "error", "not_found"}:
                raise RuntimeError(str(status.get("error") or status["status"]))
            time.sleep(5)
        result = status["result"]
        report["result"] = result
        assert result["saved"] is True
        assert result["raw_transcript"].strip()
        stt = result["analysis"]["analysis"]["stt_meta"]
        assert stt.get("transcript_source") != "fallback_filename"
        detail = call("GET", f"/contents/{result['content_id']}")
        report["reopened_detail"] = detail
        assert detail["content_id"] == result["content_id"]
        report["content_id"] = result["content_id"]
        report["passed"] = True
    except Exception as exc:
        report["error"] = str(exc)
        raise
    finally:
        try:
            call("POST", "/auth/logout", json={})
        finally:
            report["finished_at"] = datetime.now(timezone.utc).isoformat()
            persist()
    print(json.dumps({"output": str(output), "passed": report["passed"],
                      "content_id": report.get("content_id")}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
