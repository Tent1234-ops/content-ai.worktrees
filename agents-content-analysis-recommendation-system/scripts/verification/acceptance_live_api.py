"""Real local API acceptance. Only uniquely marked test records are mutated."""
import json
from pathlib import Path
import secrets
import sys
from datetime import datetime, timezone

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.core.config import settings

OUT = ROOT / "artifacts/acceptance/20260930"
BASE = "http://127.0.0.1:8000"
OUT.mkdir(parents=True, exist_ok=True)
report = {"started_at": datetime.now(timezone.utc).isoformat(), "checks": [], "readbacks": {}}


def save(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def call(method, path, session=None, expected=200, **kwargs):
    headers = {} if not session else {"Authorization": "Bearer " + session["access_token"],
        "X-Trend-Session-Key": session["session_key"]}
    response = requests.request(method, BASE + path, headers=headers, timeout=90, **kwargs)
    assert response.status_code == expected, f"{method} {path}: {response.status_code} {response.text[:350]}"
    return response.json()


def check(name, operation):
    try:
        details = operation()
        report["checks"].append({"name": name, "status": "passed", "details": details})
        print("PASS " + name, flush=True)
    except Exception as exc:
        report["checks"].append({"name": name, "status": "failed", "error": str(exc)})
        print("FAIL " + name + ": " + str(exc), flush=True)
    save("api.json", report)


user = json.loads((OUT / "private-session.json").read_text())
user_session = user["session"]
admin_path = OUT / "private-admin.json"
if admin_path.exists() and not json.loads(admin_path.read_text()).get("retired"):
    admin = json.loads(admin_path.read_text())
else:
    suffix = secrets.token_hex(5)
    admin = {"username": "acceptance_admin_" + suffix, "email": f"acceptance_admin_{suffix}@example.com",
        "password": secrets.token_hex(18)}
    call("POST", "/auth/register", expected=201, json={**admin, "role": "admin", "admin_invite_code": settings.admin_invite_code})
admin["session"] = call("POST", "/auth/login", json={"email": admin["email"], "password": admin["password"]})
save("private-admin.json", admin)
session = admin["session"]
check("Admin login and role", lambda: call("GET", "/admin/me", session)["message"])

for route in ["/contents/my", "/analyze/settings", "/admin/datasets", "/admin/users", "/admin/training"]:
    check("Anonymous denied " + route, lambda r=route: call("GET", r, expected=401))
for route in ["/admin/users", "/admin/datasets", "/admin/analysis-settings", "/admin/training"]:
    check("User denied " + route, lambda r=route: call("GET", r, user_session, expected=403))

paths = ["/admin/users", "/admin/training", "/admin/training/models", "/admin/datasets",
    "/admin/datasets?trashed=true", "/admin/datasets/readiness", "/admin/dataset-review/queue",
    "/admin/analysis-settings", "/admin/trend-settings", "/admin/reference-statistics",
    "/admin/sources/health", "/admin/logs", "/admin/clusters/runs", "/admin/reports/overview",
    "/admin/usage-statistics?year=2026&month=9", "/contents/statistics?year=2026&month=9",
    "/contents/statistics?year=2026", "/notifications/"]


def inspect(route):
    data = call("GET", route, user_session if route.startswith(("/contents", "/notifications")) else session)
    filename = route.strip("/").replace("/", "-").replace("?", "-").replace("&", "-").replace("=", "-") + ".json"
    save(filename, data)
    report["readbacks"][route] = filename
    return {"keys": list(data) if isinstance(data, dict) else [], "total": data.get("total") if isinstance(data, dict) else len(data)}


for route in paths:
    check("Read " + route, lambda r=route: inspect(r))


def follow_roundtrip():
    preferences = call("GET", "/follows/preferences", user_session)
    category = preferences["categories"][0]
    values = {"match_type": "category", "platform": "youtube", "value": category["id"]}
    first = call("POST", "/follows/topic", user_session, json=values)
    second = call("POST", "/follows/topic", user_session, json=values)
    assert first["id"] == second["id"]
    try:
        call("PUT", "/follows/preferences", user_session, json={"notification_mode": "following"})
        assert call("GET", "/follows/preferences", user_session)["notification_mode"] == "following"
        assert any(row["id"] == first["id"] for row in call("GET", "/follows/topics", user_session)["items"])
    finally:
        call("DELETE", f'/follows/topic/{first["id"]}', user_session)
        call("PUT", "/follows/preferences", user_session, json={"notification_mode": preferences["notification_mode"]})
    return {"category": category, "duplicate_prevented": True, "restored_preferences": True,
        "notification_delivery": "not verified: no new live trend inserted for test"}


check("Category follow, deduplication, preferences, unfollow", follow_roundtrip)


def dataset_roundtrip():
    row = call("POST", "/admin/datasets", session, json={"title": "ACCEPTANCE ONLY 20260930 " + secrets.token_hex(4),
        "transcript": "Acceptance test placeholder. Not training or recommendation evidence.",
        "dataset_source": "acceptance_test", "dataset_version": "acceptance-20260930", "source_platform": "manual_test",
        "is_active": False, "is_training_eligible": False})
    did = row["dataset_id"]
    report["temporary_dataset_id"] = did
    save("api.json", report)
    try:
        changed = call("PUT", f"/admin/datasets/{did}", session, json={"transcript": "Corrected acceptance text " + secrets.token_hex(8), "taxonomy_leaf_key": "phone"})
        assert changed["transcript_sha256"] and changed["taxonomy_leaf_key"] == "phone"
        assert not changed["is_active"] and not changed["is_training_eligible"]
        call("DELETE", f"/admin/datasets/{did}?confirmation_id={did + 999999}", session, expected=422)
        call("DELETE", f"/admin/datasets/{did}?confirmation_id={did}", session)
        trash = call("GET", "/admin/datasets?trashed=true&limit=100", session)
        assert any(r["dataset_id"] == did for r in trash["items"])
        restored = call("POST", f"/admin/datasets/{did}/restore?confirmation_id={did}", session)
        assert restored["deleted_at"] is None and not restored["is_training_eligible"]
        return {"dataset_id": did, "transcript_hash_updated": True, "taxonomy_corrected": True,
            "delete_restore": True, "never_training_eligible": True}
    finally:
        # Keep the marked test row in trash, not mixed into ordinary data or evidence.
        call("DELETE", f"/admin/datasets/{did}?confirmation_id={did}", session)


check("Dataset create/correct/delete/restore via real API", dataset_roundtrip)

user = json.loads((OUT / "private-session.json").read_text())
if user.get("content_id"):
    check("Other user cannot read saved analysis", lambda: call("GET", f'/contents/{user["content_id"]}', session, expected=404))
    check("Other user cannot read saved plan", lambda: call("GET", f'/contents/{user["content_id"]}/revision-plan', session, expected=404))
check("Invalid video rejected", lambda: call("POST", "/analyze/save", user_session, expected=422,
    files={"file": ("acceptance-invalid.mp4", b"not a video", "video/mp4")}))
report["finished_at"] = datetime.now(timezone.utc).isoformat()
save("api.json", report)
