from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.emotion_option import EmotionOption
from app.models.setup_option import SetupOption


def _build_client(tmp_path: Path, db_name: str) -> tuple[TestClient, int, int]:
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
        setup_id = setup.id
        emotion_id = emotion.id

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), setup_id, emotion_id


def _create_trade(client: TestClient, setup_id: int, emotion_id: int) -> int:
    response = client.post(
        "/api/trades",
        json={
            "date": "2026-02-25",
            "ticker": "SPY",
            "direction": "CALL",
            "entry_price": 1.0,
            "exit_price": 1.2,
            "quantity": 1,
            "setup_id": setup_id,
            "emotion_id": emotion_id,
            "rule_followed": True,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_fill_crud_updates_trade_summary(tmp_path: Path) -> None:
    client, setup_id, emotion_id = _build_client(tmp_path, "test_trade_fill_crud.db")
    try:
        with client:
            trade_id = _create_trade(client, setup_id, emotion_id)

            add_buy_response = client.post(
                f"/api/trades/{trade_id}/fills",
                json={
                    "side": "BUY",
                    "quantity": 1,
                    "price": 1.0,
                    "filled_at": "2026-02-25T09:30:00",
                },
            )
            assert add_buy_response.status_code == 201
            trade_after_buy = add_buy_response.json()
            assert trade_after_buy["total_pnl_usd"] == 0.0
            assert trade_after_buy["total_entry_qty"] == 1
            assert trade_after_buy["total_exit_qty"] == 0
            assert len(trade_after_buy["fills"]) == 1

            add_sell_response = client.post(
                f"/api/trades/{trade_id}/fills",
                json={
                    "side": "SELL",
                    "quantity": 1,
                    "price": 1.4,
                    "filled_at": "2026-02-25T09:45:00",
                },
            )
            assert add_sell_response.status_code == 201
            trade_after_sell = add_sell_response.json()
            assert trade_after_sell["total_pnl_usd"] == 40.0
            assert trade_after_sell["realized_pnl_usd"] == 40.0
            assert trade_after_sell["pnl"] == 0.4
            assert trade_after_sell["duration_seconds"] == 900
            assert len(trade_after_sell["fills"]) == 2

            sell_fill_id = next(
                fill["id"] for fill in trade_after_sell["fills"] if fill["side"] == "SELL"
            )
            update_response = client.put(
                f"/api/trades/{trade_id}/fills/{sell_fill_id}",
                json={
                    "side": "SELL",
                    "quantity": 1,
                    "price": 1.6,
                    "filled_at": "2026-02-25T09:45:00",
                },
            )
            assert update_response.status_code == 200
            trade_after_edit = update_response.json()
            assert trade_after_edit["total_pnl_usd"] == 60.0
            assert trade_after_edit["realized_pnl_usd"] == 60.0
            assert trade_after_edit["pnl"] == 0.6
            assert len(trade_after_edit["fills"]) == 2

            delete_response = client.delete(f"/api/trades/{trade_id}/fills/{sell_fill_id}")
            assert delete_response.status_code == 200
            trade_after_delete = delete_response.json()
            assert trade_after_delete["total_pnl_usd"] == 0.0
            assert trade_after_delete["total_entry_qty"] == 1
            assert trade_after_delete["total_exit_qty"] == 0
            assert len(trade_after_delete["fills"]) == 1
    finally:
        app.dependency_overrides.clear()


def test_fill_validation_errors(tmp_path: Path) -> None:
    client, setup_id, emotion_id = _build_client(tmp_path, "test_trade_fill_validation.db")
    try:
        with client:
            trade_id = _create_trade(client, setup_id, emotion_id)

            zero_quantity_response = client.post(
                f"/api/trades/{trade_id}/fills",
                json={"side": "BUY", "quantity": 0, "price": 1.0},
            )
            assert zero_quantity_response.status_code == 422

            negative_price_response = client.post(
                f"/api/trades/{trade_id}/fills",
                json={"side": "BUY", "quantity": 1, "price": -0.01},
            )
            assert negative_price_response.status_code == 422
    finally:
        app.dependency_overrides.clear()
