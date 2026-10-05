"""Explicit, expiring presentation authorization, separate from qualification."""
from datetime import datetime, timezone

from app.services.classification_acceptance import is_presentation_acceptance_policy


PRESENTATION_STATUS = "presentation_only"
PRESENTATION_WARNING = (
    "โหมดสาธิตชั่วคราว: โมเดลนี้ยังไม่ผ่านเกณฑ์ความถูกต้องรายหมวด 80% "
    "และยังไม่ได้ตรวจรับกับชุด Test รอบใหม่ ผลหมวดและคำแนะนำอาจผิดพลาด"
)


def presentation_authorization(payload: dict, *, now: datetime | None = None) -> dict:
    grant = payload.get("presentation_authorization")
    result = {"authorized": False, "reason": "presentation_not_authorized"}
    if not isinstance(grant, dict):
        return result
    try:
        issued = datetime.fromisoformat(grant["issued_at"])
        expires = datetime.fromisoformat(grant["expires_at"])
        current = now or datetime.now(timezone.utc)
        valid = (
            grant.get("version") == "presentation-authorization-v1"
            and grant.get("risk_acknowledged") is True
            and isinstance(grant.get("authorized_by"), int) and grant["authorized_by"] > 0
            and bool(str(grant.get("reason") or "").strip())
            and grant.get("model_key") == payload.get("model_key")
            and grant.get("model_version") == payload.get("model_version")
            and issued.tzinfo is not None and expires.tzinfo is not None
            and 0 < (expires - issued).total_seconds() <= 72 * 3600
            and is_presentation_acceptance_policy(payload.get("scope_policy"))
            and payload.get("scope_test_passed") is False
        )
        if not valid:
            return result
        result.update(expires_at=expires.isoformat(), issued_at=issued.isoformat(),
                      authorized_by=grant["authorized_by"], warning=PRESENTATION_WARNING)
        if not issued <= current < expires:
            result["reason"] = "presentation_expired"
            return result
        result.update(authorized=True, reason="presentation_unqualified")
    except (KeyError, ValueError, TypeError, OverflowError):
        pass
    return result
