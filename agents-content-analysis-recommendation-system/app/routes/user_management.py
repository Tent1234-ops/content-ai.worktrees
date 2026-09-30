from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.database.db import get_db
from app.database.models import User
from app.schemas.user_management import AccountRevision, CreateAccount, DeleteAccount, UpdateAccount
from app.services import user_management as service

router = APIRouter(prefix="/admin/users", tags=["admin-users"])
admin = require_roles("admin")


def _mutate(db: Session, operation):
    try:
        return operation()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "ชื่อหรืออีเมลซ้ำ หรือบัญชียังมีข้อมูลอ้างอิงที่ไม่สามารถเปลี่ยนได้") from exc
    except Exception:
        db.rollback()
        raise


@router.get("")
def list_users(q: str = Query("", max_length=255), role: Literal["all", "admin", "user"] = "all",
               state: Literal["all", "active", "inactive"] = "all", limit: int = Query(20, ge=1, le=100),
               offset: int = Query(0, ge=0), db: Session = Depends(get_db), actor: User = Depends(admin)):
    return service.list_accounts(db, actor_id=actor.user_id, query=q, role=role, state=state, limit=limit, offset=offset)


@router.get("/{user_id}")
def detail(user_id: int, db: Session = Depends(get_db), actor: User = Depends(admin)):
    return service.account_detail(db, user_id, actor_id=actor.user_id)


@router.post("", status_code=201)
def create(payload: CreateAccount, db: Session = Depends(get_db), actor: User = Depends(admin)):
    return _mutate(db, lambda: service.create_account(db, payload, actor_id=actor.user_id))


@router.put("/{user_id}")
def update(user_id: int, payload: UpdateAccount, db: Session = Depends(get_db), actor: User = Depends(admin)):
    return _mutate(db, lambda: service.update_account(db, user_id, payload, actor_id=actor.user_id))


@router.post("/{user_id}/revoke-sessions")
def revoke(user_id: int, payload: AccountRevision, db: Session = Depends(get_db), actor: User = Depends(admin)):
    return _mutate(db, lambda: service.revoke_sessions(db, user_id, payload.expected_revision, actor_id=actor.user_id))


@router.delete("/{user_id}")
def delete(user_id: int, payload: DeleteAccount, db: Session = Depends(get_db), actor: User = Depends(admin)):
    return _mutate(db, lambda: service.delete_account(db, user_id, payload.expected_revision, payload.confirmation, actor_id=actor.user_id))
