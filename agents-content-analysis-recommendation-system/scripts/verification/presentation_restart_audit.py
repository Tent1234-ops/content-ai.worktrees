"""Verify saved analysis survives restart, then refresh real global providers once."""
from __future__ import annotations

import argparse
from datetime import timedelta, datetime, timezone
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit("Refusing to overwrite report")
    original = json.loads(args.analysis_report.read_text(encoding="utf-8"))
    report = {"captured_at": datetime.now(timezone.utc).isoformat(), "passed": False}
    with SessionLocal() as db:
        admin = db.get(User, original["owner_user_id"])
        assert admin and admin.is_active and admin.role == "admin"
        watch = start_trend_watch_session(db, user=admin, region="TH")
        token = create_access_token(str(admin.user_id), admin.role,
                                    expires_delta=timedelta(minutes=30), session_key=watch.session_key)
        headers = {"Authorization": f"Bearer {token}", "X-Trend-Session-Key": watch.session_key}

    def call(method, path):
        response = requests.request(method, "http://127.0.0.1:8000" + path,
                                    headers=headers, timeout=120)
        response.raise_for_status()
        return response.json()

    try:
        current = call("GET", f"/contents/{original['content_id']}")
        assert current == original["reopened_detail"], "Saved analysis changed after restart"
        report["saved_result_identical_after_restart"] = True
        settings = call("GET", "/analyze/settings")
        keys = ("upload_max_duration_seconds", "asr_model", "hook_duration_seconds")
        assert all(settings[key] == original["settings_before"][key] for key in keys)
        report["settings_persisted"] = {key: settings[key] for key in keys}
        job = call("POST", "/dashboard/refresh")
        report["refresh_job_id"] = job["job_id"]
        while True:
            status = call("GET", f"/jobs/{job['job_id']}")
            if status["status"] in {"completed", "failed", "error", "not_found"}:
                break
            time.sleep(2)
        report["refresh_status"] = status["status"]
        report["refresh_result"] = status.get("result")
        report["error"] = status.get("error")
        assert status["status"] == "completed"
        report["passed"] = status["result"].get("status") == "completed"
    finally:
        try:
            call("POST", "/auth/logout")
        finally:
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "passed": report["passed"],
                      "saved_result_identical": report.get("saved_result_identical_after_restart"),
                      "refresh": report.get("refresh_result")}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
