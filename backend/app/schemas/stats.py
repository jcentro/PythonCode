from typing import Literal

from pydantic import BaseModel


class SetupStatsRow(BaseModel):
    setup_id: int | None
    setup_name: str
    count: int
    total_pnl_usd: float
    win_rate: float


class StatsSummaryRead(BaseModel):
    total_trades: int
    total_pnl_usd: float
    # Win is defined as total_pnl_usd > 0. Breakeven counts as non-win.
    win_rate_overall: float
    by_setup: list[SetupStatsRow]


class EquityPointRead(BaseModel):
    date: str
    daily_pnl_usd: float
    cumulative_pnl_usd: float


class EquityCurveRead(BaseModel):
    points: list[EquityPointRead]


class StatsRangeRead(BaseModel):
    start: str
    end: str


class PnlSeriesPointRead(BaseModel):
    label: str
    start_date: str
    end_date: str
    trade_count: int
    total_pnl_usd: float


class PnlSeriesRead(BaseModel):
    range: StatsRangeRead
    group_by: Literal["daily", "weekly"]
    series: list[PnlSeriesPointRead]


class TimeOfDayBucketRead(BaseModel):
    label: str
    start_minute: int
    end_minute: int
    count: int
    total_pnl_usd: float
    win_rate: float
    avg_pnl_usd: float


class TimeOfDayRead(BaseModel):
    range: StatsRangeRead
    bucket: str
    excluded_missing_time: int
    buckets: list[TimeOfDayBucketRead]


class HoldTimeBucketRead(BaseModel):
    label: str
    min_seconds: int
    max_seconds: int | None
    count: int
    total_pnl_usd: float
    win_rate: float
    avg_pnl_usd: float


class HoldTimeRead(BaseModel):
    range: StatsRangeRead
    excluded_missing_duration: int
    buckets: list[HoldTimeBucketRead]


class StatsDefinitionsRead(BaseModel):
    win_rule: str
    breakeven_handling: str


class StatsOverallRead(BaseModel):
    total_trades: int
    total_pnl_usd: float
    win_rate: float
    avg_win_usd: float
    avg_loss_usd: float
    expectancy_usd_per_trade: float


class RuleFollowedBucketRead(BaseModel):
    count: int
    total_pnl_usd: float
    win_rate: float
    avg_pnl_usd: float


class ByRuleFollowedRead(BaseModel):
    followed: RuleFollowedBucketRead
    broken: RuleFollowedBucketRead


class EmotionInsightsRowRead(BaseModel):
    emotion_id: int | None
    emotion_name: str
    count: int
    total_pnl_usd: float
    win_rate: float
    avg_pnl_usd: float


class SetupInsightsRowRead(BaseModel):
    setup_id: int | None
    setup_name: str
    count: int
    total_pnl_usd: float
    win_rate: float
    avg_win_usd: float
    avg_loss_usd: float
    expectancy: float


class StatsRiskRead(BaseModel):
    max_drawdown_usd: float
    max_drawdown_start: str | None = None
    max_drawdown_end: str | None = None


class StatsStreaksRead(BaseModel):
    max_win_streak: int
    max_loss_streak: int
    current_streak_type: str
    current_streak_length: int


class StatsInsightItemRead(BaseModel):
    type: Literal["rule_adherence", "emotion", "expectancy", "behavior"]
    severity: Literal["info", "warning", "positive"]
    priority_score: int
    message: str
    data: dict[str, int | float | str | bool | None] | None = None


class StatsPatternItemRead(BaseModel):
    id: str
    title: str
    severity: Literal["info", "warning", "positive"]
    message: str
    sample_size: int
    data: dict[str, int | float | str | bool | None]
    filters: dict[str, int | float | str | bool | None]


class StatsInsightsRead(BaseModel):
    range: StatsRangeRead
    definitions: StatsDefinitionsRead
    overall: StatsOverallRead
    risk: StatsRiskRead
    streaks: StatsStreaksRead
    by_rule_followed: ByRuleFollowedRead
    by_emotion: list[EmotionInsightsRowRead]
    by_setup_optional: list[SetupInsightsRowRead]
    insights: list[StatsInsightItemRead]
    patterns: list[StatsPatternItemRead]
