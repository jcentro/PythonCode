from datetime import date, time, timedelta
from math import floor
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models.trade import Trade
from app.schemas.stats import (
    ByRuleFollowedRead,
    EmotionInsightsRowRead,
    EquityCurveRead,
    EquityPointRead,
    HoldTimeBucketRead,
    HoldTimeRead,
    PnlSeriesPointRead,
    PnlSeriesRead,
    RuleFollowedBucketRead,
    SetupInsightsRowRead,
    SetupStatsRow,
    StatsDefinitionsRead,
    StatsInsightItemRead,
    StatsInsightsRead,
    StatsOverallRead,
    StatsPatternItemRead,
    StatsRangeRead,
    StatsRiskRead,
    StatsStreaksRead,
    StatsSummaryRead,
    TimeOfDayBucketRead,
    TimeOfDayRead,
)
from app.services.trade_computation import trade_total_pnl_usd

router = APIRouter(prefix="/api/stats", tags=["stats"])
INSIGHT_SEVERITY_PRIORITY = {"warning": 3, "positive": 2, "info": 1}
MIN_PATTERN_SAMPLE_SIZE = 5
MIN_PATTERN_MEANINGFUL_AVG_ABS = 0.01
HOLD_TIME_BUCKETS: list[tuple[str, int, int | None]] = [
    ("0-2m", 0, 120),
    ("2-5m", 120, 300),
    ("5-10m", 300, 600),
    ("10-20m", 600, 1200),
    ("20-45m", 1200, 2700),
    ("45-90m", 2700, 5400),
    ("90m+", 5400, None),
]


def _trade_total_pnl_usd(trade: Trade) -> float:
    return trade_total_pnl_usd(trade)


def _validate_date_range(start: date | None, end: date | None) -> None:
    if start is not None and end is not None and start > end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start must be less than or equal to end",
        )


def _build_filtered_trades_query(start: date | None, end: date | None):
    stmt = select(Trade).options(
        selectinload(Trade.setup_option),
        selectinload(Trade.emotion_option),
        selectinload(Trade.fills),
    )
    if start is not None:
        stmt = stmt.where(Trade.date >= start)
    if end is not None:
        stmt = stmt.where(Trade.date <= end)
    return stmt


def _build_daily_totals(trades: list[Trade]) -> dict[date, float]:
    daily_totals: dict[date, float] = {}
    for trade in trades:
        daily_totals[trade.date] = daily_totals.get(trade.date, 0.0) + _trade_total_pnl_usd(trade)
    return daily_totals


def _resolve_all_time_output_range(
    trades: list[Trade], start: date | None, end: date | None
) -> StatsRangeRead:
    if start is not None or end is not None:
        return StatsRangeRead(
            start=start.isoformat() if start is not None else "",
            end=end.isoformat() if end is not None else "",
        )

    if not trades:
        return StatsRangeRead(start="", end="")

    trade_dates = [trade.date for trade in trades]
    return StatsRangeRead(
        start=min(trade_dates).isoformat(),
        end=max(trade_dates).isoformat(),
    )


def _resolve_insights_date_range(start: date | None, end: date | None) -> tuple[date, date]:
    # Default behavior for insights: last 30 days including today.
    today = date.today()
    resolved_start = start
    resolved_end = end
    if resolved_start is None and resolved_end is None:
        resolved_end = today
        resolved_start = today - timedelta(days=29)
    elif resolved_start is None:
        resolved_start = resolved_end - timedelta(days=29)
    elif resolved_end is None:
        resolved_end = today

    _validate_date_range(resolved_start, resolved_end)
    return resolved_start, resolved_end


def _resolve_time_of_day_date_range(start: date | None, end: date | None) -> tuple[date, date]:
    # Default behavior matches analytics endpoints: last 30 days including today.
    return _resolve_insights_date_range(start, end)


def _resolve_hold_time_date_range(start: date | None, end: date | None) -> tuple[date, date]:
    # Default behavior matches analytics endpoints: last 30 days including today.
    return _resolve_insights_date_range(start, end)


def _compute_win_loss_metrics(
    pnl_values: list[float],
) -> tuple[float, float, float, float]:
    winning_trades = [value for value in pnl_values if value > 0]
    losing_trades = [value for value in pnl_values if value < 0]
    decisive_trade_count = len(winning_trades) + len(losing_trades)

    win_rate = len(winning_trades) / decisive_trade_count if decisive_trade_count else 0.0
    avg_win_usd = sum(winning_trades) / len(winning_trades) if winning_trades else 0.0
    avg_loss_usd = sum(losing_trades) / len(losing_trades) if losing_trades else 0.0
    expectancy = (win_rate * avg_win_usd) + ((1 - win_rate) * avg_loss_usd)
    return win_rate, avg_win_usd, avg_loss_usd, expectancy


def _trade_sort_key(trade: Trade) -> tuple[date, int, time, int]:
    return (
        trade.date,
        1 if trade.entry_time is None else 0,
        trade.entry_time or time.max,
        trade.id,
    )


def _pattern_severity_for_avg(avg_pnl_usd: float) -> Literal["warning", "positive", "info"]:
    if avg_pnl_usd < 0:
        return "warning"
    if avg_pnl_usd > 0:
        return "positive"
    return "info"


def _build_pattern_metrics(pnl_values: list[float]) -> dict[str, int | float]:
    count = len(pnl_values)
    total_pnl_usd = sum(pnl_values)
    avg_pnl_usd = total_pnl_usd / count if count else 0.0
    win_rate, _, _, _ = _compute_win_loss_metrics(pnl_values)
    return {
        "count": count,
        "total_pnl_usd": round(total_pnl_usd, 2),
        "win_rate": round(win_rate, 4),
        "avg_pnl_usd": round(avg_pnl_usd, 2),
    }


def _generate_patterns(trades: list[Trade]) -> list[StatsPatternItemRead]:
    if not trades:
        return []

    sorted_trades = sorted(trades, key=_trade_sort_key)
    patterns: list[StatsPatternItemRead] = []

    # Pattern 1: After 2 losses in a row -> next trade.
    next_trade_pnls_after_two_losses: list[float] = []
    for index in range(2, len(sorted_trades)):
        prev_two = sorted_trades[index - 2 : index]
        if all(_trade_total_pnl_usd(trade) < 0 for trade in prev_two):
            next_trade_pnls_after_two_losses.append(_trade_total_pnl_usd(sorted_trades[index]))

    next_trade_metrics = _build_pattern_metrics(next_trade_pnls_after_two_losses)
    next_trade_sample_size = int(next_trade_metrics["count"])
    next_trade_avg = float(next_trade_metrics["avg_pnl_usd"])
    if (
        next_trade_sample_size >= MIN_PATTERN_SAMPLE_SIZE
        and abs(next_trade_avg) >= MIN_PATTERN_MEANINGFUL_AVG_ABS
    ):
        next_trade_win_rate_label = _emphasize(
            _format_percent(float(next_trade_metrics["win_rate"]))
        )
        patterns.append(
            StatsPatternItemRead(
                id="after_2_losses_next_trade",
                title="After 2 losses in a row",
                severity=_pattern_severity_for_avg(next_trade_avg),
                message=(
                    "After 2 consecutive losses, your next trade averages "
                    f"{_emphasize(_format_usd_signed(next_trade_avg))} "
                    f"(win rate {next_trade_win_rate_label}, "
                    f"n={next_trade_sample_size})."
                ),
                sample_size=next_trade_sample_size,
                data={
                    **next_trade_metrics,
                    "impact_usd": next_trade_avg,
                },
                filters={"pattern": "after_2_losses_next_trade"},
            )
        )

    # Pattern 2: First 3 trades vs 4+ trades in a day.
    first_three_pnls: list[float] = []
    after_three_pnls: list[float] = []
    trades_by_date: dict[date, list[Trade]] = {}
    for trade in sorted_trades:
        trades_by_date.setdefault(trade.date, []).append(trade)

    for day_trades in trades_by_date.values():
        for index, trade in enumerate(day_trades, start=1):
            pnl_value = _trade_total_pnl_usd(trade)
            if index <= 3:
                first_three_pnls.append(pnl_value)
            else:
                after_three_pnls.append(pnl_value)

    first_three_metrics = _build_pattern_metrics(first_three_pnls)
    after_three_metrics = _build_pattern_metrics(after_three_pnls)
    first_three_avg = float(first_three_metrics["avg_pnl_usd"])
    after_three_avg = float(after_three_metrics["avg_pnl_usd"])
    after_three_sample_size = int(after_three_metrics["count"])
    avg_delta = first_three_avg - after_three_avg
    if (
        after_three_sample_size >= MIN_PATTERN_SAMPLE_SIZE
        and avg_delta >= MIN_PATTERN_MEANINGFUL_AVG_ABS
    ):
        patterns.append(
            StatsPatternItemRead(
                id="trade_index_after_3",
                title="Trade count per day: first 3 vs 4+",
                severity="warning",
                message=(
                    "Your first 3 trades average "
                    f"{_emphasize(_format_usd_signed(first_three_avg))}. "
                    "Trades 4+ average "
                    f"{_emphasize(_format_usd_signed(after_three_avg))} "
                    f"(n={after_three_sample_size})."
                ),
                sample_size=after_three_sample_size,
                data={
                    "first_3_count": int(first_three_metrics["count"]),
                    "first_3_total_pnl_usd": float(first_three_metrics["total_pnl_usd"]),
                    "first_3_win_rate": float(first_three_metrics["win_rate"]),
                    "first_3_avg_pnl_usd": first_three_avg,
                    "after_3_count": after_three_sample_size,
                    "after_3_total_pnl_usd": float(after_three_metrics["total_pnl_usd"]),
                    "after_3_win_rate": float(after_three_metrics["win_rate"]),
                    "after_3_avg_pnl_usd": after_three_avg,
                    "avg_delta_usd": round(avg_delta, 2),
                    "impact_usd": round(avg_delta, 2),
                },
                filters={"pattern": "trade_index_after_3"},
            )
        )

    # Pattern 3: Worst time-of-day bucket by average PnL.
    time_bucket_pnls: dict[int, list[float]] = {}
    for trade in sorted_trades:
        if trade.entry_time is None:
            continue
        bucket_start = trade.entry_time.hour * 60
        time_bucket_pnls.setdefault(bucket_start, []).append(_trade_total_pnl_usd(trade))

    if time_bucket_pnls:
        worst_time_bucket_start, worst_time_bucket_values = min(
            time_bucket_pnls.items(),
            key=lambda item: (
                (sum(item[1]) / len(item[1])) if item[1] else 0.0,
                sum(item[1]),
                item[0],
            ),
        )
        worst_time_metrics = _build_pattern_metrics(worst_time_bucket_values)
        worst_time_count = int(worst_time_metrics["count"])
        worst_time_avg = float(worst_time_metrics["avg_pnl_usd"])
        if (
            worst_time_count >= MIN_PATTERN_SAMPLE_SIZE
            and abs(worst_time_avg) >= MIN_PATTERN_MEANINGFUL_AVG_ABS
        ):
            hour = worst_time_bucket_start // 60
            label = f"{hour:02d}:00-{hour:02d}:59"
            worst_time_win_rate_label = _emphasize(
                _format_percent(float(worst_time_metrics["win_rate"]))
            )
            patterns.append(
                StatsPatternItemRead(
                    id="worst_time_of_day_bucket",
                    title="Worst time of day",
                    severity=_pattern_severity_for_avg(worst_time_avg),
                    message=(
                        "Your worst time window is "
                        f"{_emphasize(label)}: {_emphasize(_format_usd_signed(worst_time_avg))} "
                        "avg PnL "
                        f"(win rate {worst_time_win_rate_label}, "
                        f"n={worst_time_count})."
                    ),
                    sample_size=worst_time_count,
                    data={
                        **worst_time_metrics,
                        "label": label,
                        "start_minute": worst_time_bucket_start,
                        "end_minute": worst_time_bucket_start + 60,
                        "impact_usd": worst_time_avg,
                    },
                    filters={
                        "entry_time_start_minute": worst_time_bucket_start,
                        "entry_time_end_minute": worst_time_bucket_start + 60,
                    },
                )
            )

    # Pattern 4: Worst hold-time bucket by average PnL.
    hold_time_bucket_pnls: dict[int, list[float]] = {
        index: [] for index in range(len(HOLD_TIME_BUCKETS))
    }
    for trade in sorted_trades:
        if trade.duration_seconds is None:
            continue
        for index, (_, min_seconds, max_seconds) in enumerate(HOLD_TIME_BUCKETS):
            if max_seconds is None and trade.duration_seconds >= min_seconds:
                hold_time_bucket_pnls[index].append(_trade_total_pnl_usd(trade))
                break
            if max_seconds is not None and min_seconds <= trade.duration_seconds < max_seconds:
                hold_time_bucket_pnls[index].append(_trade_total_pnl_usd(trade))
                break

    non_empty_hold_time_buckets = [
        (index, values) for index, values in hold_time_bucket_pnls.items() if values
    ]
    if non_empty_hold_time_buckets:
        worst_hold_time_index, worst_hold_time_values = min(
            non_empty_hold_time_buckets,
            key=lambda item: (
                (sum(item[1]) / len(item[1])) if item[1] else 0.0,
                sum(item[1]),
                item[0],
            ),
        )
        label, min_seconds, max_seconds = HOLD_TIME_BUCKETS[worst_hold_time_index]
        worst_hold_time_metrics = _build_pattern_metrics(worst_hold_time_values)
        worst_hold_time_count = int(worst_hold_time_metrics["count"])
        worst_hold_time_avg = float(worst_hold_time_metrics["avg_pnl_usd"])
        if (
            worst_hold_time_count >= MIN_PATTERN_SAMPLE_SIZE
            and abs(worst_hold_time_avg) >= MIN_PATTERN_MEANINGFUL_AVG_ABS
        ):
            worst_hold_time_win_rate_label = _emphasize(
                _format_percent(float(worst_hold_time_metrics["win_rate"]))
            )
            patterns.append(
                StatsPatternItemRead(
                    id="worst_hold_time_bucket",
                    title="Worst hold time",
                    severity=_pattern_severity_for_avg(worst_hold_time_avg),
                    message=(
                        f"Trades held {_emphasize(label)} average "
                        f"{_emphasize(_format_usd_signed(worst_hold_time_avg))} "
                        f"(win rate {worst_hold_time_win_rate_label}, "
                        f"n={worst_hold_time_count})."
                    ),
                    sample_size=worst_hold_time_count,
                    data={
                        **worst_hold_time_metrics,
                        "label": label,
                        "min_seconds": min_seconds,
                        "max_seconds": max_seconds,
                        "impact_usd": worst_hold_time_avg,
                    },
                    filters={
                        "hold_time_min_seconds": min_seconds,
                        "hold_time_max_seconds": max_seconds,
                    },
                )
            )

    def pattern_abs_impact(pattern: StatsPatternItemRead) -> float:
        impact_value = pattern.data.get("impact_usd")
        if isinstance(impact_value, int | float):
            return abs(float(impact_value))
        return 0.0

    patterns.sort(
        key=lambda pattern: (
            -INSIGHT_SEVERITY_PRIORITY.get(pattern.severity, 1),
            -pattern_abs_impact(pattern),
            pattern.id,
        )
    )
    return patterns


def _build_rule_followed_bucket(trades: list[Trade]) -> RuleFollowedBucketRead:
    pnl_values = [_trade_total_pnl_usd(trade) for trade in trades]
    total_pnl_usd = sum(pnl_values)
    trade_count = len(trades)
    avg_pnl_usd = total_pnl_usd / trade_count if trade_count else 0.0
    win_rate, _, _, _ = _compute_win_loss_metrics(pnl_values)

    return RuleFollowedBucketRead(
        count=trade_count,
        total_pnl_usd=round(total_pnl_usd, 2),
        win_rate=round(win_rate, 4),
        avg_pnl_usd=round(avg_pnl_usd, 2),
    )


def _compute_streaks(trades: list[Trade]) -> StatsStreaksRead:
    sorted_trades = sorted(trades, key=lambda trade: (trade.date, trade.id))

    max_win_streak = 0
    max_loss_streak = 0
    current_type = "none"
    current_length = 0

    for trade in sorted_trades:
        pnl_value = _trade_total_pnl_usd(trade)
        if pnl_value > 0:
            next_type = "win"
        elif pnl_value < 0:
            next_type = "loss"
        else:
            next_type = "none"

        if next_type == "none":
            current_type = "none"
            current_length = 0
            continue

        if current_type == next_type:
            current_length += 1
        else:
            current_type = next_type
            current_length = 1

        if next_type == "win":
            max_win_streak = max(max_win_streak, current_length)
        else:
            max_loss_streak = max(max_loss_streak, current_length)

    return StatsStreaksRead(
        max_win_streak=max_win_streak,
        max_loss_streak=max_loss_streak,
        current_streak_type=current_type,
        current_streak_length=current_length,
    )


def _compute_drawdown_from_daily_totals(daily_totals: dict[date, float]) -> StatsRiskRead:
    if not daily_totals:
        return StatsRiskRead(
            max_drawdown_usd=0.0,
            max_drawdown_start=None,
            max_drawdown_end=None,
        )

    cumulative = 0.0
    peak_value = 0.0
    peak_date = min(daily_totals).isoformat()
    max_drawdown = 0.0
    max_drawdown_start: str | None = None
    max_drawdown_end: str | None = None

    for trade_date in sorted(daily_totals):
        cumulative += daily_totals[trade_date]

        if cumulative > peak_value:
            peak_value = cumulative
            peak_date = trade_date.isoformat()

        drawdown = peak_value - cumulative
        if drawdown > max_drawdown:
            max_drawdown = drawdown
            max_drawdown_start = peak_date
            max_drawdown_end = trade_date.isoformat()

    return StatsRiskRead(
        max_drawdown_usd=round(max_drawdown, 2),
        max_drawdown_start=max_drawdown_start,
        max_drawdown_end=max_drawdown_end,
    )


def _round_dollars(value: float) -> int:
    return floor(abs(value) + 0.5)


def _format_usd_abs(value: float) -> str:
    return f"${_round_dollars(value)}"


def _format_usd_signed(value: float) -> str:
    sign = "+" if value >= 0 else "-"
    return f"{sign}${_round_dollars(value)}"


def _format_percent(value: float) -> str:
    percent_value = round(value * 100, 1)
    label = f"{percent_value:.1f}".rstrip("0").rstrip(".")
    return f"{label}%"


def _emphasize(value: str) -> str:
    return f"**{value}**"


def _generate_insights(
    overall: StatsOverallRead,
    by_rule_followed: ByRuleFollowedRead,
    by_emotion_rows: list[EmotionInsightsRowRead],
) -> list[StatsInsightItemRead]:
    if overall.total_trades == 0:
        return []

    insights: list[StatsInsightItemRead] = []

    def add_insight(
        *,
        insight_type: str,
        severity: str,
        message: str,
        data: dict[str, int | float | str | bool | None] | None = None,
    ) -> None:
        insights.append(
            StatsInsightItemRead(
                type=insight_type,
                severity=severity,
                priority_score=INSIGHT_SEVERITY_PRIORITY.get(severity, 1),
                message=message,
                data=data,
            )
        )

    followed = by_rule_followed.followed
    broken = by_rule_followed.broken
    if followed.count > 0 and broken.count > 0:
        if followed.total_pnl_usd > 0 and broken.total_pnl_usd < 0:
            followed_usd = _emphasize(_format_usd_abs(followed.total_pnl_usd))
            broken_usd = _emphasize(_format_usd_abs(broken.total_pnl_usd))
            add_insight(
                insight_type="rule_adherence",
                severity="positive",
                message=(
                    f"Your disciplined trades are up {followed_usd}. "
                    f"Rule-breaking trades are down {broken_usd}."
                ),
                data={
                    "followed_total_pnl_usd": followed.total_pnl_usd,
                    "broken_total_pnl_usd": broken.total_pnl_usd,
                    "impact_usd": max(abs(followed.total_pnl_usd), abs(broken.total_pnl_usd)),
                },
            )
        elif followed.total_pnl_usd > 0:
            followed_usd = _emphasize(_format_usd_abs(followed.total_pnl_usd))
            add_insight(
                insight_type="rule_adherence",
                severity="positive",
                message=f"Your disciplined trades are up {followed_usd}.",
                data={
                    "followed_total_pnl_usd": followed.total_pnl_usd,
                    "impact_usd": followed.total_pnl_usd,
                },
            )
        elif broken.total_pnl_usd < 0:
            broken_usd = _emphasize(_format_usd_abs(broken.total_pnl_usd))
            add_insight(
                insight_type="rule_adherence",
                severity="warning",
                message=f"Breaking your rules has cost you {broken_usd}.",
                data={
                    "broken_total_pnl_usd": broken.total_pnl_usd,
                    "impact_usd": broken.total_pnl_usd,
                },
            )
    elif broken.count > 0 and broken.total_pnl_usd < 0:
        broken_usd = _emphasize(_format_usd_abs(broken.total_pnl_usd))
        add_insight(
            insight_type="rule_adherence",
            severity="warning",
            message=f"Breaking your rules has cost you {broken_usd}.",
            data={
                "broken_total_pnl_usd": broken.total_pnl_usd,
                "impact_usd": broken.total_pnl_usd,
            },
        )
    elif followed.count > 0 and followed.total_pnl_usd > 0:
        followed_usd = _emphasize(_format_usd_abs(followed.total_pnl_usd))
        add_insight(
            insight_type="rule_adherence",
            severity="positive",
            message=f"Your disciplined trades are up {followed_usd}.",
            data={
                "followed_total_pnl_usd": followed.total_pnl_usd,
                "impact_usd": followed.total_pnl_usd,
            },
        )

    if by_emotion_rows:
        worst_emotion = min(by_emotion_rows, key=lambda row: row.total_pnl_usd)
        if worst_emotion.total_pnl_usd < 0:
            add_insight(
                insight_type="emotion",
                severity="warning",
                message=(
                    f"{worst_emotion.emotion_name} trades are down "
                    f"{_emphasize(_format_usd_abs(worst_emotion.total_pnl_usd))} with a "
                    f"{_emphasize(_format_percent(worst_emotion.win_rate))} win rate."
                ),
                data={
                    "emotion_id": worst_emotion.emotion_id,
                    "emotion_name": worst_emotion.emotion_name,
                    "total_pnl_usd": worst_emotion.total_pnl_usd,
                    "win_rate": worst_emotion.win_rate,
                    "impact_usd": worst_emotion.total_pnl_usd,
                },
            )

        best_emotion = max(by_emotion_rows, key=lambda row: row.total_pnl_usd)
        if best_emotion.total_pnl_usd > 0 and best_emotion.count >= 2:
            add_insight(
                insight_type="emotion",
                severity="positive",
                message=(
                    f"You perform best when {best_emotion.emotion_name}: up "
                    f"{_emphasize(_format_usd_abs(best_emotion.total_pnl_usd))}, "
                    f"{_emphasize(_format_percent(best_emotion.win_rate))} win rate."
                ),
                data={
                    "emotion_id": best_emotion.emotion_id,
                    "emotion_name": best_emotion.emotion_name,
                    "total_pnl_usd": best_emotion.total_pnl_usd,
                    "win_rate": best_emotion.win_rate,
                    "impact_usd": best_emotion.total_pnl_usd,
                },
            )

    if overall.expectancy_usd_per_trade < 0:
        add_insight(
            insight_type="expectancy",
            severity="warning",
            message=(
                "Your edge is currently negative: "
                f"{_emphasize(_format_usd_signed(overall.expectancy_usd_per_trade))} per trade."
            ),
            data={
                "expectancy_usd_per_trade": overall.expectancy_usd_per_trade,
                "impact_usd": overall.expectancy_usd_per_trade,
            },
        )
    elif overall.expectancy_usd_per_trade > 0:
        add_insight(
            insight_type="expectancy",
            severity="positive",
            message=(
                "Your edge is positive: "
                f"{_emphasize(_format_usd_signed(overall.expectancy_usd_per_trade))} per trade."
            ),
            data={
                "expectancy_usd_per_trade": overall.expectancy_usd_per_trade,
                "impact_usd": overall.expectancy_usd_per_trade,
            },
        )

    if overall.total_trades > 10 and overall.win_rate < 0.5:
        add_insight(
            insight_type="behavior",
            severity="warning",
            message="High trade volume with low win rate may indicate overtrading.",
            data={
                "total_trades": overall.total_trades,
                "win_rate": overall.win_rate,
                "threshold": 10,
            },
        )

    def abs_impact(insight: StatsInsightItemRead) -> float:
        if not insight.data:
            return 0.0
        impact_value = insight.data.get("impact_usd")
        if isinstance(impact_value, int | float):
            return abs(float(impact_value))
        for key in (
            "broken_total_pnl_usd",
            "followed_total_pnl_usd",
            "total_pnl_usd",
            "expectancy_usd_per_trade",
        ):
            value = insight.data.get(key)
            if isinstance(value, int | float):
                return abs(float(value))
        return 0.0

    insights.sort(
        key=lambda insight: (
            -insight.priority_score,
            -abs_impact(insight),
        )
    )
    return insights[:5]


@router.get("/summary", response_model=StatsSummaryRead)
def get_stats_summary(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> StatsSummaryRead:
    # Default behavior is all-time when start/end are omitted.
    _validate_date_range(start, end)

    stmt = _build_filtered_trades_query(start, end)
    trades = list(db.scalars(stmt).all())
    total_trades = len(trades)

    total_pnl_usd = round(sum(_trade_total_pnl_usd(trade) for trade in trades), 2)
    wins_overall = sum(1 for trade in trades if _trade_total_pnl_usd(trade) > 0)
    win_rate_overall = round((wins_overall / total_trades) * 100, 2) if total_trades else 0.0

    by_setup_accumulator: dict[tuple[int, str], dict[str, float | int]] = {}
    for trade in trades:
        setup_id = trade.setup_id
        setup_name = trade.setup_name or "UNKNOWN"
        key = (setup_id, setup_name)
        if key not in by_setup_accumulator:
            by_setup_accumulator[key] = {"count": 0, "wins": 0, "total_pnl_usd": 0.0}

        setup_total = _trade_total_pnl_usd(trade)
        by_setup_accumulator[key]["count"] += 1
        by_setup_accumulator[key]["total_pnl_usd"] += setup_total
        if setup_total > 0:
            by_setup_accumulator[key]["wins"] += 1

    by_setup: list[SetupStatsRow] = []
    sorted_by_setup = sorted(by_setup_accumulator.items(), key=lambda item: item[0][1])
    for (setup_id, setup_name), values in sorted_by_setup:
        count = int(values["count"])
        wins = int(values["wins"])
        setup_win_rate = round((wins / count) * 100, 2) if count else 0.0
        by_setup.append(
            SetupStatsRow(
                setup_id=setup_id,
                setup_name=setup_name,
                count=count,
                total_pnl_usd=round(float(values["total_pnl_usd"]), 2),
                win_rate=setup_win_rate,
            )
        )

    return StatsSummaryRead(
        total_trades=total_trades,
        total_pnl_usd=total_pnl_usd,
        win_rate_overall=win_rate_overall,
        by_setup=by_setup,
    )


@router.get("/equity", response_model=EquityCurveRead)
def get_equity_curve(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> EquityCurveRead:
    # Default behavior is all-time when start/end are omitted.
    # Gap days with no trades are omitted in this MVP response.
    _validate_date_range(start, end)

    stmt = _build_filtered_trades_query(start, end)
    trades = list(db.scalars(stmt).all())

    daily_totals = _build_daily_totals(trades)

    points: list[EquityPointRead] = []
    cumulative = 0.0
    for trade_date in sorted(daily_totals):
        daily_total = round(daily_totals[trade_date], 2)
        cumulative = round(cumulative + daily_total, 2)
        points.append(
            EquityPointRead(
                date=trade_date.isoformat(),
                daily_pnl_usd=daily_total,
                cumulative_pnl_usd=cumulative,
            )
        )

    return EquityCurveRead(points=points)


@router.get("/pnl-series", response_model=PnlSeriesRead)
def get_pnl_series(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    group_by: Literal["daily", "weekly"] = Query(default="daily"),
    db: Session = Depends(get_db),
) -> PnlSeriesRead:
    # Default behavior is all-time when start/end are omitted.
    # Weekly grouping uses ISO weeks (Monday-Sunday) keyed from trade.date.
    _validate_date_range(start, end)

    trades = list(db.scalars(_build_filtered_trades_query(start, end)).all())
    range_read = _resolve_all_time_output_range(trades, start, end)

    if group_by == "daily":
        daily_buckets: dict[date, dict[str, int | float]] = {}
        for trade in trades:
            bucket = daily_buckets.setdefault(
                trade.date,
                {"trade_count": 0, "total_pnl_usd": 0.0},
            )
            bucket["trade_count"] += 1
            bucket["total_pnl_usd"] += _trade_total_pnl_usd(trade)

        series = [
            PnlSeriesPointRead(
                label=trade_date.isoformat(),
                start_date=trade_date.isoformat(),
                end_date=trade_date.isoformat(),
                trade_count=int(values["trade_count"]),
                total_pnl_usd=round(float(values["total_pnl_usd"]), 2),
            )
            for trade_date, values in sorted(daily_buckets.items())
        ]
    else:
        weekly_buckets: dict[tuple[int, int], dict[str, int | float | date]] = {}
        for trade in trades:
            iso_year, iso_week, _ = trade.date.isocalendar()
            week_start = date.fromisocalendar(iso_year, iso_week, 1)
            week_end = date.fromisocalendar(iso_year, iso_week, 7)
            bucket = weekly_buckets.setdefault(
                (iso_year, iso_week),
                {
                    "start_date": week_start,
                    "end_date": week_end,
                    "trade_count": 0,
                    "total_pnl_usd": 0.0,
                },
            )
            bucket["trade_count"] += 1
            bucket["total_pnl_usd"] += _trade_total_pnl_usd(trade)

        series = [
            PnlSeriesPointRead(
                label=f"{iso_year}-W{iso_week:02d}",
                start_date=values["start_date"].isoformat(),
                end_date=values["end_date"].isoformat(),
                trade_count=int(values["trade_count"]),
                total_pnl_usd=round(float(values["total_pnl_usd"]), 2),
            )
            for (iso_year, iso_week), values in sorted(weekly_buckets.items())
        ]

    return PnlSeriesRead(
        range=range_read,
        group_by=group_by,
        series=series,
    )


@router.get("/time-of-day", response_model=TimeOfDayRead)
def get_time_of_day_stats(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    bucket: Literal["hour"] = Query(default="hour"),
    db: Session = Depends(get_db),
) -> TimeOfDayRead:
    resolved_start, resolved_end = _resolve_time_of_day_date_range(start, end)
    trades = list(db.scalars(_build_filtered_trades_query(resolved_start, resolved_end)).all())

    excluded_missing_time = 0
    bucket_pnls: dict[int, list[float]] = {}
    bucket_minutes = 60

    for trade in trades:
        if trade.entry_time is None:
            excluded_missing_time += 1
            continue

        entry_minutes = (trade.entry_time.hour * 60) + trade.entry_time.minute
        bucket_start = (entry_minutes // bucket_minutes) * bucket_minutes
        if bucket_start not in bucket_pnls:
            bucket_pnls[bucket_start] = []
        bucket_pnls[bucket_start].append(_trade_total_pnl_usd(trade))

    bucket_rows: list[TimeOfDayBucketRead] = []
    for bucket_start in sorted(bucket_pnls):
        pnl_values = bucket_pnls[bucket_start]
        count = len(pnl_values)
        total_pnl_usd = sum(pnl_values)
        avg_pnl_usd = total_pnl_usd / count if count else 0.0
        win_rate, _, _, _ = _compute_win_loss_metrics(pnl_values)
        label = f"{bucket_start // 60:02d}:00"
        bucket_rows.append(
            TimeOfDayBucketRead(
                label=label,
                start_minute=bucket_start,
                end_minute=bucket_start + bucket_minutes,
                count=count,
                total_pnl_usd=round(total_pnl_usd, 2),
                win_rate=round(win_rate, 4),
                avg_pnl_usd=round(avg_pnl_usd, 2),
            )
        )

    return TimeOfDayRead(
        range=StatsRangeRead(
            start=resolved_start.isoformat(),
            end=resolved_end.isoformat(),
        ),
        bucket=bucket,
        excluded_missing_time=excluded_missing_time,
        buckets=bucket_rows,
    )


@router.get("/hold-time", response_model=HoldTimeRead)
def get_hold_time_stats(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> HoldTimeRead:
    resolved_start, resolved_end = _resolve_hold_time_date_range(start, end)
    trades = list(db.scalars(_build_filtered_trades_query(resolved_start, resolved_end)).all())

    excluded_missing_duration = 0
    bucket_pnls: dict[int, list[float]] = {index: [] for index in range(len(HOLD_TIME_BUCKETS))}

    for trade in trades:
        if trade.duration_seconds is None:
            excluded_missing_duration += 1
            continue

        for index, (_, min_seconds, max_seconds) in enumerate(HOLD_TIME_BUCKETS):
            if max_seconds is None and trade.duration_seconds >= min_seconds:
                bucket_pnls[index].append(_trade_total_pnl_usd(trade))
                break
            if max_seconds is not None and min_seconds <= trade.duration_seconds < max_seconds:
                bucket_pnls[index].append(_trade_total_pnl_usd(trade))
                break

    bucket_rows: list[HoldTimeBucketRead] = []
    for index, (label, min_seconds, max_seconds) in enumerate(HOLD_TIME_BUCKETS):
        pnl_values = bucket_pnls[index]
        count = len(pnl_values)
        total_pnl_usd = sum(pnl_values)
        avg_pnl_usd = total_pnl_usd / count if count else 0.0
        win_rate, _, _, _ = _compute_win_loss_metrics(pnl_values)
        bucket_rows.append(
            HoldTimeBucketRead(
                label=label,
                min_seconds=min_seconds,
                max_seconds=max_seconds,
                count=count,
                total_pnl_usd=round(total_pnl_usd, 2),
                win_rate=round(win_rate, 4),
                avg_pnl_usd=round(avg_pnl_usd, 2),
            )
        )

    return HoldTimeRead(
        range=StatsRangeRead(
            start=resolved_start.isoformat(),
            end=resolved_end.isoformat(),
        ),
        excluded_missing_duration=excluded_missing_duration,
        buckets=bucket_rows,
    )


@router.get("/insights", response_model=StatsInsightsRead)
def get_stats_insights(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> StatsInsightsRead:
    resolved_start, resolved_end = _resolve_insights_date_range(start, end)
    trades = list(db.scalars(_build_filtered_trades_query(resolved_start, resolved_end)).all())

    pnl_values = [_trade_total_pnl_usd(trade) for trade in trades]
    total_trades = len(trades)
    total_pnl_usd = sum(pnl_values)
    win_rate, avg_win_usd, avg_loss_usd, expectancy = _compute_win_loss_metrics(pnl_values)
    daily_totals = _build_daily_totals(trades)
    risk = _compute_drawdown_from_daily_totals(daily_totals)
    streaks = _compute_streaks(trades)

    followed_trades = [trade for trade in trades if trade.rule_followed]
    broken_trades = [trade for trade in trades if not trade.rule_followed]

    by_emotion_accumulator: dict[tuple[int, str], list[float]] = {}
    for trade in trades:
        key = (trade.emotion_id, trade.emotion_name or "UNKNOWN")
        if key not in by_emotion_accumulator:
            by_emotion_accumulator[key] = []
        by_emotion_accumulator[key].append(_trade_total_pnl_usd(trade))

    by_emotion_rows: list[EmotionInsightsRowRead] = []
    for (emotion_id, emotion_name), values in by_emotion_accumulator.items():
        emotion_total = sum(values)
        emotion_count = len(values)
        emotion_avg = emotion_total / emotion_count if emotion_count else 0.0
        emotion_win_rate, _, _, _ = _compute_win_loss_metrics(values)
        by_emotion_rows.append(
            EmotionInsightsRowRead(
                emotion_id=emotion_id,
                emotion_name=emotion_name,
                count=emotion_count,
                total_pnl_usd=round(emotion_total, 2),
                win_rate=round(emotion_win_rate, 4),
                avg_pnl_usd=round(emotion_avg, 2),
            )
        )
    by_emotion_rows.sort(
        key=lambda row: (
            -row.count,
            -abs(row.total_pnl_usd),
            row.emotion_name,
        )
    )

    by_setup_accumulator: dict[tuple[int, str], list[float]] = {}
    for trade in trades:
        key = (trade.setup_id, trade.setup_name or "UNKNOWN")
        if key not in by_setup_accumulator:
            by_setup_accumulator[key] = []
        by_setup_accumulator[key].append(_trade_total_pnl_usd(trade))

    by_setup_rows: list[SetupInsightsRowRead] = []
    for (setup_id, setup_name), values in by_setup_accumulator.items():
        setup_total = sum(values)
        setup_count = len(values)
        setup_win_rate, setup_avg_win, setup_avg_loss, setup_expectancy = _compute_win_loss_metrics(
            values
        )
        by_setup_rows.append(
            SetupInsightsRowRead(
                setup_id=setup_id,
                setup_name=setup_name,
                count=setup_count,
                total_pnl_usd=round(setup_total, 2),
                win_rate=round(setup_win_rate, 4),
                avg_win_usd=round(setup_avg_win, 2),
                avg_loss_usd=round(setup_avg_loss, 2),
                expectancy=round(setup_expectancy, 2),
            )
        )
    by_setup_rows.sort(
        key=lambda row: (
            -row.count,
            -abs(row.total_pnl_usd),
            row.setup_name,
        )
    )

    overall_stats = StatsOverallRead(
        total_trades=total_trades,
        total_pnl_usd=round(total_pnl_usd, 2),
        win_rate=round(win_rate, 4),
        avg_win_usd=round(avg_win_usd, 2),
        avg_loss_usd=round(avg_loss_usd, 2),
        expectancy_usd_per_trade=round(expectancy, 2),
    )
    by_rule_followed_data = ByRuleFollowedRead(
        followed=_build_rule_followed_bucket(followed_trades),
        broken=_build_rule_followed_bucket(broken_trades),
    )
    insights = _generate_insights(
        overall=overall_stats,
        by_rule_followed=by_rule_followed_data,
        by_emotion_rows=by_emotion_rows,
    )
    patterns = _generate_patterns(trades)

    return StatsInsightsRead(
        range=StatsRangeRead(
            start=resolved_start.isoformat(),
            end=resolved_end.isoformat(),
        ),
        definitions=StatsDefinitionsRead(
            win_rule="Win = total_pnl_usd > 0",
            breakeven_handling=(
                "Breakeven trades (total_pnl_usd == 0) are excluded from "
                "win rate and expectancy calculations."
            ),
        ),
        overall=overall_stats,
        risk=risk,
        streaks=streaks,
        by_rule_followed=by_rule_followed_data,
        by_emotion=by_emotion_rows,
        by_setup_optional=by_setup_rows,
        insights=insights,
        patterns=patterns,
    )
