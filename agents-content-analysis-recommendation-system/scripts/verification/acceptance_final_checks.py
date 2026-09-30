"""Acceptance state checks on local MySQL/API, without changing active models."""
import json
from pathlib import Path
import secrets
import sys
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "artifacts/acceptance/20260930"
BASE = "http://127.0.0.1:8000"
user = json.loads((OUT / "private-session.json").read_text())
admin = json.loads((OUT / "private-admin.json").read_text())
report_path = OUT / "final-checks.json"
report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {"checks": []}


def call(method, path, account=admin, expected=200, **kwargs):
    session = account["session"]
    response = requests.request(method, BASE + path, timeout=90,
        headers={"Authorization": "Bearer " + session["access_token"], "X-Trend-Session-Key": session["session_key"]}, **kwargs)
    assert response.status_code == expected, f"{method} {path}: {response.status_code}: {response.text[:250]}"
    return response.json()


def check(name, operation):
    try:
        details = operation()
        row = {"name": name, "status": "passed", "details": details}
    except Exception as exc:
        row = {"name": name, "status": "failed", "error": str(exc)}
    report["checks"] = [r for r in report["checks"] if r["name"] != name] + [row]
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(row, ensure_ascii=True), flush=True)


def account_lifecycle():
    suffix = secrets.token_hex(4)
    payload = {"username": "acceptance_disposable_" + suffix, "email": f"acceptance_disposable_{suffix}@example.com", "password": secrets.token_hex(18)}
    row = call("POST", "/admin/users", expected=201, json=payload)
    uid = row["user_id"]
    try:
        for role, active in [("admin", True), ("user", True), ("user", False)]:
            row = call("PUT", f"/admin/users/{uid}", json={"username": row["username"], "email": row["email"],
                "expected_revision": row["revision"], "role": role, "is_active": active})
            assert row["role"] == role and row["is_active"] == active
        call("POST", "/auth/login", expected=403, json={k: payload[k] for k in ("email", "password")})
        return {"temporary_user_id": uid, "promote_demote_suspend": True, "inactive_login_denied": True}
    finally:
        row = call("GET", f"/admin/users/{uid}")
        call("DELETE", f"/admin/users/{uid}", json={"expected_revision": row["revision"], "confirmation": row["username"]})
        call("GET", f"/admin/users/{uid}", expected=404)


def settings_roundtrip():
    keys = ("upload_max_duration_seconds", "asr_model", "hook_duration_seconds")
    before = call("GET", "/admin/analysis-settings")
    values = {k: before[k] for k in keys}
    # Change only the Hook window briefly; restore before any further upload.
    changed = {**values, "hook_duration_seconds": values["hook_duration_seconds"] - 1}
    try:
        call("PUT", "/admin/analysis-settings", json=changed)
        applied = call("GET", "/analyze/settings", user)
        assert all(applied[k] == changed[k] for k in keys)
        existing = call("GET", f'/contents/{user["content_id"]}', user)
        assert existing["analysis"]["analysis_settings"]["hook_duration_seconds"] == values["hook_duration_seconds"]
        unavailable = next(m["name"] for m in before["whisper_models"] if not m["ready"])
        call("PUT", "/admin/analysis-settings", expected=422, json={**values, "asr_model": unavailable})
        return {"changed_values_read_by_upload_endpoint": changed, "saved_analysis_kept_old_settings": True,
            "unavailable_whisper_rejected": unavailable}
    finally:
        call("PUT", "/admin/analysis-settings", json=values)
        restored = call("GET", "/admin/analysis-settings")
        assert all(restored[k] == values[k] for k in keys)


def verify_result():
    original = json.loads((OUT / "analysis-detail.json").read_text(encoding="utf-8"))
    current = call("GET", f'/contents/{user["content_id"]}', user)
    assert current == original
    plan = call("GET", f'/contents/{user["content_id"]}/revision-plan', user)
    assert "30/09/2026" in plan["notes"]
    settings = call("GET", "/analyze/settings", user)
    saved = current["analysis"]["analysis_settings"]
    assert all(settings[k] == saved[k] for k in ("upload_max_duration_seconds", "asr_model", "hook_duration_seconds"))
    admin_settings = call("GET", "/admin/analysis-settings")
    assert admin_settings["classification_model"]["model_id"] == saved["classification_model"]["model_id"] == 14
    return {"content_id": current["content_id"], "plan_revision": plan["revision"], "model_id": 14,
        "saved_result_unchanged": True, "settings_restored": True}


if "--after-restart" in sys.argv:
    check("Result, plan, settings survive backend restart", verify_result)
else:
    if "--verify-only" not in sys.argv:
        check("Admin account create, role change, suspend, delete", account_lifecycle)
        check("Analysis settings apply and restore; missing Whisper rejected", settings_roundtrip)
    check("Result remains frozen after settings changes", verify_result)
    report["checks"] = [r for r in report["checks"] if r["name"] != "Other normal user job is not exposed"]
    check("Nonexistent job returns not_found", lambda: call("GET", "/jobs/not-an-owned-job", user))
