from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.database.db import get_db
from app.database.models import TaxonomyNode, User
from app.schemas.classification import ClassificationRequest, ClassificationResponse, TaxonomyResponse
from app.services.classification import classify_text_domain
from app.services.taxonomy import TAXONOMY_VERSION, serialize_taxonomy_nodes, taxonomy_coverage

router = APIRouter(prefix="/classification", tags=["classification"])


@router.get("/taxonomy", response_model=TaxonomyResponse)
def get_classification_taxonomy(
    _current_user: User = Depends(require_roles("admin", "user")),
    db: Session = Depends(get_db),
):
    coverage = taxonomy_coverage(db)
    nodes = (
        db.query(TaxonomyNode)
        .filter(TaxonomyNode.taxonomy_version == TAXONOMY_VERSION)
        .order_by(TaxonomyNode.level, TaxonomyNode.node_key)
        .all()
    )
    return TaxonomyResponse.model_validate(
        {
            **coverage,
            "nodes": serialize_taxonomy_nodes(nodes),
        }
    )


@router.post("/text", response_model=ClassificationResponse)
def classify_text(
    payload: ClassificationRequest,
    _current_user: User = Depends(require_roles("admin", "user")),
    db: Session = Depends(get_db),
):
    return ClassificationResponse.model_validate(
        classify_text_domain(
            db,
            title=payload.title,
            text=payload.text,
            source_prefix=payload.source,
            profile_limit=payload.profile_limit,
            top_k=payload.top_k,
        )
    )
