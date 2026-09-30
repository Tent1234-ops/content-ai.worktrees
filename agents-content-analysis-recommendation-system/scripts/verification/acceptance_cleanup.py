"""Retire only the disposable admin created by this acceptance run."""
import json
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.database.db import SessionLocal
from app.database.models import User, UserTrendWatchSession
from app.services.persistence import log_system_event

out = ROOT / "artifacts/acceptance/20260930"
path = out / "private-admin.json"
account = json.loads(path.read_text())
uid = account["session"]["user"]["user_id"]
with SessionLocal() as db:
    user = db.get(User, uid)
    assert user.username == account["username"] and user.email == account["email"]
    assert user.username.startswith("acceptance_admin_")
    assert user.created_at >= datetime(2026, 9, 30)
    user.is_active = False
    revoked = db.query(UserTrendWatchSession).filter_by(user_id=uid, is_active=True).update(
        {"is_active": False, "ended_at": datetime.utcnow()}, synchronize_session=False)
    log_system_event(db, None, "acceptance_test_cleanup", "success", json.dumps({
        "disabled_disposable_admin_id": uid, "revoked_sessions": revoked,
        "note": "No pre-existing accounts modified. Test result retained for acceptance evidence."}))
    db.commit()
account["retired"] = True
path.write_text(json.dumps(account), encoding="utf-8")
summary = {"disabled_test_admin_id": uid, "test_user_id_retained": 13, "saved_content_id": 19,
    "test_datasets_in_trash": [428, 429], "temporary_lifecycle_user_deleted": 15}
(out / "cleanup.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary))
