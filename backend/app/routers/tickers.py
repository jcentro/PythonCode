from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.trade import Trade

router = APIRouter(prefix="/api/tickers", tags=["tickers"])


@router.get("", response_model=list[str])
def list_recent_tickers(
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[str]:
    stmt = (
        select(Trade.ticker)
        .group_by(Trade.ticker)
        .order_by(func.max(Trade.date).desc(), func.max(Trade.id).desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())
