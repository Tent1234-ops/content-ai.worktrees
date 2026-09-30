from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.database.db import get_db
from app.database.models import User
from app.schemas.nlp import NLPRequest, NLPResponse, NLPSaveRequest, NLPSaveResponse
from app.services.nlp import run_nlp_pipeline
from app.services.persistence import save_nlp_result

router = APIRouter(prefix="/nlp", tags=["nlp"])


@router.post("/extract", response_model=NLPResponse)
def extract_nlp(
    payload: NLPRequest,
    _current_user: User = Depends(require_roles("admin", "user")),
):
    return NLPResponse.model_validate(run_nlp_pipeline(payload.text, payload.max_keywords))


@router.post("/extract/save", response_model=NLPSaveResponse)
def extract_nlp_and_save(
    payload: NLPSaveRequest,
    current_user: User = Depends(require_roles("admin", "user")),
    db: Session = Depends(get_db),
):
    result = run_nlp_pipeline(payload.text, payload.max_keywords)
    saved = save_nlp_result(
        db,
        user=current_user,
        title=payload.title,
        text=payload.text,
        nlp_result=result,
    )
    return NLPSaveResponse(
        content_id=saved["content_id"],
        saved_keywords=saved["saved_keywords"],
        result=NLPResponse.model_validate(result),
    )
