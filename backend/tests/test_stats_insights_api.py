from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.emotion_option import EmotionOption
from app.models.setup_option import SetupOption


def _seed_setups(testing_session_local: sessionmaker[Session]) -> dict[str, int]:
    with testing_session_local() as session:
        session.add_all(
            [
                SetupOption(name="HOD_BREAK", is_active=True, sort_order=1),
                SetupOption(name="CHOP", is_active=True, sort_order=2),
            ]
        )
        session.commit()
        setups = session.query(SetupOption).all()
        return {setup.name: setup.id for setup in setups}


def _seed_emotions(testing_session_local: sessionmaker[Session]) -> dict[str, int]:
    with testing_session_local() as session:
        session.add_all(
            [
                EmotionOption(name="CALM", is_active=True, sort_order=1),
                EmotionOption(name="FOMO", is_active=True, sort_order=2),
                EmotionOption(name="REVENGE", is_active=True, sort_order=3),
            ]
        )
        session.commit()
        emotions = session.query(EmotionOption).all()
        return {emotion.name: emotion.id for emotion in emotions}


def _build_client(
    tmp_path: Path, db_name: str
) -> tuple[TestClient, dict[str, int], dict[str, int]]:
    db_path = tmp_path / db_name
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, class_=Session
    )
    Base.metadata.create_all(bind=engine)
    setup_ids = _seed_setups(testing_session_local)
    emotion_ids = _seed_emotions(testing_session_local)

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), setup_ids, emotion_ids


def _seed_insight_trades(
    client: TestClient, setup_ids: dict[str, int], emotion_ids: dict[str, int]
) -> None:
    payloads = [
        {
            "date": "2026-02-20",
            "ticker": "SPY",
            "direction": "CALL",
            "entry_price": 1.0,
            "exit_price": 2.0,
            "quantity": 1,
            "setup_id": setup_ids["HOD_BREAK"],
            "emotion_id": emotion_ids["CALM"],
            "rule_followed": True,
            "notes": "win followed calm",
        },  # +100
        {
            "date": "2026-02-20",
            "ticker": "QQQ",
            "direction": "CALL",
            "entry_price": 2.0,
            "exit_price": 1.5,
            "quantity": 1,
            "setup_id": setup_ids["HOD_BREAK"],
            "emotion_id": emotion_ids["FOMO"],
            "rule_followed": True,
            "notes": "loss followed fomo",
        },  # -50
        {
            "date": "2026-02-21",
            "ticker": "IWM",
            "direction": "PUT",
            "entry_price": 1.0,
            "exit_price": 0.8,
            "quantity": 1,
            "setup_id": setup_ids["CHOP"],
            "emotion_id": emotion_ids["FOMO"],
            "rule_followed": False,
            "notes": "loss broken fomo",
        },  # -20
        {
            "date": "2026-02-21",
            "ticker": "DIA",
            "direction": "PUT",
            "entry_price": 1.0,
            "exit_price": 1.0,
            "quantity": 1,
            "setup_id": setup_ids["CHOP"],
            "emotion_id": emotion_ids["REVENGE"],
            "rule_followed": False,
            "notes": "breakeven broken revenge",
        },  # 0
        {
            "date": "2026-02-22",
            "ticker": "NVDA",
            "direction": "CALL",
            "entry_price": 1.0,
            "exit_price": 1.3,
            "quantity": 1,
            "setup_id": setup_ids["CHOP"],
            "emotion_id": emotion_ids["CALM"],
            "rule_followed": True,
            "notes": "win followed calm",
        },  # +30
    ]

    for payload in payloads:
        response = client.post("/api/trades", json=payload)
        assert response.status_code == 201


def test_stats_insights_returns_behavior_analytics(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_stats_insights.db")
    try:
        with client:
            _seed_insight_trades(client, setup_ids, emotion_ids)

            response = client.get(
                "/api/stats/insights",
                params={"start": "2026-02-20", "end": "2026-02-22"},
            )
            assert response.status_code == 200
            body = response.json()

            assert body["range"] == {"start": "2026-02-20", "end": "2026-02-22"}
            assert body["definitions"]["win_rule"] == "Win = total_pnl_usd > 0"
            assert (
                "excluded from win rate and expectancy" in body["definitions"]["breakeven_handling"]
            )

            overall = body["overall"]
            assert overall["total_trades"] == 5
            assert overall["total_pnl_usd"] == 60.0
            assert overall["win_rate"] == 0.5
            assert overall["avg_win_usd"] == 65.0
            assert overall["avg_loss_usd"] == -35.0
            assert overall["expectancy_usd_per_trade"] == 15.0

            assert body["risk"] == {
                "max_drawdown_usd": 20.0,
                "max_drawdown_start": "2026-02-20",
                "max_drawdown_end": "2026-02-21",
            }
            assert body["streaks"] == {
                "max_win_streak": 1,
                "max_loss_streak": 2,
                "current_streak_type": "win",
                "current_streak_length": 1,
            }
            assert len(body["insights"]) >= 1
            assert any(insight["type"] == "rule_adherence" for insight in body["insights"])
            assert any(insight["type"] == "emotion" for insight in body["insights"])
            assert any(insight["type"] == "expectancy" for insight in body["insights"])
            assert body["patterns"] == []

            by_rule = body["by_rule_followed"]
            assert by_rule["followed"]["count"] == 3
            assert by_rule["followed"]["total_pnl_usd"] == 80.0
            assert by_rule["followed"]["win_rate"] == 0.6667
            assert by_rule["followed"]["avg_pnl_usd"] == 26.67

            assert by_rule["broken"]["count"] == 2
            assert by_rule["broken"]["total_pnl_usd"] == -20.0
            assert by_rule["broken"]["win_rate"] == 0.0
            assert by_rule["broken"]["avg_pnl_usd"] == -10.0

            by_emotion = {row["emotion_name"]: row for row in body["by_emotion"]}
            assert by_emotion["CALM"]["count"] == 2
            assert by_emotion["CALM"]["total_pnl_usd"] == 130.0
            assert by_emotion["CALM"]["win_rate"] == 1.0
            assert by_emotion["CALM"]["avg_pnl_usd"] == 65.0

            assert by_emotion["FOMO"]["count"] == 2
            assert by_emotion["FOMO"]["total_pnl_usd"] == -70.0
            assert by_emotion["FOMO"]["win_rate"] == 0.0
            assert by_emotion["FOMO"]["avg_pnl_usd"] == -35.0

            assert by_emotion["REVENGE"]["count"] == 1
            assert by_emotion["REVENGE"]["total_pnl_usd"] == 0.0
            assert by_emotion["REVENGE"]["win_rate"] == 0.0
            assert by_emotion["REVENGE"]["avg_pnl_usd"] == 0.0

            by_setup = {row["setup_name"]: row for row in body["by_setup_optional"]}
            assert by_setup["HOD_BREAK"]["count"] == 2
            assert by_setup["HOD_BREAK"]["total_pnl_usd"] == 50.0
            assert by_setup["HOD_BREAK"]["win_rate"] == 0.5
            assert by_setup["HOD_BREAK"]["avg_win_usd"] == 100.0
            assert by_setup["HOD_BREAK"]["avg_loss_usd"] == -50.0
            assert by_setup["HOD_BREAK"]["expectancy"] == 25.0

            assert by_setup["CHOP"]["count"] == 3
            assert by_setup["CHOP"]["total_pnl_usd"] == 10.0
            assert by_setup["CHOP"]["win_rate"] == 0.5
            assert by_setup["CHOP"]["avg_win_usd"] == 30.0
            assert by_setup["CHOP"]["avg_loss_usd"] == -20.0
            assert by_setup["CHOP"]["expectancy"] == 5.0
    finally:
        app.dependency_overrides.clear()


def test_stats_insights_respects_date_filter(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_stats_insights_date_filter.db")
    try:
        with client:
            _seed_insight_trades(client, setup_ids, emotion_ids)

            response = client.get(
                "/api/stats/insights",
                params={"start": "2026-02-22", "end": "2026-02-22"},
            )
            assert response.status_code == 200
            body = response.json()

            overall = body["overall"]
            assert overall["total_trades"] == 1
            assert overall["total_pnl_usd"] == 30.0
            assert overall["win_rate"] == 1.0
            assert overall["avg_win_usd"] == 30.0
            assert overall["avg_loss_usd"] == 0.0
            assert overall["expectancy_usd_per_trade"] == 30.0
            assert body["risk"] == {
                "max_drawdown_usd": 0.0,
                "max_drawdown_start": None,
                "max_drawdown_end": None,
            }
            assert body["streaks"] == {
                "max_win_streak": 1,
                "max_loss_streak": 0,
                "current_streak_type": "win",
                "current_streak_length": 1,
            }

            assert body["by_rule_followed"]["followed"]["count"] == 1
            assert body["by_rule_followed"]["broken"]["count"] == 0
            assert len(body["by_emotion"]) == 1
            assert body["by_emotion"][0]["emotion_name"] == "CALM"
    finally:
        app.dependency_overrides.clear()


def test_stats_insights_defaults_to_last_30_days(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_stats_insights_default_range.db")
    try:
        with client:
            today = date.today()
            old_date = (today - timedelta(days=40)).isoformat()
            recent_date = (today - timedelta(days=5)).isoformat()

            for payload in [
                {
                    "date": old_date,
                    "ticker": "OLD",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 1.5,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                    "notes": "outside default range",
                },
                {
                    "date": recent_date,
                    "ticker": "NEW",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 1.2,
                    "quantity": 1,
                    "setup_id": setup_ids["CHOP"],
                    "emotion_id": emotion_ids["FOMO"],
                    "rule_followed": True,
                    "notes": "inside default range",
                },
            ]:
                response = client.post("/api/trades", json=payload)
                assert response.status_code == 201

            response = client.get("/api/stats/insights")
            assert response.status_code == 200
            body = response.json()

            assert body["range"] == {
                "start": (today - timedelta(days=29)).isoformat(),
                "end": today.isoformat(),
            }
            assert body["overall"]["total_trades"] == 1
            assert body["overall"]["total_pnl_usd"] == 20.0
    finally:
        app.dependency_overrides.clear()


def test_stats_insights_streak_logic_with_breakeven_breaks(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_stats_insights_streaks.db")
    try:
        with client:
            payloads = [
                {
                    "date": "2026-02-20",
                    "ticker": "A1",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 1.1,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                    "notes": "+10",
                },
                {
                    "date": "2026-02-20",
                    "ticker": "A2",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 1.2,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                    "notes": "+20",
                },
                {
                    "date": "2026-02-20",
                    "ticker": "A3",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 0.95,
                    "quantity": 1,
                    "setup_id": setup_ids["CHOP"],
                    "emotion_id": emotion_ids["FOMO"],
                    "rule_followed": False,
                    "notes": "-5",
                },
                {
                    "date": "2026-02-20",
                    "ticker": "A4",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 0.94,
                    "quantity": 1,
                    "setup_id": setup_ids["CHOP"],
                    "emotion_id": emotion_ids["FOMO"],
                    "rule_followed": False,
                    "notes": "-6",
                },
                {
                    "date": "2026-02-20",
                    "ticker": "A5",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 1.0,
                    "quantity": 1,
                    "setup_id": setup_ids["CHOP"],
                    "emotion_id": emotion_ids["REVENGE"],
                    "rule_followed": False,
                    "notes": "0",
                },
                {
                    "date": "2026-02-20",
                    "ticker": "A6",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 0.99,
                    "quantity": 1,
                    "setup_id": setup_ids["CHOP"],
                    "emotion_id": emotion_ids["FOMO"],
                    "rule_followed": False,
                    "notes": "-1",
                },
                {
                    "date": "2026-02-20",
                    "ticker": "A7",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 0.98,
                    "quantity": 1,
                    "setup_id": setup_ids["CHOP"],
                    "emotion_id": emotion_ids["FOMO"],
                    "rule_followed": False,
                    "notes": "-2",
                },
                {
                    "date": "2026-02-20",
                    "ticker": "A8",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 0.97,
                    "quantity": 1,
                    "setup_id": setup_ids["CHOP"],
                    "emotion_id": emotion_ids["FOMO"],
                    "rule_followed": False,
                    "notes": "-3",
                },
            ]

            for payload in payloads:
                response = client.post("/api/trades", json=payload)
                assert response.status_code == 201

            response = client.get(
                "/api/stats/insights",
                params={"start": "2026-02-20", "end": "2026-02-20"},
            )
            assert response.status_code == 200
            body = response.json()

            assert body["streaks"] == {
                "max_win_streak": 2,
                "max_loss_streak": 3,
                "current_streak_type": "loss",
                "current_streak_length": 3,
            }
    finally:
        app.dependency_overrides.clear()


def test_stats_insights_drawdown_on_known_daily_series(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_stats_insights_drawdown.db")
    try:
        with client:
            payloads = [
                {
                    "date": "2026-02-20",
                    "ticker": "D1",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 2.0,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                    "notes": "+100",
                },
                {
                    "date": "2026-02-21",
                    "ticker": "D2",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 0.6,
                    "quantity": 1,
                    "setup_id": setup_ids["CHOP"],
                    "emotion_id": emotion_ids["FOMO"],
                    "rule_followed": False,
                    "notes": "-40",
                },
                {
                    "date": "2026-02-22",
                    "ticker": "D3",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 1.2,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                    "notes": "+20",
                },
                {
                    "date": "2026-02-23",
                    "ticker": "D4",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 0.1,
                    "quantity": 1,
                    "setup_id": setup_ids["CHOP"],
                    "emotion_id": emotion_ids["FOMO"],
                    "rule_followed": False,
                    "notes": "-90",
                },
                {
                    "date": "2026-02-24",
                    "ticker": "D5",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 1.1,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                    "notes": "+10",
                },
            ]

            for payload in payloads:
                response = client.post("/api/trades", json=payload)
                assert response.status_code == 201

            response = client.get(
                "/api/stats/insights",
                params={"start": "2026-02-20", "end": "2026-02-24"},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["risk"] == {
                "max_drawdown_usd": 110.0,
                "max_drawdown_start": "2026-02-20",
                "max_drawdown_end": "2026-02-23",
            }
    finally:
        app.dependency_overrides.clear()


def test_stats_insights_returns_no_insights_for_empty_range(tmp_path: Path) -> None:
    client, _, _ = _build_client(tmp_path, "test_stats_insights_empty_range.db")
    try:
        with client:
            response = client.get(
                "/api/stats/insights",
                params={"start": "2026-02-20", "end": "2026-02-20"},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["overall"]["total_trades"] == 0
            assert body["insights"] == []
            assert body["patterns"] == []
    finally:
        app.dependency_overrides.clear()


def test_stats_insights_pattern_after_two_losses_next_trade(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(
        tmp_path, "test_stats_patterns_after_two_losses.db"
    )
    try:
        with client:
            for index in range(7):
                response = client.post(
                    "/api/trades",
                    json={
                        "date": "2026-02-20",
                        "ticker": f"LOS{index}",
                        "direction": "CALL",
                        "entry_price": 2.0,
                        "exit_price": 1.5,
                        "quantity": 1,
                        "setup_id": setup_ids["CHOP"],
                        "emotion_id": emotion_ids["FOMO"],
                        "rule_followed": False,
                        "notes": "pattern test",
                    },
                )
                assert response.status_code == 201

            response = client.get(
                "/api/stats/insights",
                params={"start": "2026-02-20", "end": "2026-02-20"},
            )
            assert response.status_code == 200
            body = response.json()

            pattern = next(
                item for item in body["patterns"] if item["id"] == "after_2_losses_next_trade"
            )
            assert pattern["severity"] == "warning"
            assert (
                pattern["message"]
                == "After 2 consecutive losses, your next trade averages **-$50** "
                "(win rate **0%**, n=5)."
            )
            assert pattern["sample_size"] == 5
            assert pattern["data"] == {
                "count": 5,
                "total_pnl_usd": -250.0,
                "win_rate": 0.0,
                "avg_pnl_usd": -50.0,
                "impact_usd": -50.0,
            }
            assert pattern["filters"] == {"pattern": "after_2_losses_next_trade"}
    finally:
        app.dependency_overrides.clear()


def test_stats_insights_pattern_trade_index_after_three(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_stats_patterns_trade_index.db")
    try:
        with client:
            for day in ("2026-02-20", "2026-02-21"):
                for trade_index in range(1, 7):
                    is_first_three = trade_index <= 3
                    response = client.post(
                        "/api/trades",
                        json={
                            "date": day,
                            "ticker": f"T{day[-2:]}{trade_index}",
                            "direction": "CALL",
                            "entry_price": 1.0 if is_first_three else 2.0,
                            "exit_price": 2.0 if is_first_three else 1.5,
                            "quantity": 1,
                            "setup_id": setup_ids["HOD_BREAK"]
                            if is_first_three
                            else setup_ids["CHOP"],
                            "emotion_id": emotion_ids["CALM"]
                            if is_first_three
                            else emotion_ids["FOMO"],
                            "rule_followed": is_first_three,
                            "notes": "pattern test",
                        },
                    )
                    assert response.status_code == 201

            response = client.get(
                "/api/stats/insights",
                params={"start": "2026-02-20", "end": "2026-02-21"},
            )
            assert response.status_code == 200
            body = response.json()

            pattern = next(item for item in body["patterns"] if item["id"] == "trade_index_after_3")
            assert pattern["severity"] == "warning"
            assert (
                pattern["message"]
                == "Your first 3 trades average **+$100**. Trades 4+ average **-$50** (n=6)."
            )
            assert pattern["sample_size"] == 6
            assert pattern["filters"] == {"pattern": "trade_index_after_3"}
            assert pattern["data"]["first_3_count"] == 6
            assert pattern["data"]["after_3_count"] == 6
            assert pattern["data"]["first_3_avg_pnl_usd"] == 100.0
            assert pattern["data"]["after_3_avg_pnl_usd"] == -50.0
            assert pattern["data"]["avg_delta_usd"] == 150.0
    finally:
        app.dependency_overrides.clear()


def test_stats_insights_pattern_worst_time_of_day_bucket(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_stats_patterns_worst_time.db")
    try:
        with client:
            for day_offset in range(5):
                day = f"2026-02-{20 + day_offset:02d}"
                loss_response = client.post(
                    "/api/trades",
                    json={
                        "date": day,
                        "ticker": f"WTL{day_offset}",
                        "direction": "CALL",
                        "entry_price": 2.0,
                        "exit_price": 1.8,
                        "quantity": 1,
                        "setup_id": setup_ids["CHOP"],
                        "emotion_id": emotion_ids["FOMO"],
                        "rule_followed": False,
                        "entry_time": "09:10:00",
                        "notes": "pattern test",
                    },
                )
                assert loss_response.status_code == 201

                win_response = client.post(
                    "/api/trades",
                    json={
                        "date": day,
                        "ticker": f"WTW{day_offset}",
                        "direction": "CALL",
                        "entry_price": 1.0,
                        "exit_price": 1.3,
                        "quantity": 1,
                        "setup_id": setup_ids["HOD_BREAK"],
                        "emotion_id": emotion_ids["CALM"],
                        "rule_followed": True,
                        "entry_time": "10:10:00",
                        "notes": "pattern test",
                    },
                )
                assert win_response.status_code == 201

            response = client.get(
                "/api/stats/insights",
                params={"start": "2026-02-20", "end": "2026-02-24"},
            )
            assert response.status_code == 200
            body = response.json()

            pattern = next(
                item for item in body["patterns"] if item["id"] == "worst_time_of_day_bucket"
            )
            assert pattern["severity"] == "warning"
            assert (
                pattern["message"] == "Your worst time window is **09:00-09:59**: **-$20** avg PnL "
                "(win rate **0%**, n=5)."
            )
            assert pattern["sample_size"] == 5
            assert pattern["filters"] == {
                "entry_time_start_minute": 540,
                "entry_time_end_minute": 600,
            }
            assert pattern["data"]["count"] == 5
            assert pattern["data"]["avg_pnl_usd"] == -20.0
            assert pattern["data"]["win_rate"] == 0.0
    finally:
        app.dependency_overrides.clear()


def test_stats_insights_pattern_worst_hold_time_bucket(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(
        tmp_path, "test_stats_patterns_worst_hold_time.db"
    )
    try:
        with client:
            for day_offset in range(5):
                day = f"2026-02-{20 + day_offset:02d}"
                loss_response = client.post(
                    "/api/trades",
                    json={
                        "date": day,
                        "ticker": f"WHL{day_offset}",
                        "direction": "CALL",
                        "entry_price": 2.0,
                        "exit_price": 1.7,
                        "quantity": 1,
                        "setup_id": setup_ids["CHOP"],
                        "emotion_id": emotion_ids["FOMO"],
                        "rule_followed": False,
                        "duration_seconds": 180,
                        "notes": "pattern test",
                    },
                )
                assert loss_response.status_code == 201

                win_response = client.post(
                    "/api/trades",
                    json={
                        "date": day,
                        "ticker": f"WHW{day_offset}",
                        "direction": "CALL",
                        "entry_price": 1.0,
                        "exit_price": 1.4,
                        "quantity": 1,
                        "setup_id": setup_ids["HOD_BREAK"],
                        "emotion_id": emotion_ids["CALM"],
                        "rule_followed": True,
                        "duration_seconds": 700,
                        "notes": "pattern test",
                    },
                )
                assert win_response.status_code == 201

            response = client.get(
                "/api/stats/insights",
                params={"start": "2026-02-20", "end": "2026-02-24"},
            )
            assert response.status_code == 200
            body = response.json()

            pattern = next(
                item for item in body["patterns"] if item["id"] == "worst_hold_time_bucket"
            )
            assert pattern["severity"] == "warning"
            assert (
                pattern["message"]
                == "Trades held **2-5m** average **-$30** (win rate **0%**, n=5)."
            )
            assert pattern["sample_size"] == 5
            assert pattern["filters"] == {
                "hold_time_min_seconds": 120,
                "hold_time_max_seconds": 300,
            }
            assert pattern["data"]["count"] == 5
            assert pattern["data"]["avg_pnl_usd"] == -30.0
            assert pattern["data"]["win_rate"] == 0.0
    finally:
        app.dependency_overrides.clear()
