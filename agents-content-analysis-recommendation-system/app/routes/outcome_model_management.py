from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.database.db import get_db
from app.database.models import User
from app.services import outcome_model_management as service


router = APIRouter(
    prefix="/admin/outcome-training",
    tags=["admin-outcome-training"],
    dependencies=[Depends(require_roles("admin"))],
)


class OutcomeTrainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


@router.get("/preflight")
def preflight(manifest_sha256: str | None = Query(default=None, pattern=r"^[a-f0-9]{64}$")):
    return service.outcome_preflight(manifest_sha256)


@router.get("/runs")
def runs(limit: int = Query(20, ge=1, le=50), db: Session = Depends(get_db)):
    return service.list_training_runs(db, limit=limit)


@router.post("/runs", status_code=202)
def start(
    payload: OutcomeTrainRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    try:
        return service.start_training_run(
            db, user_id=user.user_id, manifest_sha256=payload.manifest_sha256
        )
    except service.OutcomeTrainingConflict as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc


@router.get("/runs/{run_id}")
def run(run_id: UUID, db: Session = Depends(get_db)):
    result = service.get_training_run(db, str(run_id))
    if result is None:
        raise HTTPException(404, "Outcome training run not found")
    return result


@router.get("/models")
def models(
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return service.list_models(db, limit=limit, offset=offset)


@router.get("/models/{model_id}")
def detail(model_id: int, db: Session = Depends(get_db)):
    result = service.model_detail(db, model_id)
    if result is None:
        raise HTTPException(404, "Outcome model not found")
    return result
