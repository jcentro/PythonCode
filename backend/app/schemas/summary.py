from datetime import date

from pydantic import BaseModel


class DailySummaryRead(BaseModel):
    date: date
    total_trades: int
    pct_rule_followed: float
    discipline_score: int
    total_pnl: float
    counts_by_setup: dict[str, int] | None = None
    counts_by_emotion: dict[str, int] | None = None
