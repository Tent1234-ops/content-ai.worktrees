"""Live local API acceptance with isolated records and guarded cleanup.

This script does not upload a valid clip, fetch providers, review/import data,
train, or activate a model. Positive recommendation acceptance is intentionally
left to the model gate and fresh-heldout protocol instead of being faked here.
"""
from __future__ import annotations

import argparse
from datetime import timedelta
import json
from pathlib import Path
import secrets
import sys
from uuid import uuid4

import requests


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.core.security import create_access_token
from app.database.db import SessionLocal
from app.database.models import DatasetContent, User
from app.services.trend_watch_sessions import start_trend_watch_session


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise SystemExit(f"Refusing to overwrite acceptance artifact: {output}")

    marker = f"phase5-{uuid4().hex[:12]}"
    report = {
        "schema_version": "project-closeout-phase5-api-v1",
        "marker": marker,
        "evidence_type": "live local API with isolated temporary rows",
        "constraints": [
            "no provider fetch",
            "no valid-video analysis",
            "no dataset review/import",
            "no train or model activation",
        ],
        "checks": [],
        "requests": [],
        "cleanup": {},
    }
    created_user_ids: list[int] = []
    dataset_id: int | None = None
    admin_session: dict | None = None

    def persist() -> None:
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    def headers(session: dict | None) -> dict:
        if session is None:
            return {}
        return {
            "Authorization": f"Bearer {session['access_token']}",
            "X-Trend-Session-Key": session["session_key"],
        }

    def call(method: str, path: str, *, session=None, expected=200, **kwargs):
        response = requests.request(
            method,
            args.base_url.rstrip("/") + path,
            headers=headers(session),
            timeout=90,
            **kwargs,
        )
        report["requests"].append({"method": method, "path": path, "status": response.status_code})
        if response.status_code != expected:
            raise AssertionError(f"{method} {path}: expected {expected}, got {response.status_code}")
        if not response.content:
            return None
        return response.json()

    def check(name: str, operation) -> None:
        try:
            details = operation() or {}
            report["checks"].append({"name": name, "status": "passed", "details": details})
        except Exception as exc:
            report["checks"].append({"name": name, "status": "failed", "error": str(exc)})
        persist()

    with SessionLocal() as db:
        admin = db.query(User).filter_by(role="admin", is_active=True).order_by(User.user_id).first()
        if admin is None:
            raise SystemExit("No active admin is available for acceptance")
        watch = start_trend_watch_session(db, user=admin, region="TH")
        admin_session = {
            "access_token": create_access_token(
                str(admin.user_id), admin.role,
                expires_delta=timedelta(minutes=30),
                session_key=watch.session_key,
            ),
            "session_key": watch.session_key,
        }

    password = secrets.token_urlsafe(18)
    accounts = [
        {"username": f"{marker}-a", "email": f"{marker}-a@test.invalid", "password": password},
        {"username": f"{marker}-b", "email": f"{marker}-b@test.invalid", "password": password},
    ]

    try:
        sessions: list[dict] = []

        def registration_flow():
            for payload in accounts:
                row = call("POST", "/auth/register", expected=201, json=payload)
                created_user_ids.append(row["user_id"])
            call("POST", "/auth/register", expected=409, json=accounts[0])
            call("POST", "/auth/login", expected=401, json={"email": accounts[0]["email"], "password": "wrong-password"})
            for payload in accounts:
                sessions.append(call("POST", "/auth/login", json={"email": payload["email"], "password": payload["password"]}))
            return {"registered": len(accounts), "duplicate_rejected": True, "wrong_password_rejected": True}

        check("Register, duplicate validation, login, and wrong credentials", registration_flow)

        def authorization_flow():
            call("GET", "/contents/my", expected=401)
            call("GET", "/admin/users", expected=401)
            call("GET", "/admin/users", session=sessions[0], expected=403)
            own_a = call("GET", "/contents/my", session=sessions[0])
            own_b = call("GET", "/contents/my", session=sessions[1])
            return {"anonymous_denied": True, "user_admin_denied": True,
                    "isolated_history_counts": [own_a.get("total", 0), own_b.get("total", 0)]}

        check("Protected routes and per-account history", authorization_flow)

        def public_and_settings_flow():
            dashboard = call("GET", "/dashboard/public/trends?platform=youtube&limit=5")
            settings = call("GET", "/analyze/settings", session=sessions[0])
            platforms = dashboard.get("platforms", {})
            return {
                "youtube_items": len(platforms.get("youtube", {}).get("items", [])),
                "google_items": len(platforms.get("google", {}).get("items", [])),
                "analysis_settings": {key: settings.get(key) for key in (
                    "upload_max_duration_seconds", "asr_model", "hook_duration_seconds", "asr_ready"
                )},
            }

        check("Public trends and server-owned analysis settings", public_and_settings_flow)

        def follow_flow():
            preferences = call("GET", "/follows/preferences", session=sessions[0])
            category = preferences["categories"][0]
            payload = {"match_type": "category", "platform": "youtube", "value": category["id"]}
            first = call("POST", "/follows/topic", session=sessions[0], json=payload)
            second = call("POST", "/follows/topic", session=sessions[0], json=payload)
            assert first["id"] == second["id"]
            assert call("GET", "/follows/topics", session=sessions[1])["total"] == 0
            call("PUT", "/follows/preferences", session=sessions[0], json={"notification_mode": "following"})
            assert call("GET", "/follows/preferences", session=sessions[0])["notification_mode"] == "following"
            assert call("DELETE", f"/follows/topic/{first['id']}", session=sessions[0])["deleted"]
            call("PUT", "/follows/preferences", session=sessions[0], json={"notification_mode": "all"})
            return {"category": category["id"], "deduplicated": True, "account_isolated": True, "cleanup": True}

        check("Follow, deduplication, preferences, isolation, and unfollow", follow_flow)

        def dataset_flow():
            nonlocal dataset_id
            row = call("POST", "/admin/datasets", session=admin_session, json={
                "title": f"{marker} temporary acceptance dataset",
                "transcript": f"Temporary acceptance transcript {marker}. Not training or recommendation evidence.",
                "dataset_source": "acceptance_test",
                "dataset_version": marker,
                "source_platform": "manual_test",
                "is_active": False,
                "is_training_eligible": False,
            })
            dataset_id = row["dataset_id"]
            changed = call("PUT", f"/admin/datasets/{dataset_id}", session=admin_session, json={
                "title": f"{marker} corrected acceptance dataset",
                "transcript": f"Corrected temporary acceptance transcript {marker}.",
                "taxonomy_leaf_key": "phone",
            })
            assert changed["transcript_sha256"] and changed["taxonomy_leaf_key"] == "phone"
            assert not changed["is_training_eligible"] and not changed["is_active"]
            call("DELETE", f"/admin/datasets/{dataset_id}?confirmation_id={dataset_id + 1}", session=admin_session, expected=422)
            call("DELETE", f"/admin/datasets/{dataset_id}?confirmation_id={dataset_id}", session=admin_session)
            restored = call("POST", f"/admin/datasets/{dataset_id}/restore?confirmation_id={dataset_id}", session=admin_session)
            assert restored["deleted_at"] is None and not restored["is_training_eligible"]
            call("DELETE", f"/admin/datasets/{dataset_id}?confirmation_id={dataset_id}", session=admin_session)
            return {"dataset_id": dataset_id, "hash_recomputed": True, "trash_restore": True,
                    "never_training_or_reference": True}

        check("Admin Dataset create, correct, trash, restore, and trash", dataset_flow)

        def account_management_flow():
            user_id = created_user_ids[1]
            row = call("GET", f"/admin/users/{user_id}", session=admin_session)
            for role, active in (("admin", True), ("user", True), ("user", False)):
                row = call("PUT", f"/admin/users/{user_id}", session=admin_session, json={
                    "username": row["username"], "email": row["email"],
                    "expected_revision": row["revision"], "role": role, "is_active": active,
                })
            call("POST", "/auth/login", expected=403, json={"email": accounts[1]["email"], "password": password})
            return {"target_user_id": user_id, "promote_demote_suspend": True, "inactive_login_denied": True}

        check("Admin user role and status management", account_management_flow)

        check("Corrupt video is rejected without a saved success", lambda: {
            "status": "rejected",
            "response": call("POST", "/analyze/save", session=sessions[0], expected=422,
                             files={"file": (f"{marker}.mp4", b"not a video", "video/mp4")}),
        })

        def admin_reads():
            routes = (
                "/admin/training", "/admin/analysis-settings", "/admin/trend-settings",
                "/admin/datasets/readiness", "/admin/dataset-review/queue",
                "/admin/sources/health", "/admin/logs", "/admin/usage-statistics?year=2026&month=10",
            )
            for path in routes:
                call("GET", path, session=admin_session)
            return {"routes": list(routes)}

        check("Admin status, settings, data, health, logs, and usage reads", admin_reads)
    finally:
        # Delete disposable users through the public administration workflow.
        if admin_session:
            for user_id in reversed(created_user_ids):
                try:
                    row = call("GET", f"/admin/users/{user_id}", session=admin_session)
                    call("DELETE", f"/admin/users/{user_id}", session=admin_session, json={
                        "expected_revision": row["revision"], "confirmation": row["username"],
                    })
                except Exception as exc:
                    report["cleanup"].setdefault("errors", []).append(f"user {user_id}: {exc}")

        # Trash is user-visible history, not a hard-delete workflow. Remove only
        # this script's isolated row after strict marker and eligibility guards.
        if dataset_id is not None:
            with SessionLocal() as db:
                row = db.get(DatasetContent, dataset_id)
                guarded = bool(
                    row
                    and row.dataset_source == "acceptance_test"
                    and row.dataset_version == marker
                    and marker in row.title
                    and row.deleted_at is not None
                    and not row.is_active
                    and not row.is_training_eligible
                    and not row.is_keyword_recommendation_eligible
                    and not row.is_duration_recommendation_eligible
                )
                if guarded:
                    db.delete(row)
                    db.commit()
                else:
                    db.rollback()
                    report["cleanup"].setdefault("errors", []).append("dataset identity guard refused cleanup")

        if admin_session:
            try:
                call("POST", "/auth/logout", session=admin_session, json={})
            except Exception as exc:
                report["cleanup"].setdefault("errors", []).append(f"admin session: {exc}")

        with SessionLocal() as db:
            remaining_users = db.query(User).filter(User.username.like(f"{marker}%")).count()
            remaining_datasets = db.query(DatasetContent).filter_by(
                dataset_source="acceptance_test", dataset_version=marker
            ).count()
        report["cleanup"].update({
            "temporary_users_remaining": remaining_users,
            "temporary_datasets_remaining": remaining_datasets,
            "passed": remaining_users == 0 and remaining_datasets == 0 and not report["cleanup"].get("errors"),
        })
        report["passed"] = all(row["status"] == "passed" for row in report["checks"]) and report["cleanup"]["passed"]
        persist()

    print(json.dumps({
        "output": str(output),
        "passed": report["passed"],
        "checks": len(report["checks"]),
        "cleanup": report["cleanup"],
    }, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
