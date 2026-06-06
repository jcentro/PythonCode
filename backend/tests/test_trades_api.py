from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.emotion_option import EmotionOption
from app.models.setup_option import SetupOption


def _seed_default_setups(testing_session_local: sessionmaker[Session]) -> dict[str, int]:
    with testing_session_local() as session:
        session.add_all(
            [
                SetupOption(name="HOD_BREAK", is_active=True, sort_order=1),
                SetupOption(name="LOD_BREAK", is_active=True, sort_order=2),
                SetupOption(name="CHOP", is_active=True, sort_order=3),
                SetupOption(name="OTHER", is_active=True, sort_order=4),
            ]
        )
        session.commit()
        setups = session.query(SetupOption).all()
        return {setup.name: setup.id for setup in setups}


def _seed_default_emotions(testing_session_local: sessionmaker[Session]) -> dict[str, int]:
    with testing_session_local() as session:
        session.add_all(
            [
                EmotionOption(name="CALM", is_active=True, sort_order=1),
                EmotionOption(name="FOMO", is_active=True, sort_order=2),
                EmotionOption(name="REVENGE", is_active=True, sort_order=3),
                EmotionOption(name="HESITATION", is_active=True, sort_order=4),
                EmotionOption(name="OTHER", is_active=True, sort_order=5),
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
    setup_ids = _seed_default_setups(testing_session_local)
    emotion_ids = _seed_default_emotions(testing_session_local)

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), setup_ids, emotion_ids


def _create_trade(client: TestClient, payload: dict) -> dict:
    response = client.post("/api/trades", json=payload)
    assert response.status_code == 201
    return response.json()


def test_post_get_delete_trade(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_trades_api.db")
    try:
        with client:
            create_payload = {
                "date": "2026-02-21",
                "ticker": "SPY",
                "direction": "CALL",
                "entry_price": 1.25,
                "exit_price": 1.75,
                "quantity": 1,
                "setup_id": setup_ids["HOD_BREAK"],
                "emotion_id": emotion_ids["CALM"],
                "rule_followed": True,
                "notes": "Clean breakout setup.",
            }

            create_response = client.post("/api/trades", json=create_payload)
            assert create_response.status_code == 201
            created_trade = create_response.json()
            trade_id = created_trade["id"]

            assert created_trade["date"] == create_payload["date"]
            assert created_trade["ticker"] == create_payload["ticker"]
            assert created_trade["direction"] == create_payload["direction"]
            assert created_trade["entry_price"] == create_payload["entry_price"]
            assert created_trade["exit_price"] == create_payload["exit_price"]
            assert created_trade["pnl"] == 0.5
            assert created_trade["quantity"] == 1
            assert created_trade["contract_multiplier"] == 100
            assert created_trade["total_pnl_usd"] == 50.0
            assert created_trade["setup_id"] == create_payload["setup_id"]
            assert created_trade["setup_name"] == "HOD_BREAK"
            assert created_trade["emotion_id"] == create_payload["emotion_id"]
            assert created_trade["emotion_name"] == "CALM"
            assert created_trade["rule_followed"] is True
            assert created_trade["notes"] == create_payload["notes"]
            assert created_trade["use_fills"] is False
            assert created_trade["source"] is None
            assert created_trade["source_id"] is None

            list_response = client.get("/api/trades")
            assert list_response.status_code == 200
            trades = list_response.json()
            assert len(trades) == 1
            assert trades[0]["id"] == trade_id

            filtered_response = client.get("/api/trades", params={"date": "2026-02-21"})
            assert filtered_response.status_code == 200
            filtered_trades = filtered_response.json()
            assert len(filtered_trades) == 1
            assert filtered_trades[0]["id"] == trade_id

            empty_filtered_response = client.get("/api/trades", params={"date": "2026-02-22"})
            assert empty_filtered_response.status_code == 200
            assert empty_filtered_response.json() == []

            delete_response = client.delete(f"/api/trades/{trade_id}")
            assert delete_response.status_code == 200
            deleted_trade = delete_response.json()
            assert deleted_trade["id"] == trade_id
            assert deleted_trade["pnl"] == 0.5
            assert deleted_trade["total_pnl_usd"] == 50.0
            assert deleted_trade["setup_name"] == "HOD_BREAK"
            assert deleted_trade["emotion_name"] == "CALM"

            post_delete_list = client.get("/api/trades")
            assert post_delete_list.status_code == 200
            assert post_delete_list.json() == []
    finally:
        app.dependency_overrides.clear()


def test_update_trade_success(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_update_trade.db")
    try:
        with client:
            created = client.post(
                "/api/trades",
                json={
                    "date": "2026-02-21",
                    "ticker": "SPY",
                    "direction": "CALL",
                    "entry_price": 1.25,
                    "exit_price": 1.75,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                    "notes": "Original",
                },
            )
            assert created.status_code == 201
            trade_id = created.json()["id"]

            update_response = client.put(
                f"/api/trades/{trade_id}",
                json={
                    "date": "2026-02-21",
                    "ticker": "QQQ",
                    "direction": "PUT",
                    "entry_price": 2.0,
                    "exit_price": 1.7,
                    "quantity": 3,
                    "setup_id": setup_ids["CHOP"],
                    "emotion_id": emotion_ids["FOMO"],
                    "rule_followed": False,
                    "notes": "Updated",
                },
            )

            assert update_response.status_code == 200
            updated = update_response.json()
            assert updated["id"] == trade_id
            assert updated["ticker"] == "QQQ"
            assert updated["direction"] == "PUT"
            assert updated["entry_price"] == 2.0
            assert updated["exit_price"] == 1.7
            assert abs(updated["pnl"] - (-0.3)) < 1e-9
            assert updated["quantity"] == 3
            assert updated["contract_multiplier"] == 100
            assert abs(updated["total_pnl_usd"] - (-90.0)) < 1e-9
            assert updated["setup_id"] == setup_ids["CHOP"]
            assert updated["setup_name"] == "CHOP"
            assert updated["emotion_id"] == emotion_ids["FOMO"]
            assert updated["emotion_name"] == "FOMO"
            assert updated["rule_followed"] is False
            assert updated["notes"] == "Updated"
    finally:
        app.dependency_overrides.clear()


def test_create_trade_with_fills_computes_top_level_values_and_persists_fills(
    tmp_path: Path,
) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_create_trade_with_fills.db")
    try:
        with client:
            response = client.post(
                "/api/trades",
                json={
                    "date": "2026-04-19",
                    "ticker": "AAPL",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 1.0,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                    "notes": "Scaled manually.",
                    "use_fills": True,
                    "fills": [
                        {"side": "BUY", "price": 1.2, "quantity": 1},
                        {"side": "BUY", "price": 1.1, "quantity": 1},
                        {"side": "SELL", "price": 1.5, "quantity": 2},
                    ],
                },
            )

            assert response.status_code == 201
            trade = response.json()
            assert trade["quantity"] == 2
            assert trade["entry_price"] == 1.15
            assert trade["exit_price"] == 1.5
            assert trade["pnl"] == 0.35
            assert trade["total_pnl_usd"] == 70.0
            assert trade["realized_pnl_usd"] == 70.0
            assert trade["total_entry_qty"] == 2
            assert trade["total_exit_qty"] == 2
            assert trade["is_partial"] is False
            assert trade["use_fills"] is True
            assert len(trade["fills"]) == 3
    finally:
        app.dependency_overrides.clear()


def test_create_trade_with_fills_rejects_mismatched_quantities(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(
        tmp_path, "test_create_trade_with_fills_mismatch.db"
    )
    try:
        with client:
            response = client.post(
                "/api/trades",
                json={
                    "date": "2026-04-19",
                    "ticker": "AAPL",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 1.0,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                    "use_fills": True,
                    "fills": [
                        {"side": "BUY", "price": 1.2, "quantity": 1},
                        {"side": "SELL", "price": 1.5, "quantity": 2},
                    ],
                },
            )

            assert response.status_code == 422
            assert (
                response.json()["detail"]
                == "Open positions are not supported yet. Total BUY quantity "
                "must equal total SELL quantity."
            )
    finally:
        app.dependency_overrides.clear()


def test_create_trade_rejects_whitespace_ticker(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_create_trade_blank_ticker.db")
    try:
        with client:
            response = client.post(
                "/api/trades",
                json={
                    "date": "2026-04-19",
                    "ticker": "   ",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 1.2,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                },
            )

            assert response.status_code == 422
            assert response.json()["detail"] == "Ticker is required."
    finally:
        app.dependency_overrides.clear()


def test_create_trade_rejects_non_positive_entry_price(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(
        tmp_path, "test_create_trade_invalid_entry_price.db"
    )
    try:
        with client:
            response = client.post(
                "/api/trades",
                json={
                    "date": "2026-04-19",
                    "ticker": "AAPL",
                    "direction": "CALL",
                    "entry_price": 0,
                    "exit_price": 1.2,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                },
            )

            assert response.status_code == 422
            assert response.json()["detail"] == "Entry price must be greater than zero."
    finally:
        app.dependency_overrides.clear()


def test_update_trade_with_fills_replaces_existing_fills(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_update_trade_with_fills.db")
    try:
        with client:
            created = client.post(
                "/api/trades",
                json={
                    "date": "2026-02-21",
                    "ticker": "SPY",
                    "direction": "CALL",
                    "entry_price": 1.25,
                    "exit_price": 1.75,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                    "notes": "Original",
                },
            )
            assert created.status_code == 201
            trade_id = created.json()["id"]

            update_response = client.put(
                f"/api/trades/{trade_id}",
                json={
                    "date": "2026-02-21",
                    "ticker": "SPY",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 1.0,
                    "quantity": 1,
                    "setup_id": setup_ids["CHOP"],
                    "emotion_id": emotion_ids["FOMO"],
                    "rule_followed": False,
                    "notes": "Scaled update",
                    "use_fills": True,
                    "fills": [
                        {"side": "BUY", "price": 1.0, "quantity": 1},
                        {"side": "BUY", "price": 1.1, "quantity": 1},
                        {"side": "SELL", "price": 1.6, "quantity": 2},
                    ],
                },
            )

            assert update_response.status_code == 200
            updated = update_response.json()
            assert updated["quantity"] == 2
            assert updated["entry_price"] == 1.05
            assert updated["exit_price"] == 1.6
            assert updated["pnl"] == 0.55
            assert updated["total_pnl_usd"] == 110.0
            assert updated["setup_id"] == setup_ids["CHOP"]
            assert updated["emotion_id"] == emotion_ids["FOMO"]
            assert len(updated["fills"]) == 3
    finally:
        app.dependency_overrides.clear()


def test_update_trade_invalid_id_returns_404(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_update_trade_404.db")
    try:
        with client:
            update_response = client.put(
                "/api/trades/9999",
                json={
                    "date": "2026-02-21",
                    "ticker": "SPY",
                    "direction": "CALL",
                    "entry_price": 1.25,
                    "exit_price": 1.75,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                    "notes": "Missing row",
                },
            )
            assert update_response.status_code == 404
            assert update_response.json()["detail"] == "Trade not found"
    finally:
        app.dependency_overrides.clear()


def test_update_trade_validation_error_returns_422(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_update_trade_422.db")
    try:
        with client:
            created = client.post(
                "/api/trades",
                json={
                    "date": "2026-02-21",
                    "ticker": "SPY",
                    "direction": "CALL",
                    "entry_price": 1.25,
                    "exit_price": 1.75,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                    "notes": "Original",
                },
            )
            assert created.status_code == 201
            trade_id = created.json()["id"]

            update_response = client.put(
                f"/api/trades/{trade_id}",
                json={
                    "date": "2026-02-21",
                    "ticker": "",
                    "direction": "CALL",
                    "entry_price": 1.25,
                    "exit_price": 1.75,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                    "notes": "Invalid ticker",
                },
            )
            assert update_response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_update_trade_with_fills_rejects_missing_sell_fill(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(
        tmp_path, "test_update_trade_with_fills_missing_sell.db"
    )
    try:
        with client:
            created = client.post(
                "/api/trades",
                json={
                    "date": "2026-02-21",
                    "ticker": "SPY",
                    "direction": "CALL",
                    "entry_price": 1.25,
                    "exit_price": 1.75,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                    "notes": "Original",
                },
            )
            assert created.status_code == 201
            trade_id = created.json()["id"]

            update_response = client.put(
                f"/api/trades/{trade_id}",
                json={
                    "date": "2026-02-21",
                    "ticker": "SPY",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 1.0,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                    "use_fills": True,
                    "fills": [
                        {"side": "BUY", "price": 1.0, "quantity": 1},
                    ],
                },
            )

            assert update_response.status_code == 422
            assert (
                update_response.json()["detail"]
                == "Add at least one BUY fill and one SELL fill."
            )
    finally:
        app.dependency_overrides.clear()


def test_patch_trade_updates_only_provided_fields(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_patch_trade_partial.db")
    try:
        with client:
            created = client.post(
                "/api/trades",
                json={
                    "date": "2026-02-21",
                    "ticker": "SPY",
                    "direction": "CALL",
                    "entry_price": 1.25,
                    "exit_price": 1.75,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                    "notes": "Original",
                },
            )
            assert created.status_code == 201
            trade = created.json()
            trade_id = trade["id"]

            patch_response = client.patch(
                f"/api/trades/{trade_id}",
                json={"setup_id": setup_ids["CHOP"]},
            )
            assert patch_response.status_code == 200
            patched = patch_response.json()
            assert patched["setup_id"] == setup_ids["CHOP"]
            assert patched["setup_name"] == "CHOP"
            assert patched["emotion_id"] == emotion_ids["CALM"]
            assert patched["emotion_name"] == "CALM"
            assert patched["rule_followed"] is True
            assert patched["ticker"] == "SPY"
            assert patched["notes"] == "Original"
    finally:
        app.dependency_overrides.clear()


def test_patch_trade_supports_rule_followed_unknown(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_patch_trade_rule_null.db")
    try:
        with client:
            created = client.post(
                "/api/trades",
                json={
                    "date": "2026-02-21",
                    "ticker": "SPY",
                    "direction": "CALL",
                    "entry_price": 1.25,
                    "exit_price": 1.75,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                },
            )
            assert created.status_code == 201
            trade_id = created.json()["id"]

            patch_response = client.patch(
                f"/api/trades/{trade_id}",
                json={"rule_followed": None},
            )
            assert patch_response.status_code == 200
            patched = patch_response.json()
            assert patched["rule_followed"] is None
            assert patched["setup_id"] == setup_ids["HOD_BREAK"]
            assert patched["emotion_id"] == emotion_ids["CALM"]

            unknown_response = client.get("/api/trades", params={"rule_followed": "unknown"})
            assert unknown_response.status_code == 200
            assert [row["id"] for row in unknown_response.json()] == [trade_id]
    finally:
        app.dependency_overrides.clear()


def test_patch_trade_requires_at_least_one_field(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_patch_trade_empty_payload.db")
    try:
        with client:
            created = client.post(
                "/api/trades",
                json={
                    "date": "2026-02-21",
                    "ticker": "SPY",
                    "direction": "CALL",
                    "entry_price": 1.25,
                    "exit_price": 1.75,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                },
            )
            assert created.status_code == 201
            trade_id = created.json()["id"]

            patch_response = client.patch(f"/api/trades/{trade_id}", json={})
            assert patch_response.status_code == 422
            assert (
                patch_response.json()["detail"] == "At least one field must be provided for update."
            )
    finally:
        app.dependency_overrides.clear()


def test_create_trade_invalid_setup_id_returns_422(tmp_path: Path) -> None:
    client, _, emotion_ids = _build_client(tmp_path, "test_create_trade_invalid_setup_id.db")
    try:
        with client:
            response = client.post(
                "/api/trades",
                json={
                    "date": "2026-02-21",
                    "ticker": "SPY",
                    "direction": "CALL",
                    "entry_price": 1.25,
                    "exit_price": 1.75,
                    "quantity": 1,
                    "setup_id": 9999,
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                    "notes": "Invalid setup id",
                },
            )

            assert response.status_code == 422
            assert response.json()["detail"] == "Invalid setup_id: 9999"
    finally:
        app.dependency_overrides.clear()


def test_create_trade_invalid_emotion_id_returns_422(tmp_path: Path) -> None:
    client, setup_ids, _ = _build_client(tmp_path, "test_create_trade_invalid_emotion_id.db")
    try:
        with client:
            response = client.post(
                "/api/trades",
                json={
                    "date": "2026-02-21",
                    "ticker": "SPY",
                    "direction": "CALL",
                    "entry_price": 1.25,
                    "exit_price": 1.75,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": 9999,
                    "rule_followed": True,
                    "notes": "Invalid emotion id",
                },
            )

            assert response.status_code == 422
            assert response.json()["detail"] == "Invalid emotion_id: 9999"
    finally:
        app.dependency_overrides.clear()


def test_create_trade_allows_missing_setup_and_emotion(tmp_path: Path) -> None:
    client, _, _ = _build_client(tmp_path, "test_create_trade_without_classification.db")
    try:
        with client:
            response = client.post(
                "/api/trades",
                json={
                    "date": "2026-04-20",
                    "ticker": "SPY",
                    "direction": "CALL",
                    "entry_price": 1.25,
                    "exit_price": 1.75,
                    "quantity": 1,
                    "setup_id": None,
                    "emotion_id": None,
                    "rule_followed": True,
                    "notes": "First-run trade without classifications",
                },
            )

            assert response.status_code == 201
            payload = response.json()
            assert payload["setup_id"] is None
            assert payload["emotion_id"] is None
            assert payload["setup_name"] == ""
            assert payload["emotion_name"] == ""

            unclassified_response = client.get(
                "/api/trades", params={"classification": "unclassified"}
            )
            assert unclassified_response.status_code == 200
            assert [row["id"] for row in unclassified_response.json()] == [payload["id"]]
    finally:
        app.dependency_overrides.clear()


def test_total_pnl_usd_uses_quantity_and_multiplier(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_total_pnl_usd_quantity.db")
    try:
        with client:
            response = client.post(
                "/api/trades",
                json={
                    "date": "2026-02-21",
                    "ticker": "SPY",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 1.5,
                    "quantity": 2,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                    "notes": "quantity pnl test",
                },
            )
            assert response.status_code == 201
            trade = response.json()
            assert trade["pnl"] == 0.5
            assert trade["quantity"] == 2
            assert trade["contract_multiplier"] == 100
            assert trade["total_pnl_usd"] == 100.0
    finally:
        app.dependency_overrides.clear()


def test_create_trade_computes_duration_when_entry_and_exit_times_provided(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_trade_time_duration.db")
    try:
        with client:
            response = client.post(
                "/api/trades",
                json={
                    "date": "2026-02-21",
                    "ticker": "SPY",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 1.5,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                    "entry_time": "09:35:00",
                    "exit_time": "10:05:00",
                },
            )
            assert response.status_code == 201
            trade = response.json()
            assert trade["entry_time"] == "09:35:00"
            assert trade["exit_time"] == "10:05:00"
            assert trade["duration_seconds"] == 1800
    finally:
        app.dependency_overrides.clear()


def test_create_trade_without_times_keeps_duration_null(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_trade_time_missing.db")
    try:
        with client:
            response = client.post(
                "/api/trades",
                json={
                    "date": "2026-02-21",
                    "ticker": "SPY",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 1.5,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                },
            )
            assert response.status_code == 201
            trade = response.json()
            assert trade["entry_time"] is None
            assert trade["exit_time"] is None
            assert trade["duration_seconds"] is None
    finally:
        app.dependency_overrides.clear()


def test_create_trade_with_exit_before_entry_sets_duration_null_without_failure(
    tmp_path: Path,
) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_trade_time_invalid_order.db")
    try:
        with client:
            with pytest.warns(UserWarning, match="duration_seconds set to null"):
                response = client.post(
                    "/api/trades",
                    json={
                        "date": "2026-02-21",
                        "ticker": "SPY",
                        "direction": "CALL",
                        "entry_price": 1.0,
                        "exit_price": 1.5,
                        "quantity": 1,
                        "setup_id": setup_ids["HOD_BREAK"],
                        "emotion_id": emotion_ids["CALM"],
                        "rule_followed": True,
                        "entry_time": "10:05:00",
                        "exit_time": "09:35:00",
                    },
                )

            assert response.status_code == 201
            trade = response.json()
            assert trade["entry_time"] == "10:05:00"
            assert trade["exit_time"] == "09:35:00"
            assert trade["duration_seconds"] is None
    finally:
        app.dependency_overrides.clear()


def test_list_trades_supports_server_side_filters(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_list_trade_filters.db")
    try:
        with client:
            created = [
                _create_trade(
                    client,
                    {
                        "date": "2026-02-20",
                        "ticker": "SPY",
                        "direction": "CALL",
                        "entry_price": 1.0,
                        "exit_price": 1.5,
                        "quantity": 1,
                        "setup_id": setup_ids["HOD_BREAK"],
                        "emotion_id": emotion_ids["CALM"],
                        "rule_followed": True,
                        "notes": "win",
                    },
                ),
                _create_trade(
                    client,
                    {
                        "date": "2026-02-21",
                        "ticker": "QQQ",
                        "direction": "PUT",
                        "entry_price": 2.0,
                        "exit_price": 1.5,
                        "quantity": 1,
                        "setup_id": setup_ids["CHOP"],
                        "emotion_id": emotion_ids["FOMO"],
                        "rule_followed": False,
                        "notes": "loss",
                    },
                ),
                _create_trade(
                    client,
                    {
                        "date": "2026-02-22",
                        "ticker": "msft",
                        "direction": "CALL",
                        "entry_price": 1.0,
                        "exit_price": 1.0,
                        "quantity": 1,
                        "setup_id": setup_ids["LOD_BREAK"],
                        "emotion_id": emotion_ids["REVENGE"],
                        "rule_followed": True,
                        "notes": "breakeven",
                    },
                ),
                _create_trade(
                    client,
                    {
                        "date": "2026-02-23",
                        "ticker": "SPX",
                        "direction": "CALL",
                        "entry_price": 1.0,
                        "exit_price": 1.2,
                        "quantity": 2,
                        "setup_id": setup_ids["HOD_BREAK"],
                        "emotion_id": emotion_ids["CALM"],
                        "rule_followed": False,
                        "notes": "win",
                    },
                ),
            ]
            ids = [trade["id"] for trade in created]

            date_range_response = client.get(
                "/api/trades",
                params={"start": "2026-02-21", "end": "2026-02-22"},
            )
            assert date_range_response.status_code == 200
            assert [trade["id"] for trade in date_range_response.json()] == [ids[2], ids[1]]

            ticker_response = client.get("/api/trades", params={"ticker": "sp"})
            assert ticker_response.status_code == 200
            assert [trade["id"] for trade in ticker_response.json()] == [ids[3], ids[0]]

            setup_response = client.get("/api/trades", params={"setup_id": setup_ids["HOD_BREAK"]})
            assert setup_response.status_code == 200
            assert [trade["id"] for trade in setup_response.json()] == [ids[3], ids[0]]

            unknown_rule_response = client.get("/api/trades", params={"rule_followed": "unknown"})
            assert unknown_rule_response.status_code == 200
            assert unknown_rule_response.json() == []

            win_response = client.get("/api/trades", params={"outcome": "win"})
            assert win_response.status_code == 200
            assert [trade["id"] for trade in win_response.json()] == [ids[3], ids[0]]

            loss_response = client.get("/api/trades", params={"outcome": "loss"})
            assert loss_response.status_code == 200
            assert [trade["id"] for trade in loss_response.json()] == [ids[1]]

            combined_response = client.get(
                "/api/trades",
                params={"ticker": "qq", "outcome": "loss"},
            )
            assert combined_response.status_code == 200
            assert [trade["id"] for trade in combined_response.json()] == [ids[1]]

            manual_source_response = client.get("/api/trades", params={"source": "manual"})
            assert manual_source_response.status_code == 200
            assert [trade["id"] for trade in manual_source_response.json()] == [
                ids[3],
                ids[2],
                ids[1],
                ids[0],
            ]

            tos_source_response = client.get("/api/trades", params={"source": "tos_csv"})
            assert tos_source_response.status_code == 200
            assert tos_source_response.json() == []

            classified_response = client.get("/api/trades", params={"classification": "classified"})
            assert classified_response.status_code == 200
            assert [trade["id"] for trade in classified_response.json()] == [
                ids[3],
                ids[2],
                ids[1],
                ids[0],
            ]

            unclassified_response = client.get(
                "/api/trades",
                params={"classification": "unclassified"},
            )
            assert unclassified_response.status_code == 200
            assert unclassified_response.json() == []
    finally:
        app.dependency_overrides.clear()


def test_list_trades_supports_pattern_and_time_based_filters(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_list_trade_pattern_filters.db")
    try:
        with client:
            created_by_key = {
                "t1": _create_trade(
                    client,
                    {
                        "date": "2026-02-20",
                        "ticker": "T1",
                        "direction": "CALL",
                        "entry_price": 1.0,
                        "exit_price": 0.9,
                        "quantity": 1,
                        "setup_id": setup_ids["CHOP"],
                        "emotion_id": emotion_ids["FOMO"],
                        "rule_followed": False,
                        "entry_time": "09:00:00",
                        "duration_seconds": 60,
                        "notes": "loss",
                    },
                ),
                "t2": _create_trade(
                    client,
                    {
                        "date": "2026-02-20",
                        "ticker": "T2",
                        "direction": "CALL",
                        "entry_price": 1.0,
                        "exit_price": 0.9,
                        "quantity": 1,
                        "setup_id": setup_ids["CHOP"],
                        "emotion_id": emotion_ids["FOMO"],
                        "rule_followed": False,
                        "entry_time": "09:30:00",
                        "duration_seconds": 120,
                        "notes": "loss",
                    },
                ),
                "t3": _create_trade(
                    client,
                    {
                        "date": "2026-02-20",
                        "ticker": "T3",
                        "direction": "CALL",
                        "entry_price": 1.0,
                        "exit_price": 1.2,
                        "quantity": 1,
                        "setup_id": setup_ids["HOD_BREAK"],
                        "emotion_id": emotion_ids["CALM"],
                        "rule_followed": True,
                        "entry_time": "10:00:00",
                        "duration_seconds": 180,
                        "notes": "win",
                    },
                ),
                "t4": _create_trade(
                    client,
                    {
                        "date": "2026-02-20",
                        "ticker": "T4",
                        "direction": "CALL",
                        "entry_price": 1.0,
                        "exit_price": 0.9,
                        "quantity": 1,
                        "setup_id": setup_ids["CHOP"],
                        "emotion_id": emotion_ids["REVENGE"],
                        "rule_followed": False,
                        "entry_time": "10:30:00",
                        "duration_seconds": 6000,
                        "notes": "loss",
                    },
                ),
                "t5": _create_trade(
                    client,
                    {
                        "date": "2026-02-20",
                        "ticker": "T5",
                        "direction": "CALL",
                        "entry_price": 1.0,
                        "exit_price": 1.5,
                        "quantity": 1,
                        "setup_id": setup_ids["LOD_BREAK"],
                        "emotion_id": emotion_ids["CALM"],
                        "rule_followed": True,
                        "notes": "no timing",
                    },
                ),
                "t6": _create_trade(
                    client,
                    {
                        "date": "2026-02-21",
                        "ticker": "T6",
                        "direction": "CALL",
                        "entry_price": 1.0,
                        "exit_price": 1.1,
                        "quantity": 1,
                        "setup_id": setup_ids["HOD_BREAK"],
                        "emotion_id": emotion_ids["CALM"],
                        "rule_followed": True,
                        "entry_time": "09:15:00",
                        "duration_seconds": 180,
                        "notes": "win",
                    },
                ),
                "t7": _create_trade(
                    client,
                    {
                        "date": "2026-02-21",
                        "ticker": "T7",
                        "direction": "CALL",
                        "entry_price": 1.0,
                        "exit_price": 0.8,
                        "quantity": 1,
                        "setup_id": setup_ids["CHOP"],
                        "emotion_id": emotion_ids["FOMO"],
                        "rule_followed": False,
                        "entry_time": "11:00:00",
                        "duration_seconds": 600,
                        "notes": "loss",
                    },
                ),
                "t8": _create_trade(
                    client,
                    {
                        "date": "2026-02-21",
                        "ticker": "T8",
                        "direction": "CALL",
                        "entry_price": 1.0,
                        "exit_price": 1.3,
                        "quantity": 1,
                        "setup_id": setup_ids["OTHER"],
                        "emotion_id": emotion_ids["HESITATION"],
                        "rule_followed": True,
                        "entry_time": "12:00:00",
                        "duration_seconds": 200,
                        "notes": "win",
                    },
                ),
            }

            entry_time_response = client.get(
                "/api/trades",
                params={"entry_time_start_minute": 540, "entry_time_end_minute": 600},
            )
            assert entry_time_response.status_code == 200
            assert [trade["id"] for trade in entry_time_response.json()] == [
                created_by_key["t6"]["id"],
                created_by_key["t2"]["id"],
                created_by_key["t1"]["id"],
            ]

            hold_time_range_response = client.get(
                "/api/trades",
                params={"hold_time_min_seconds": 120, "hold_time_max_seconds": 300},
            )
            assert hold_time_range_response.status_code == 200
            assert [trade["id"] for trade in hold_time_range_response.json()] == [
                created_by_key["t8"]["id"],
                created_by_key["t6"]["id"],
                created_by_key["t3"]["id"],
                created_by_key["t2"]["id"],
            ]

            hold_time_90_plus_response = client.get(
                "/api/trades",
                params={"hold_time_min_seconds": 5400},
            )
            assert hold_time_90_plus_response.status_code == 200
            assert [trade["id"] for trade in hold_time_90_plus_response.json()] == [
                created_by_key["t4"]["id"]
            ]

            first_three_response = client.get(
                "/api/trades",
                params={"trade_index_bucket": "first_3"},
            )
            assert first_three_response.status_code == 200
            assert [trade["id"] for trade in first_three_response.json()] == [
                created_by_key["t8"]["id"],
                created_by_key["t7"]["id"],
                created_by_key["t6"]["id"],
                created_by_key["t3"]["id"],
                created_by_key["t2"]["id"],
                created_by_key["t1"]["id"],
            ]

            after_three_response = client.get(
                "/api/trades",
                params={"trade_index_bucket": "after_3"},
            )
            assert after_three_response.status_code == 200
            assert [trade["id"] for trade in after_three_response.json()] == [
                created_by_key["t5"]["id"],
                created_by_key["t4"]["id"],
            ]

            pattern_response = client.get(
                "/api/trades",
                params={"pattern": "after_2_losses_next_trade"},
            )
            assert pattern_response.status_code == 200
            assert [trade["id"] for trade in pattern_response.json()] == [
                created_by_key["t3"]["id"]
            ]

            pattern_with_date_range_response = client.get(
                "/api/trades",
                params={
                    "start": "2026-02-20",
                    "end": "2026-02-20",
                    "pattern": "after_2_losses_next_trade",
                },
            )
            assert pattern_with_date_range_response.status_code == 200
            assert [trade["id"] for trade in pattern_with_date_range_response.json()] == [
                created_by_key["t3"]["id"]
            ]

            combined_hold_time_and_date_range = client.get(
                "/api/trades",
                params={
                    "start": "2026-02-20",
                    "end": "2026-02-20",
                    "hold_time_min_seconds": 120,
                    "hold_time_max_seconds": 300,
                },
            )
            assert combined_hold_time_and_date_range.status_code == 200
            assert [trade["id"] for trade in combined_hold_time_and_date_range.json()] == [
                created_by_key["t3"]["id"],
                created_by_key["t2"]["id"],
            ]
    finally:
        app.dependency_overrides.clear()


def test_list_trades_classification_filter_combines_with_existing_filters(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_list_trade_classification.db")
    try:
        with client:
            created = {
                "spy": _create_trade(
                    client,
                    {
                        "date": "2026-02-20",
                        "ticker": "SPY",
                        "direction": "CALL",
                        "entry_price": 1.0,
                        "exit_price": 1.1,
                        "quantity": 1,
                        "setup_id": setup_ids["HOD_BREAK"],
                        "emotion_id": emotion_ids["CALM"],
                        "rule_followed": True,
                    },
                ),
                "qqq": _create_trade(
                    client,
                    {
                        "date": "2026-02-21",
                        "ticker": "QQQ",
                        "direction": "CALL",
                        "entry_price": 1.0,
                        "exit_price": 0.9,
                        "quantity": 1,
                        "setup_id": setup_ids["CHOP"],
                        "emotion_id": emotion_ids["FOMO"],
                        "rule_followed": False,
                    },
                ),
                "spx": _create_trade(
                    client,
                    {
                        "date": "2026-02-22",
                        "ticker": "SPX",
                        "direction": "PUT",
                        "entry_price": 1.2,
                        "exit_price": 1.0,
                        "quantity": 1,
                        "setup_id": setup_ids["LOD_BREAK"],
                        "emotion_id": emotion_ids["REVENGE"],
                        "rule_followed": True,
                    },
                ),
            }

            classified_response = client.get("/api/trades", params={"classification": "classified"})
            assert classified_response.status_code == 200
            assert [trade["id"] for trade in classified_response.json()] == [
                created["spx"]["id"],
                created["qqq"]["id"],
                created["spy"]["id"],
            ]

            classified_ticker_filtered_response = client.get(
                "/api/trades",
                params={"classification": "classified", "ticker": "sp"},
            )
            assert classified_ticker_filtered_response.status_code == 200
            assert [trade["id"] for trade in classified_ticker_filtered_response.json()] == [
                created["spx"]["id"],
                created["spy"]["id"],
            ]

            classified_date_filtered_response = client.get(
                "/api/trades",
                params={"classification": "classified", "start": "2026-02-21"},
            )
            assert classified_date_filtered_response.status_code == 200
            assert [trade["id"] for trade in classified_date_filtered_response.json()] == [
                created["spx"]["id"],
                created["qqq"]["id"],
            ]

            unclassified_ticker_filtered_response = client.get(
                "/api/trades",
                params={
                    "classification": "unclassified",
                    "ticker": "sp",
                },
            )
            assert unclassified_ticker_filtered_response.status_code == 200
            assert unclassified_ticker_filtered_response.json() == []

            unclassified_date_filtered_response = client.get(
                "/api/trades",
                params={"classification": "unclassified", "start": "2026-02-21"},
            )
            assert unclassified_date_filtered_response.status_code == 200
            assert unclassified_date_filtered_response.json() == []
    finally:
        app.dependency_overrides.clear()


def test_unclassified_count_matches_server_side_classification(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_unclassified_count.db")
    try:
        with client:
            classified_trade = _create_trade(
                client,
                {
                    "date": "2026-02-20",
                    "ticker": "SPY",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 1.1,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                },
            )
            unknown_rule_trade = _create_trade(
                client,
                {
                    "date": "2026-02-21",
                    "ticker": "QQQ",
                    "direction": "PUT",
                    "entry_price": 1.2,
                    "exit_price": 1.0,
                    "quantity": 1,
                    "setup_id": setup_ids["CHOP"],
                    "emotion_id": emotion_ids["FOMO"],
                    "rule_followed": False,
                },
            )
            _create_trade(
                client,
                {
                    "date": "2026-02-22",
                    "ticker": "NVDA",
                    "direction": "CALL",
                    "entry_price": 2.0,
                    "exit_price": 2.2,
                    "quantity": 1,
                    "setup_id": setup_ids["LOD_BREAK"],
                    "emotion_id": emotion_ids["REVENGE"],
                    "rule_followed": True,
                },
            )

            patch_response = client.patch(
                f"/api/trades/{unknown_rule_trade['id']}",
                json={"rule_followed": None},
            )
            assert patch_response.status_code == 200

            count_response = client.get("/api/trades/unclassified-count")
            assert count_response.status_code == 200
            assert count_response.json() == {"count": 1}

            unclassified_response = client.get(
                "/api/trades", params={"classification": "unclassified"}
            )
            assert unclassified_response.status_code == 200
            unclassified_ids = [row["id"] for row in unclassified_response.json()]
            assert unclassified_ids == [unknown_rule_trade["id"]]
            assert classified_trade["id"] not in unclassified_ids
    finally:
        app.dependency_overrides.clear()


def test_bulk_update_trades_updates_multiple_without_overwriting_other_fields(
    tmp_path: Path,
) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_bulk_update_trades.db")
    try:
        with client:
            trade_1 = _create_trade(
                client,
                {
                    "date": "2026-02-21",
                    "ticker": "SPY",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 1.2,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                    "notes": "first",
                },
            )
            trade_2 = _create_trade(
                client,
                {
                    "date": "2026-02-21",
                    "ticker": "QQQ",
                    "direction": "PUT",
                    "entry_price": 1.3,
                    "exit_price": 1.0,
                    "quantity": 2,
                    "setup_id": setup_ids["LOD_BREAK"],
                    "emotion_id": emotion_ids["FOMO"],
                    "rule_followed": False,
                    "notes": "second",
                },
            )

            response = client.patch(
                "/api/trades/bulk",
                json={
                    "trade_ids": [trade_1["id"], trade_2["id"]],
                    "setup_id": setup_ids["CHOP"],
                },
            )
            assert response.status_code == 200
            assert response.json() == {"updated_count": 2, "errors": []}

            list_response = client.get("/api/trades", params={"date": "2026-02-21"})
            assert list_response.status_code == 200
            by_id = {trade["id"]: trade for trade in list_response.json()}

            assert by_id[trade_1["id"]]["setup_id"] == setup_ids["CHOP"]
            assert by_id[trade_1["id"]]["emotion_id"] == emotion_ids["CALM"]
            assert by_id[trade_1["id"]]["rule_followed"] is True
            assert by_id[trade_2["id"]]["setup_id"] == setup_ids["CHOP"]
            assert by_id[trade_2["id"]]["emotion_id"] == emotion_ids["FOMO"]
            assert by_id[trade_2["id"]]["rule_followed"] is False
    finally:
        app.dependency_overrides.clear()


def test_bulk_update_trades_handles_invalid_ids_with_partial_success(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_bulk_update_partial.db")
    try:
        with client:
            trade = _create_trade(
                client,
                {
                    "date": "2026-02-21",
                    "ticker": "SPY",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 1.1,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                },
            )

            response = client.patch(
                "/api/trades/bulk",
                json={
                    "trade_ids": [trade["id"], 999999],
                    "emotion_id": emotion_ids["REVENGE"],
                },
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["updated_count"] == 1
            assert "Trade not found: 999999" in payload["errors"]

            updated_trade_response = client.get("/api/trades", params={"date": "2026-02-21"})
            assert updated_trade_response.status_code == 200
            updated_trade = updated_trade_response.json()[0]
            assert updated_trade["emotion_id"] == emotion_ids["REVENGE"]
            assert updated_trade["setup_id"] == setup_ids["HOD_BREAK"]
            assert updated_trade["rule_followed"] is True
    finally:
        app.dependency_overrides.clear()


def test_bulk_update_trades_supports_setting_rule_followed_to_unknown(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_bulk_update_rule_unknown.db")
    try:
        with client:
            trade = _create_trade(
                client,
                {
                    "date": "2026-02-21",
                    "ticker": "SPY",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 1.1,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                },
            )

            update_response = client.patch(
                "/api/trades/bulk",
                json={"trade_ids": [trade["id"]], "rule_followed": None},
            )
            assert update_response.status_code == 200
            assert update_response.json() == {"updated_count": 1, "errors": []}

            unknown_rule_response = client.get("/api/trades", params={"rule_followed": "unknown"})
            assert unknown_rule_response.status_code == 200
            assert [row["id"] for row in unknown_rule_response.json()] == [trade["id"]]

            unclassified_response = client.get(
                "/api/trades", params={"classification": "unclassified"}
            )
            assert unclassified_response.status_code == 200
            assert [row["id"] for row in unclassified_response.json()] == [trade["id"]]
    finally:
        app.dependency_overrides.clear()


def test_bulk_update_trades_rejects_inactive_setup_id(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(tmp_path, "test_bulk_update_inactive_setup.db")
    try:
        with client:
            trade = _create_trade(
                client,
                {
                    "date": "2026-02-21",
                    "ticker": "SPY",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 1.1,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                },
            )

            deactivate_response = client.patch(
                f"/api/setups/{setup_ids['CHOP']}",
                json={"is_active": False},
            )
            assert deactivate_response.status_code == 200

            response = client.patch(
                "/api/trades/bulk",
                json={
                    "trade_ids": [trade["id"]],
                    "setup_id": setup_ids["CHOP"],
                },
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["updated_count"] == 0
            assert f"Inactive setup_id: {setup_ids['CHOP']}" in payload["errors"]

            trade_response = client.get("/api/trades", params={"date": "2026-02-21"})
            assert trade_response.status_code == 200
            updated_trade = trade_response.json()[0]
            assert updated_trade["setup_id"] == setup_ids["HOD_BREAK"]
    finally:
        app.dependency_overrides.clear()


def test_bulk_update_trades_rejects_inactive_emotion_id(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids = _build_client(
        tmp_path, "test_bulk_update_inactive_emotion.db"
    )
    try:
        with client:
            trade = _create_trade(
                client,
                {
                    "date": "2026-02-21",
                    "ticker": "SPY",
                    "direction": "CALL",
                    "entry_price": 1.0,
                    "exit_price": 1.1,
                    "quantity": 1,
                    "setup_id": setup_ids["HOD_BREAK"],
                    "emotion_id": emotion_ids["CALM"],
                    "rule_followed": True,
                },
            )

            deactivate_response = client.patch(
                f"/api/emotions/{emotion_ids['FOMO']}",
                json={"is_active": False},
            )
            assert deactivate_response.status_code == 200

            response = client.patch(
                "/api/trades/bulk",
                json={
                    "trade_ids": [trade["id"]],
                    "emotion_id": emotion_ids["FOMO"],
                },
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["updated_count"] == 0
            assert f"Inactive emotion_id: {emotion_ids['FOMO']}" in payload["errors"]

            trade_response = client.get("/api/trades", params={"date": "2026-02-21"})
            assert trade_response.status_code == 200
            updated_trade = trade_response.json()[0]
            assert updated_trade["emotion_id"] == emotion_ids["CALM"]
    finally:
        app.dependency_overrides.clear()


def test_bulk_update_trades_rejects_empty_trade_ids(tmp_path: Path) -> None:
    client, _, _ = _build_client(tmp_path, "test_bulk_update_empty_ids.db")
    try:
        with client:
            response = client.patch(
                "/api/trades/bulk",
                json={"trade_ids": [], "rule_followed": True},
            )
            assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()
