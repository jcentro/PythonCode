from app.routers.stats import _generate_insights
from app.schemas.stats import (
    ByRuleFollowedRead,
    EmotionInsightsRowRead,
    RuleFollowedBucketRead,
    StatsOverallRead,
)


def _bucket(
    count: int, total_pnl_usd: float, win_rate: float, avg_pnl_usd: float
) -> RuleFollowedBucketRead:
    return RuleFollowedBucketRead(
        count=count,
        total_pnl_usd=total_pnl_usd,
        win_rate=win_rate,
        avg_pnl_usd=avg_pnl_usd,
    )


def _overall(total_trades: int, win_rate: float, expectancy: float) -> StatsOverallRead:
    return StatsOverallRead(
        total_trades=total_trades,
        total_pnl_usd=0.0,
        win_rate=win_rate,
        avg_win_usd=0.0,
        avg_loss_usd=0.0,
        expectancy_usd_per_trade=expectancy,
    )


def test_generate_insights_returns_empty_for_no_trades() -> None:
    insights = _generate_insights(
        overall=_overall(total_trades=0, win_rate=0.0, expectancy=0.0),
        by_rule_followed=ByRuleFollowedRead(
            followed=_bucket(0, 0.0, 0.0, 0.0),
            broken=_bucket(0, 0.0, 0.0, 0.0),
        ),
        by_emotion_rows=[],
    )

    assert insights == []


def test_generate_insights_rule_adherence_triggers() -> None:
    insights = _generate_insights(
        overall=_overall(total_trades=4, win_rate=0.5, expectancy=0.0),
        by_rule_followed=ByRuleFollowedRead(
            followed=_bucket(2, 120.0, 1.0, 60.0),
            broken=_bucket(2, -80.0, 0.0, -40.0),
        ),
        by_emotion_rows=[],
    )

    rule_insights = [insight for insight in insights if insight.type == "rule_adherence"]
    assert len(rule_insights) == 1
    assert rule_insights[0].severity == "positive"
    assert (
        rule_insights[0].message
        == "Your disciplined trades are up **$120**. Rule-breaking trades are down **$80**."
    )


def test_generate_insights_emotion_triggers() -> None:
    insights = _generate_insights(
        overall=_overall(total_trades=5, win_rate=0.4, expectancy=0.0),
        by_rule_followed=ByRuleFollowedRead(
            followed=_bucket(0, 0.0, 0.0, 0.0),
            broken=_bucket(0, 0.0, 0.0, 0.0),
        ),
        by_emotion_rows=[
            EmotionInsightsRowRead(
                emotion_id=1,
                emotion_name="FOMO",
                count=3,
                total_pnl_usd=-150.0,
                win_rate=0.0,
                avg_pnl_usd=-50.0,
            ),
            EmotionInsightsRowRead(
                emotion_id=2,
                emotion_name="CALM",
                count=2,
                total_pnl_usd=90.0,
                win_rate=1.0,
                avg_pnl_usd=45.0,
            ),
        ],
    )

    assert any(
        insight.type == "emotion"
        and insight.severity == "warning"
        and insight.message == "FOMO trades are down **$150** with a **0%** win rate."
        for insight in insights
    )
    assert any(
        insight.type == "emotion"
        and insight.severity == "positive"
        and insight.message == "You perform best when CALM: up **$90**, **100%** win rate."
        for insight in insights
    )


def test_generate_insights_expectancy_and_overtrading_triggers() -> None:
    insights = _generate_insights(
        overall=_overall(total_trades=11, win_rate=0.45, expectancy=-12.5),
        by_rule_followed=ByRuleFollowedRead(
            followed=_bucket(0, 0.0, 0.0, 0.0),
            broken=_bucket(0, 0.0, 0.0, 0.0),
        ),
        by_emotion_rows=[],
    )

    assert any(
        insight.type == "expectancy"
        and insight.severity == "warning"
        and insight.message == "Your edge is currently negative: **-$13** per trade."
        for insight in insights
    )
    assert any(
        insight.type == "behavior"
        and insight.severity == "warning"
        and insight.message == "High trade volume with low win rate may indicate overtrading."
        for insight in insights
    )


def test_generate_insights_positive_expectancy_trigger() -> None:
    insights = _generate_insights(
        overall=_overall(total_trades=3, win_rate=0.67, expectancy=8.0),
        by_rule_followed=ByRuleFollowedRead(
            followed=_bucket(0, 0.0, 0.0, 0.0),
            broken=_bucket(0, 0.0, 0.0, 0.0),
        ),
        by_emotion_rows=[],
    )

    assert any(
        insight.type == "expectancy"
        and insight.severity == "positive"
        and insight.message == "Your edge is positive: **+$8** per trade."
        for insight in insights
    )


def test_generate_insights_sorted_by_priority_then_impact_and_limited_to_top_five() -> None:
    insights = _generate_insights(
        overall=_overall(total_trades=12, win_rate=0.4, expectancy=-25.0),
        by_rule_followed=ByRuleFollowedRead(
            followed=_bucket(6, 400.0, 0.66, 66.67),
            broken=_bucket(6, -200.0, 0.2, -33.33),
        ),
        by_emotion_rows=[
            EmotionInsightsRowRead(
                emotion_id=1,
                emotion_name="REVENGE",
                count=4,
                total_pnl_usd=-300.0,
                win_rate=0.25,
                avg_pnl_usd=-75.0,
            ),
            EmotionInsightsRowRead(
                emotion_id=2,
                emotion_name="CALM",
                count=4,
                total_pnl_usd=100.0,
                win_rate=0.75,
                avg_pnl_usd=25.0,
            ),
        ],
    )

    assert len(insights) == 5
    assert [insight.priority_score for insight in insights] == [3, 3, 3, 2, 2]
    assert insights[0].type == "emotion"
    assert insights[1].type == "expectancy"
    assert insights[2].type == "behavior"
    assert insights[3].type == "rule_adherence"
    assert insights[4].type == "emotion"
