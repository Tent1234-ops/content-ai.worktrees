from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.database.db import get_db
from app.database.models import User
from app.services import model_management as service
from app.services.classification_collection_plan import preview_collection_channels

router = APIRouter(prefix="/admin/training", tags=["admin-training"], dependencies=[Depends(require_roles("admin"))])


class TrainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class ActivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_active_model_id: int | None = Field(..., gt=0)


class ChannelPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel_ids: list[str] = Field(min_length=1, max_length=50)


@router.post("/channel-preview")
def channel_preview(payload: ChannelPreviewRequest, db: Session = Depends(get_db)):
    try:
        return preview_collection_channels(db, payload.channel_ids)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("")
def overview(db: Session = Depends(get_db)):
    return service.training_overview(db)


@router.post("/runs", status_code=202)
def start(payload: TrainRequest, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    try:
        return service.start_training_run(db, user_id=user.user_id, dataset_fingerprint=payload.dataset_fingerprint)
    except service.TrainingConflict as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc


@router.get("/runs/{run_id}")
def run(run_id: UUID, db: Session = Depends(get_db)):
    result = service.get_training_run(db, str(run_id))
    if result is None:
        raise HTTPException(404, "Training run not found")
    return result


@router.get("/models")
def models(limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    return service.list_models(db, limit=limit, offset=offset)


@router.get("/models/{model_id}")
def detail(model_id: int, db: Session = Depends(get_db)):
    result = service.model_detail(db, model_id)
    if result is None:
        raise HTTPException(404, "Model not found")
    return result


@router.post("/models/{model_id}/activate")
def activate(model_id: int, payload: ActivateRequest, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    try:
        return service.activate_evaluated_model(db, model_id, expected_active_model_id=payload.expected_active_model_id, user_id=user.user_id)
    except service.TrainingConflict as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    except LookupError as exc:
        db.rollback()
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, OSError, RuntimeError) as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
