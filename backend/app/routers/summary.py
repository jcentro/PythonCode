from collections import Counter
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models.trade import Trade
from app.schemas.summary import DailySummaryRead
from app.services.scoring import calculate_discipline_score
from app.services.trade_computation import trade_total_pnl_usd

router = APIRouter(prefix="/api/summary", tags=["summary"])


@router.get("/daily", response_model=DailySummaryRead)
def get_daily_summary(
    date: date = Query(...),
    db: Session = Depends(get_db),
) -> DailySummaryRead:
    trades = list(
        db.scalars(
            select(Trade)
            .options(
                selectinload(Trade.setup_option),
                selectinload(Trade.emotion_option),
                selectinload(Trade.fills),
            )
            .where(Trade.date == date)
        ).all()
    )

    total_trades = len(trades)
    if total_trades == 0:
        return DailySummaryRead(
            date=date,
            total_trades=0,
            pct_rule_followed=0.0,
            discipline_score=0,
            total_pnl=0.0,
            counts_by_setup={},
            counts_by_emotion={},
        )

    rule_followed_count = sum(1 for trade in trades if trade.rule_followed)
    pct_rule_followed = round((rule_followed_count / total_trades) * 100, 2)
    total_pnl = round(sum(trade_total_pnl_usd(trade) for trade in trades), 2)
    counts_by_setup = dict(Counter(trade.setup_name or "OTHER" for trade in trades))
    counts_by_emotion = dict(Counter(trade.emotion_name or "OTHER" for trade in trades))

    return DailySummaryRead(
        date=date,
        total_trades=total_trades,
        pct_rule_followed=pct_rule_followed,
        discipline_score=calculate_discipline_score(trades),
        total_pnl=total_pnl,
        counts_by_setup=counts_by_setup,
        counts_by_emotion=counts_by_emotion,
    )
