import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Product, RecommendationEvent
from ..rate_limit import RECOMMEND_LIMIT, TRACK_VIEW_LIMIT, get_client_identifier, rate_limiter
from ..recommender import get_recommendations, get_similar_products, track_view_event
from ..schemas import TrackViewRequest
from ..security import get_optional_current_user

router = APIRouter(prefix="/api", tags=["Recommendations"])

SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,80}$")


def normalize_session_id(raw_value: Optional[str]) -> Optional[str]:
    if raw_value is None:
        return None

    value = raw_value.strip()
    if not value:
        return None

    if not SESSION_ID_PATTERN.fullmatch(value):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid session id")

    return value


@router.get("/recommendations")
def list_recommendations(
    request: Request,
    context_product_id: Optional[int] = Query(default=None),
    limit: int = Query(default=10, ge=1, le=24),
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-ID"),
    current_user: Optional[dict] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    identifier = get_client_identifier(request)
    rate_limiter.enforce("recommend", identifier, RECOMMEND_LIMIT)

    session_id = normalize_session_id(x_session_id)
    user_id = current_user["id"] if current_user else None

    if context_product_id is not None:
        product = db.query(Product.id).filter(Product.id == context_product_id, Product.is_active.is_(True)).first()
        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    recommendations = get_recommendations(
        db=db,
        user_id=user_id,
        session_id=session_id,
        context_product_id=context_product_id,
        limit=limit,
    )

    return {
        "count": len(recommendations),
        "products": recommendations,
    }


@router.get("/products/{product_id}/recommendations")
def similar_products(
    product_id: int,
    request: Request,
    limit: int = Query(default=8, ge=1, le=24),
    db: Session = Depends(get_db),
):
    identifier = get_client_identifier(request)
    rate_limiter.enforce("recommend", identifier, RECOMMEND_LIMIT)

    product = db.query(Product.id).filter(Product.id == product_id, Product.is_active.is_(True)).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    recommendations = get_similar_products(db=db, product_id=product_id, limit=limit)
    return {
        "count": len(recommendations),
        "products": recommendations,
    }


@router.post("/recommendations/track-view")
def track_view(
    payload: TrackViewRequest,
    request: Request,
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-ID"),
    current_user: Optional[dict] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    identifier = get_client_identifier(request)
    rate_limiter.enforce("recommend_track", identifier, TRACK_VIEW_LIMIT)

    session_id = normalize_session_id(x_session_id)
    user_id = current_user["id"] if current_user else None

    if user_id is None and session_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Session id or authenticated user required",
        )

    product = db.query(Product.id).filter(Product.id == payload.product_id, Product.is_active.is_(True)).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    recent_cutoff = datetime.utcnow() - timedelta(minutes=10)
    duplicate_query = db.query(RecommendationEvent.id).filter(
        RecommendationEvent.product_id == payload.product_id,
        RecommendationEvent.event_type == "view",
        RecommendationEvent.created_at >= recent_cutoff,
    )
    if user_id is not None:
        duplicate_query = duplicate_query.filter(RecommendationEvent.user_id == user_id)
    else:
        duplicate_query = duplicate_query.filter(RecommendationEvent.session_id == session_id)

    if duplicate_query.first():
        return {"status": "ok"}

    track_view_event(db=db, product_id=payload.product_id, user_id=user_id, session_id=session_id)
    db.commit()
    return {"status": "ok"}
