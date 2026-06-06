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
        session.add(EmotionOption(name="CALM", is_active=True, sort_order=1))
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


def test_stats_summary_aggregates_overall_and_by_setup(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_stats_summary_aggregate.db")
    try:
        with client:
            common_payload = {
                "ticker": "SPY",
                "direction": "CALL",
                "emotion_id": emotion_ids["CALM"],
                "rule_followed": True,
                "notes": "stats test",
            }

            payloads = [
                {
                    **common_payload,
                    "date": "2026-02-20",
                    "entry_price": 1.0,
                    "exit_price": 1.5,
                    "quantity": 2,
                    "setup_id": setup_ids["HOD_BREAK"],
                },  # +100
                {
                    **common_payload,
                    "date": "2026-02-21",
                    "entry_price": 1.0,
                    "exit_price": 1.0,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                },  # 0
                {
                    **common_payload,
                    "date": "2026-02-21",
                    "entry_price": 2.0,
                    "exit_price": 1.8,
                    "quantity": 1,
                    "setup_id": setup_ids["CHOP"],
                },  # -20
                {
                    **common_payload,
                    "date": "2026-02-22",
                    "entry_price": 1.0,
                    "exit_price": 1.3,
                    "quantity": 1,
                    "setup_id": setup_ids["CHOP"],
                },  # +30
            ]

            for payload in payloads:
                response = client.post("/api/trades", json=payload)
                assert response.status_code == 201

            summary_response = client.get("/api/stats/summary")
            assert summary_response.status_code == 200
            summary = summary_response.json()

            assert summary["total_trades"] == 4
            assert summary["total_pnl_usd"] == 110.0
            assert summary["win_rate_overall"] == 50.0

            by_setup = {row["setup_name"]: row for row in summary["by_setup"]}
            assert by_setup["HOD_BREAK"]["count"] == 2
            assert by_setup["HOD_BREAK"]["total_pnl_usd"] == 100.0
            assert by_setup["HOD_BREAK"]["win_rate"] == 50.0

            assert by_setup["CHOP"]["count"] == 2
            assert by_setup["CHOP"]["total_pnl_usd"] == 10.0
            assert by_setup["CHOP"]["win_rate"] == 50.0
    finally:
        app.dependency_overrides.clear()


def test_stats_summary_respects_date_filter(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_stats_summary_date_filter.db")
    try:
        with client:
            common_payload = {
                "ticker": "QQQ",
                "direction": "CALL",
                "emotion_id": emotion_ids["CALM"],
                "rule_followed": True,
                "notes": "stats filter test",
            }

            payloads = [
                {
                    **common_payload,
                    "date": "2026-02-20",
                    "entry_price": 1.0,
                    "exit_price": 1.5,
                    "quantity": 2,
                    "setup_id": setup_ids["HOD_BREAK"],
                },  # +100
                {
                    **common_payload,
                    "date": "2026-02-21",
                    "entry_price": 1.0,
                    "exit_price": 1.0,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                },  # 0
                {
                    **common_payload,
                    "date": "2026-02-21",
                    "entry_price": 2.0,
                    "exit_price": 1.8,
                    "quantity": 1,
                    "setup_id": setup_ids["CHOP"],
                },  # -20
            ]

            for payload in payloads:
                response = client.post("/api/trades", json=payload)
                assert response.status_code == 201

            filtered_response = client.get(
                "/api/stats/summary",
                params={"start": "2026-02-21", "end": "2026-02-21"},
            )
            assert filtered_response.status_code == 200
            summary = filtered_response.json()

            assert summary["total_trades"] == 2
            assert summary["total_pnl_usd"] == -20.0
            assert summary["win_rate_overall"] == 0.0

            by_setup = {row["setup_name"]: row for row in summary["by_setup"]}
            assert by_setup["HOD_BREAK"]["count"] == 1
            assert by_setup["HOD_BREAK"]["total_pnl_usd"] == 0.0
            assert by_setup["HOD_BREAK"]["win_rate"] == 0.0
            assert by_setup["CHOP"]["count"] == 1
            assert by_setup["CHOP"]["total_pnl_usd"] == -20.0
            assert by_setup["CHOP"]["win_rate"] == 0.0
    finally:
        app.dependency_overrides.clear()


def test_stats_equity_returns_daily_and_cumulative_points(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_stats_equity_points.db")
    try:
        with client:
            common_payload = {
                "ticker": "IWM",
                "direction": "CALL",
                "emotion_id": emotion_ids["CALM"],
                "rule_followed": True,
                "notes": "equity points test",
            }

            payloads = [
                {
                    **common_payload,
                    "date": "2026-02-20",
                    "entry_price": 1.0,
                    "exit_price": 1.5,
                    "quantity": 2,
                    "setup_id": setup_ids["HOD_BREAK"],
                },  # +100
                {
                    **common_payload,
                    "date": "2026-02-20",
                    "entry_price": 1.0,
                    "exit_price": 0.9,
                    "quantity": 1,
                    "setup_id": setup_ids["CHOP"],
                },  # -10
                {
                    **common_payload,
                    "date": "2026-02-22",
                    "entry_price": 1.0,
                    "exit_price": 1.2,
                    "quantity": 1,
                    "setup_id": setup_ids["CHOP"],
                },  # +20
            ]

            for payload in payloads:
                response = client.post("/api/trades", json=payload)
                assert response.status_code == 201

            equity_response = client.get("/api/stats/equity")
            assert equity_response.status_code == 200
            points = equity_response.json()["points"]

            assert points == [
                {"date": "2026-02-20", "daily_pnl_usd": 90.0, "cumulative_pnl_usd": 90.0},
                {"date": "2026-02-22", "daily_pnl_usd": 20.0, "cumulative_pnl_usd": 110.0},
            ]
    finally:
        app.dependency_overrides.clear()


def test_stats_equity_respects_date_filter(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_stats_equity_date_filter.db")
    try:
        with client:
            common_payload = {
                "ticker": "DIA",
                "direction": "CALL",
                "emotion_id": emotion_ids["CALM"],
                "rule_followed": True,
                "notes": "equity filter test",
            }

            payloads = [
                {
                    **common_payload,
                    "date": "2026-02-20",
                    "entry_price": 1.0,
                    "exit_price": 1.5,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                },  # +50
                {
                    **common_payload,
                    "date": "2026-02-21",
                    "entry_price": 1.0,
                    "exit_price": 0.9,
                    "quantity": 1,
                    "setup_id": setup_ids["CHOP"],
                },  # -10
                {
                    **common_payload,
                    "date": "2026-02-22",
                    "entry_price": 1.0,
                    "exit_price": 1.2,
                    "quantity": 1,
                    "setup_id": setup_ids["CHOP"],
                },  # +20
            ]

            for payload in payloads:
                response = client.post("/api/trades", json=payload)
                assert response.status_code == 201

            filtered_response = client.get(
                "/api/stats/equity",
                params={"start": "2026-02-21", "end": "2026-02-22"},
            )
            assert filtered_response.status_code == 200
            points = filtered_response.json()["points"]

            assert points == [
                {"date": "2026-02-21", "daily_pnl_usd": -10.0, "cumulative_pnl_usd": -10.0},
                {"date": "2026-02-22", "daily_pnl_usd": 20.0, "cumulative_pnl_usd": 10.0},
            ]
    finally:
        app.dependency_overrides.clear()


def test_stats_pnl_series_daily_groups_by_trade_date(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_stats_pnl_series_daily.db")
    try:
        with client:
            common_payload = {
                "ticker": "SPY",
                "direction": "CALL",
                "emotion_id": emotion_ids["CALM"],
                "rule_followed": True,
                "setup_id": setup_ids["HOD_BREAK"],
                "notes": "pnl series daily test",
            }

            payloads = [
                {
                    **common_payload,
                    "date": "2026-02-22",
                    "entry_price": 1.0,
                    "exit_price": 1.5,
                    "quantity": 1,
                },  # +50
                {
                    **common_payload,
                    "date": "2026-02-22",
                    "entry_price": 2.0,
                    "exit_price": 1.8,
                    "quantity": 1,
                },  # -20
                {
                    **common_payload,
                    "date": "2026-02-23",
                    "entry_price": 1.0,
                    "exit_price": 1.0,
                    "quantity": 1,
                },  # 0
                {
                    **common_payload,
                    "date": "2026-02-24",
                    "entry_price": 1.0,
                    "exit_price": 1.3,
                    "quantity": 2,
                },  # +60
            ]

            for payload in payloads:
                response = client.post("/api/trades", json=payload)
                assert response.status_code == 201

            response = client.get(
                "/api/stats/pnl-series",
                params={
                    "start": "2026-02-22",
                    "end": "2026-02-24",
                    "group_by": "daily",
                },
            )
            assert response.status_code == 200
            body = response.json()

            assert body["range"] == {"start": "2026-02-22", "end": "2026-02-24"}
            assert body["group_by"] == "daily"
            assert body["series"] == [
                {
                    "label": "2026-02-22",
                    "start_date": "2026-02-22",
                    "end_date": "2026-02-22",
                    "trade_count": 2,
                    "total_pnl_usd": 30.0,
                },
                {
                    "label": "2026-02-23",
                    "start_date": "2026-02-23",
                    "end_date": "2026-02-23",
                    "trade_count": 1,
                    "total_pnl_usd": 0.0,
                },
                {
                    "label": "2026-02-24",
                    "start_date": "2026-02-24",
                    "end_date": "2026-02-24",
                    "trade_count": 1,
                    "total_pnl_usd": 60.0,
                },
            ]

            summary_response = client.get(
                "/api/stats/summary",
                params={"start": "2026-02-22", "end": "2026-02-24"},
            )
            assert summary_response.status_code == 200
            summary = summary_response.json()
            assert (
                sum(point["total_pnl_usd"] for point in body["series"]) == summary["total_pnl_usd"]
            )
    finally:
        app.dependency_overrides.clear()


def test_stats_pnl_series_weekly_groups_by_iso_week(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_stats_pnl_series_weekly.db")
    try:
        with client:
            common_payload = {
                "ticker": "QQQ",
                "direction": "CALL",
                "emotion_id": emotion_ids["CALM"],
                "rule_followed": True,
                "setup_id": setup_ids["CHOP"],
                "notes": "pnl series weekly test",
            }

            payloads = [
                {
                    **common_payload,
                    "date": "2026-02-22",
                    "entry_price": 1.0,
                    "exit_price": 1.5,
                    "quantity": 1,
                },  # +50, 2026-W08
                {
                    **common_payload,
                    "date": "2026-02-23",
                    "entry_price": 1.0,
                    "exit_price": 0.9,
                    "quantity": 1,
                },  # -10, 2026-W09
                {
                    **common_payload,
                    "date": "2026-02-24",
                    "entry_price": 1.0,
                    "exit_price": 1.2,
                    "quantity": 1,
                },  # +20, 2026-W09
                {
                    **common_payload,
                    "date": "2026-03-01",
                    "entry_price": 1.0,
                    "exit_price": 1.1,
                    "quantity": 1,
                },  # +10, 2026-W09
                {
                    **common_payload,
                    "date": "2026-03-02",
                    "entry_price": 2.0,
                    "exit_price": 1.8,
                    "quantity": 1,
                },  # -20, 2026-W10
            ]

            for payload in payloads:
                response = client.post("/api/trades", json=payload)
                assert response.status_code == 201

            response = client.get(
                "/api/stats/pnl-series",
                params={
                    "start": "2026-02-22",
                    "end": "2026-03-02",
                    "group_by": "weekly",
                },
            )
            assert response.status_code == 200
            body = response.json()

            assert body["range"] == {"start": "2026-02-22", "end": "2026-03-02"}
            assert body["group_by"] == "weekly"
            assert body["series"] == [
                {
                    "label": "2026-W08",
                    "start_date": "2026-02-16",
                    "end_date": "2026-02-22",
                    "trade_count": 1,
                    "total_pnl_usd": 50.0,
                },
                {
                    "label": "2026-W09",
                    "start_date": "2026-02-23",
                    "end_date": "2026-03-01",
                    "trade_count": 3,
                    "total_pnl_usd": 20.0,
                },
                {
                    "label": "2026-W10",
                    "start_date": "2026-03-02",
                    "end_date": "2026-03-08",
                    "trade_count": 1,
                    "total_pnl_usd": -20.0,
                },
            ]

            summary_response = client.get(
                "/api/stats/summary",
                params={"start": "2026-02-22", "end": "2026-03-02"},
            )
            assert summary_response.status_code == 200
            summary = summary_response.json()
            assert sum(point["trade_count"] for point in body["series"]) == summary["total_trades"]
            assert (
                sum(point["total_pnl_usd"] for point in body["series"]) == summary["total_pnl_usd"]
            )
    finally:
        app.dependency_overrides.clear()


def test_stats_time_of_day_groups_hourly_and_excludes_missing_entry_time(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_stats_time_of_day_hourly.db")
    try:
        with client:
            common_payload = {
                "ticker": "SPY",
                "direction": "CALL",
                "emotion_id": emotion_ids["CALM"],
                "rule_followed": True,
                "setup_id": setup_ids["HOD_BREAK"],
                "notes": "time of day test",
                "date": "2026-02-21",
            }

            payloads = [
                {
                    **common_payload,
                    "entry_price": 1.0,
                    "exit_price": 1.5,
                    "quantity": 1,
                    "entry_time": "09:15:00",
                },  # +50, 09:00
                {
                    **common_payload,
                    "entry_price": 2.0,
                    "exit_price": 1.8,
                    "quantity": 1,
                    "entry_time": "09:45:00",
                },  # -20, 09:00
                {
                    **common_payload,
                    "entry_price": 1.0,
                    "exit_price": 1.0,
                    "quantity": 1,
                    "entry_time": "10:05:00",
                },  # 0, 10:00
                {
                    **common_payload,
                    "entry_price": 1.0,
                    "exit_price": 1.3,
                    "quantity": 1,
                },  # +30, missing entry_time -> excluded
            ]

            for payload in payloads:
                response = client.post("/api/trades", json=payload)
                assert response.status_code == 201

            response = client.get(
                "/api/stats/time-of-day",
                params={"start": "2026-02-21", "end": "2026-02-21", "bucket": "hour"},
            )
            assert response.status_code == 200
            body = response.json()

            assert body["range"] == {"start": "2026-02-21", "end": "2026-02-21"}
            assert body["bucket"] == "hour"
            assert body["excluded_missing_time"] == 1
            assert body["buckets"] == [
                {
                    "label": "09:00",
                    "start_minute": 540,
                    "end_minute": 600,
                    "count": 2,
                    "total_pnl_usd": 30.0,
                    "win_rate": 0.5,
                    "avg_pnl_usd": 15.0,
                },
                {
                    "label": "10:00",
                    "start_minute": 600,
                    "end_minute": 660,
                    "count": 1,
                    "total_pnl_usd": 0.0,
                    "win_rate": 0.0,
                    "avg_pnl_usd": 0.0,
                },
            ]
    finally:
        app.dependency_overrides.clear()


def test_stats_time_of_day_respects_date_range(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_stats_time_of_day_range.db")
    try:
        with client:
            common_payload = {
                "ticker": "QQQ",
                "direction": "CALL",
                "emotion_id": emotion_ids["CALM"],
                "rule_followed": True,
                "setup_id": setup_ids["CHOP"],
                "notes": "time filter test",
            }

            payloads = [
                {
                    **common_payload,
                    "date": "2026-02-20",
                    "entry_price": 1.0,
                    "exit_price": 1.5,
                    "quantity": 1,
                    "entry_time": "09:20:00",
                },  # +50
                {
                    **common_payload,
                    "date": "2026-02-22",
                    "entry_price": 1.5,
                    "exit_price": 1.3,
                    "quantity": 1,
                    "entry_time": "11:10:00",
                },  # -20
            ]

            for payload in payloads:
                response = client.post("/api/trades", json=payload)
                assert response.status_code == 201

            response = client.get(
                "/api/stats/time-of-day",
                params={"start": "2026-02-20", "end": "2026-02-20"},
            )
            assert response.status_code == 200
            body = response.json()

            assert body["range"] == {"start": "2026-02-20", "end": "2026-02-20"}
            assert body["excluded_missing_time"] == 0
            assert body["buckets"] == [
                {
                    "label": "09:00",
                    "start_minute": 540,
                    "end_minute": 600,
                    "count": 1,
                    "total_pnl_usd": 50.0,
                    "win_rate": 1.0,
                    "avg_pnl_usd": 50.0,
                }
            ]
    finally:
        app.dependency_overrides.clear()


def test_stats_hold_time_groups_trades_and_excludes_missing_duration(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_stats_hold_time_buckets.db")
    try:
        with client:
            common_payload = {
                "ticker": "SPY",
                "direction": "CALL",
                "emotion_id": emotion_ids["CALM"],
                "rule_followed": True,
                "setup_id": setup_ids["HOD_BREAK"],
                "notes": "hold time test",
                "date": "2026-02-21",
            }

            payloads = [
                {
                    **common_payload,
                    "entry_price": 1.0,
                    "exit_price": 1.5,
                    "quantity": 1,
                    "duration_seconds": 60,
                },  # +50, 0-2m
                {
                    **common_payload,
                    "entry_price": 2.0,
                    "exit_price": 1.8,
                    "quantity": 1,
                    "duration_seconds": 180,
                },  # -20, 2-5m
                {
                    **common_payload,
                    "entry_price": 1.0,
                    "exit_price": 1.0,
                    "quantity": 1,
                    "duration_seconds": 600,
                },  # 0, 10-20m
                {
                    **common_payload,
                    "entry_price": 1.0,
                    "exit_price": 1.3,
                    "quantity": 1,
                    "duration_seconds": 2700,
                },  # +30, 45-90m
                {
                    **common_payload,
                    "entry_price": 2.0,
                    "exit_price": 1.9,
                    "quantity": 1,
                    "duration_seconds": 7200,
                },  # -10, 90m+
                {
                    **common_payload,
                    "entry_price": 1.0,
                    "exit_price": 1.4,
                    "quantity": 1,
                },  # +40, missing duration -> excluded
            ]

            for payload in payloads:
                response = client.post("/api/trades", json=payload)
                assert response.status_code == 201

            response = client.get(
                "/api/stats/hold-time",
                params={"start": "2026-02-21", "end": "2026-02-21"},
            )
            assert response.status_code == 200
            body = response.json()

            assert body["range"] == {"start": "2026-02-21", "end": "2026-02-21"}
            assert body["excluded_missing_duration"] == 1
            assert body["buckets"] == [
                {
                    "label": "0-2m",
                    "min_seconds": 0,
                    "max_seconds": 120,
                    "count": 1,
                    "total_pnl_usd": 50.0,
                    "win_rate": 1.0,
                    "avg_pnl_usd": 50.0,
                },
                {
                    "label": "2-5m",
                    "min_seconds": 120,
                    "max_seconds": 300,
                    "count": 1,
                    "total_pnl_usd": -20.0,
                    "win_rate": 0.0,
                    "avg_pnl_usd": -20.0,
                },
                {
                    "label": "5-10m",
                    "min_seconds": 300,
                    "max_seconds": 600,
                    "count": 0,
                    "total_pnl_usd": 0.0,
                    "win_rate": 0.0,
                    "avg_pnl_usd": 0.0,
                },
                {
                    "label": "10-20m",
                    "min_seconds": 600,
                    "max_seconds": 1200,
                    "count": 1,
                    "total_pnl_usd": 0.0,
                    "win_rate": 0.0,
                    "avg_pnl_usd": 0.0,
                },
                {
                    "label": "20-45m",
                    "min_seconds": 1200,
                    "max_seconds": 2700,
                    "count": 0,
                    "total_pnl_usd": 0.0,
                    "win_rate": 0.0,
                    "avg_pnl_usd": 0.0,
                },
                {
                    "label": "45-90m",
                    "min_seconds": 2700,
                    "max_seconds": 5400,
                    "count": 1,
                    "total_pnl_usd": 30.0,
                    "win_rate": 1.0,
                    "avg_pnl_usd": 30.0,
                },
                {
                    "label": "90m+",
                    "min_seconds": 5400,
                    "max_seconds": None,
                    "count": 1,
                    "total_pnl_usd": -10.0,
                    "win_rate": 0.0,
                    "avg_pnl_usd": -10.0,
                },
            ]
    finally:
        app.dependency_overrides.clear()


def test_stats_hold_time_respects_date_range(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_stats_hold_time_date_filter.db")
    try:
        with client:
            common_payload = {
                "ticker": "QQQ",
                "direction": "CALL",
                "emotion_id": emotion_ids["CALM"],
                "rule_followed": True,
                "setup_id": setup_ids["CHOP"],
                "notes": "hold time filter test",
            }

            payloads = [
                {
                    **common_payload,
                    "date": "2026-02-20",
                    "entry_price": 1.0,
                    "exit_price": 1.5,
                    "quantity": 1,
                    "duration_seconds": 180,
                },  # +50, 2-5m in range
                {
                    **common_payload,
                    "date": "2026-02-20",
                    "entry_price": 1.0,
                    "exit_price": 1.4,
                    "quantity": 1,
                },  # +40, missing duration in range
                {
                    **common_payload,
                    "date": "2026-02-22",
                    "entry_price": 2.0,
                    "exit_price": 1.8,
                    "quantity": 1,
                    "duration_seconds": 180,
                },  # -20, out of range
            ]

            for payload in payloads:
                response = client.post("/api/trades", json=payload)
                assert response.status_code == 201

            response = client.get(
                "/api/stats/hold-time",
                params={"start": "2026-02-20", "end": "2026-02-20"},
            )
            assert response.status_code == 200
            body = response.json()

            assert body["range"] == {"start": "2026-02-20", "end": "2026-02-20"}
            assert body["excluded_missing_duration"] == 1
            bucket_2_5m = next(bucket for bucket in body["buckets"] if bucket["label"] == "2-5m")
            assert bucket_2_5m == {
                "label": "2-5m",
                "min_seconds": 120,
                "max_seconds": 300,
                "count": 1,
                "total_pnl_usd": 50.0,
                "win_rate": 1.0,
                "avg_pnl_usd": 50.0,
            }
    finally:
        app.dependency_overrides.clear()
