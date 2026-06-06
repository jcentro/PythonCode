from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.emotion_option import EmotionOption
from app.models.setup_option import SetupOption
from app.models.trade_fill import TradeFill, TradeFillSide


def _build_client(
    tmp_path: Path, db_name: str
) -> tuple[TestClient, dict[str, int], dict[str, int], sessionmaker[Session]]:
    db_path = tmp_path / db_name
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, class_=Session
    )
    Base.metadata.create_all(bind=engine)

    with testing_session_local() as session:
        setup = SetupOption(name="HOD_BREAK", is_active=True, sort_order=1)
        emotion = EmotionOption(name="CALM", is_active=True, sort_order=1)
        session.add_all([setup, emotion])
        session.commit()
        session.refresh(setup)
        session.refresh(emotion)
        setup_ids = {setup.name: setup.id}
        emotion_ids = {emotion.name: emotion.id}

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), setup_ids, emotion_ids, testing_session_local


def _create_trade(
    client: TestClient,
    *,
    setup_id: int,
    emotion_id: int,
    date: str = "2026-02-21",
) -> int:
    response = client.post(
        "/api/trades",
        json={
            "date": date,
            "ticker": "SPY",
            "direction": "CALL",
            "entry_price": 9.99,
            "exit_price": 9.5,
            "quantity": 5,
            "setup_id": setup_id,
            "emotion_id": emotion_id,
            "rule_followed": True,
            "notes": "fill-summary-test",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_trades_include_fill_computed_summary_when_include_fills_true(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids, testing_session_local = _build_client(
        tmp_path, "test_trade_fill_summary_full.db"
    )
    try:
        with client:
            trade_id = _create_trade(
                client,
                setup_id=setup_ids["HOD_BREAK"],
                emotion_id=emotion_ids["CALM"],
            )

            with testing_session_local() as session:
                session.add_all(
                    [
                        TradeFill(
                            trade_id=trade_id,
                            filled_at=datetime(2026, 2, 21, 9, 30, 0),
                            side=TradeFillSide.BUY,
                            quantity=1,
                            price=1.0,
                            source="manual",
                        ),
                        TradeFill(
                            trade_id=trade_id,
                            filled_at=datetime(2026, 2, 21, 9, 40, 0),
                            side=TradeFillSide.BUY,
                            quantity=1,
                            price=1.2,
                            source="manual",
                        ),
                        TradeFill(
                            trade_id=trade_id,
                            filled_at=datetime(2026, 2, 21, 9, 50, 0),
                            side=TradeFillSide.SELL,
                            quantity=1,
                            price=1.4,
                            source="manual",
                        ),
                        TradeFill(
                            trade_id=trade_id,
                            filled_at=datetime(2026, 2, 21, 10, 0, 0),
                            side=TradeFillSide.SELL,
                            quantity=1,
                            price=1.6,
                            source="manual",
                        ),
                    ]
                )
                session.commit()

            response = client.get(
                "/api/trades",
                params={"date": "2026-02-21", "include_fills": "true"},
            )
            assert response.status_code == 200
            trades = response.json()
            assert len(trades) == 1

            trade = trades[0]
            assert trade["id"] == trade_id
            assert trade["total_entry_qty"] == 2
            assert trade["total_exit_qty"] == 2
            assert trade["avg_entry_price"] == 1.1
            assert trade["avg_exit_price"] == 1.5
            assert trade["pnl"] == 0.4
            assert trade["realized_pnl_usd"] == 80.0
            assert trade["total_pnl_usd"] == 80.0
            assert trade["duration_seconds"] == 1800
            assert trade["is_partial"] is False
            assert len(trade["fills"]) == 4
    finally:
        app.dependency_overrides.clear()


def test_trades_mark_partial_when_exit_qty_is_less_than_entry_qty(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids, testing_session_local = _build_client(
        tmp_path, "test_trade_fill_summary_partial.db"
    )
    try:
        with client:
            trade_id = _create_trade(
                client,
                setup_id=setup_ids["HOD_BREAK"],
                emotion_id=emotion_ids["CALM"],
            )

            with testing_session_local() as session:
                session.add_all(
                    [
                        TradeFill(
                            trade_id=trade_id,
                            filled_at=datetime(2026, 2, 21, 9, 30, 0),
                            side=TradeFillSide.BUY,
                            quantity=1,
                            price=1.0,
                            source="manual",
                        ),
                        TradeFill(
                            trade_id=trade_id,
                            filled_at=datetime(2026, 2, 21, 9, 35, 0),
                            side=TradeFillSide.BUY,
                            quantity=1,
                            price=1.2,
                            source="manual",
                        ),
                        TradeFill(
                            trade_id=trade_id,
                            filled_at=datetime(2026, 2, 21, 9, 50, 0),
                            side=TradeFillSide.SELL,
                            quantity=1,
                            price=1.3,
                            source="manual",
                        ),
                    ]
                )
                session.commit()

            response = client.get("/api/trades", params={"date": "2026-02-21"})
            assert response.status_code == 200
            trade = response.json()[0]

            assert trade["total_entry_qty"] == 2
            assert trade["total_exit_qty"] == 1
            assert trade["is_partial"] is True
            assert trade["total_pnl_usd"] == 20.0
    finally:
        app.dependency_overrides.clear()


def test_stats_summary_uses_fill_computed_realized_pnl(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids, testing_session_local = _build_client(
        tmp_path, "test_trade_fill_summary_stats.db"
    )
    try:
        with client:
            trade_id = _create_trade(
                client,
                setup_id=setup_ids["HOD_BREAK"],
                emotion_id=emotion_ids["CALM"],
            )

            with testing_session_local() as session:
                session.add_all(
                    [
                        TradeFill(
                            trade_id=trade_id,
                            filled_at=datetime(2026, 2, 21, 9, 30, 0),
                            side=TradeFillSide.BUY,
                            quantity=1,
                            price=1.0,
                            source="manual",
                        ),
                        TradeFill(
                            trade_id=trade_id,
                            filled_at=datetime(2026, 2, 21, 9, 40, 0),
                            side=TradeFillSide.BUY,
                            quantity=1,
                            price=1.2,
                            source="manual",
                        ),
                        TradeFill(
                            trade_id=trade_id,
                            filled_at=datetime(2026, 2, 21, 9, 55, 0),
                            side=TradeFillSide.SELL,
                            quantity=1,
                            price=1.4,
                            source="manual",
                        ),
                        TradeFill(
                            trade_id=trade_id,
                            filled_at=datetime(2026, 2, 21, 10, 5, 0),
                            side=TradeFillSide.SELL,
                            quantity=1,
                            price=1.6,
                            source="manual",
                        ),
                    ]
                )
                session.commit()

            stats_response = client.get("/api/stats/summary")
            assert stats_response.status_code == 200
            stats_body = stats_response.json()
            assert stats_body["total_pnl_usd"] == 80.0

            daily_response = client.get("/api/summary/daily", params={"date": "2026-02-21"})
            assert daily_response.status_code == 200
            daily_body = daily_response.json()
            assert daily_body["total_pnl"] == 80.0
    finally:
        app.dependency_overrides.clear()
