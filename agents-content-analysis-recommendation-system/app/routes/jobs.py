from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.deps import get_current_user
from app.database.models import User
from app.services.jobs import get_status

router = APIRouter()


@router.get("/jobs/{job_id}")
def job_status(job_id: str, current_user: User = Depends(get_current_user)):
    s = get_status(job_id, requester_user_id=current_user.user_id,
                   requester_role=current_user.role)
    return JSONResponse(content=s)
