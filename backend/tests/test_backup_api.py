from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app


def _build_client(tmp_path: Path, db_name: str) -> TestClient:
    db_path = tmp_path / db_name
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, class_=Session
    )
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _seed_single_trade(client: TestClient) -> None:
    setup_response = client.post("/api/setups", json={"name": "SEED_SETUP"})
    assert setup_response.status_code == 201
    setup_id = setup_response.json()["id"]

    emotion_response = client.post("/api/emotions", json={"name": "SEED_EMOTION"})
    assert emotion_response.status_code == 201
    emotion_id = emotion_response.json()["id"]

    trade_response = client.post(
        "/api/trades",
        json={
            "date": "2026-03-01",
            "ticker": "SPY",
            "direction": "CALL",
            "entry_price": 1.0,
            "exit_price": 1.2,
            "quantity": 1,
            "setup_id": setup_id,
            "emotion_id": emotion_id,
            "rule_followed": True,
            "notes": "seed",
        },
    )
    assert trade_response.status_code == 201


def test_backup_import_replace_success(tmp_path: Path) -> None:
    client = _build_client(tmp_path, "test_backup_import_replace_success.db")
    try:
        with client:
            _seed_single_trade(client)

            payload = {
                "schema_version": 1,
                "exported_at": "2026-03-15T12:00:00Z",
                "data": {
                    "setups": [
                        {"id": 101, "name": "RESTORE_SETUP_A", "is_active": True, "sort_order": 1},
                        {"id": 102, "name": "RESTORE_SETUP_B", "is_active": False, "sort_order": 2},
                    ],
                    "emotions": [
                        {"id": 201, "name": "RESTORE_EMOTION_A", "is_active": True, "sort_order": 1}
                    ],
                    "trades": [
                        {
                            "id": 301,
                            "date": "2026-03-10",
                            "ticker": "nvda",
                            "direction": "CALL",
                            "entry_price": 1.2,
                            "exit_price": 1.6,
                            "pnl": 0.4,
                            "quantity": 2,
                            "contract_multiplier": 100,
                            "total_pnl_usd": 80.0,
                            "setup_id": 101,
                            "emotion_id": 201,
                            "rule_followed": None,
                            "notes": "restored trade",
                            "entry_time": "09:35:00",
                            "exit_time": "10:05:00",
                            "duration_seconds": 1800,
                            "fills": [
                                {
                                    "filled_at": "2026-03-10T09:35:00Z",
                                    "side": "BUY",
                                    "quantity": 2,
                                    "price": 1.2,
                                },
                                {
                                    "filled_at": "2026-03-10T10:05:00Z",
                                    "side": "SELL",
                                    "quantity": 2,
                                    "price": 1.6,
                                },
                            ],
                        }
                    ],
                },
            }

            restore_response = client.post("/api/backup/import", json=payload)
            assert restore_response.status_code == 200
            assert restore_response.json() == {
                "status": "ok",
                "imported": {"trades": 1, "fills": 2, "setups": 2, "emotions": 1},
            }

            setups_response = client.get("/api/setups", params={"include_inactive": "true"})
            assert setups_response.status_code == 200
            setup_names = {row["name"] for row in setups_response.json()}
            assert setup_names == {"RESTORE_SETUP_A", "RESTORE_SETUP_B"}

            emotions_response = client.get("/api/emotions", params={"include_inactive": "true"})
            assert emotions_response.status_code == 200
            emotion_names = {row["name"] for row in emotions_response.json()}
            assert emotion_names == {"RESTORE_EMOTION_A"}

            trades_response = client.get("/api/trades", params={"include_fills": "true"})
            assert trades_response.status_code == 200
            trades = trades_response.json()
            assert len(trades) == 1
            restored_trade = trades[0]
            assert restored_trade["id"] == 301
            assert restored_trade["ticker"] == "NVDA"
            assert restored_trade["setup_id"] == 101
            assert restored_trade["emotion_id"] == 201
            assert restored_trade["notes"] == "restored trade"
            assert len(restored_trade["fills"]) == 2
    finally:
        app.dependency_overrides.clear()


def test_backup_import_invalid_schema_version_does_not_modify_data(tmp_path: Path) -> None:
    client = _build_client(tmp_path, "test_backup_import_invalid_schema.db")
    try:
        with client:
            _seed_single_trade(client)

            before_response = client.get("/api/trades")
            assert before_response.status_code == 200
            before_trade_ids = [trade["id"] for trade in before_response.json()]
            assert len(before_trade_ids) == 1

            invalid_payload = {
                "schema_version": 99,
                "exported_at": "2026-03-15T12:00:00Z",
                "data": {
                    "setups": [{"id": 1, "name": "INVALID_SETUP", "is_active": True}],
                    "emotions": [{"id": 1, "name": "INVALID_EMOTION", "is_active": True}],
                    "trades": [],
                },
            }

            restore_response = client.post("/api/backup/import", json=invalid_payload)
            assert restore_response.status_code == 422
            assert (
                restore_response.json()["detail"]
                == "Unsupported backup version: 99. Expected 1."
            )

            after_response = client.get("/api/trades")
            assert after_response.status_code == 200
            after_trade_ids = [trade["id"] for trade in after_response.json()]
            assert after_trade_ids == before_trade_ids
    finally:
        app.dependency_overrides.clear()


def test_backup_import_missing_trades_array_rejected_before_writing(tmp_path: Path) -> None:
    client = _build_client(tmp_path, "test_backup_import_missing_trades.db")
    try:
        with client:
            _seed_single_trade(client)

            before_response = client.get("/api/trades")
            assert before_response.status_code == 200
            before_trade_ids = [trade["id"] for trade in before_response.json()]

            invalid_payload = {
                "schema_version": 1,
                "exported_at": "2026-03-15T12:00:00Z",
                "data": {
                    "setups": [{"id": 1, "name": "VALID_SETUP", "is_active": True}],
                    "emotions": [{"id": 1, "name": "VALID_EMOTION", "is_active": True}],
                },
            }

            restore_response = client.post("/api/backup/import", json=invalid_payload)
            assert restore_response.status_code == 422
            assert restore_response.json()["detail"] == "Missing trades array."

            after_response = client.get("/api/trades")
            assert after_response.status_code == 200
            after_trade_ids = [trade["id"] for trade in after_response.json()]
            assert after_trade_ids == before_trade_ids
    finally:
        app.dependency_overrides.clear()


def test_backup_import_invalid_trade_rolls_back_existing_data(tmp_path: Path) -> None:
    client = _build_client(tmp_path, "test_backup_import_invalid_trade.db")
    try:
        with client:
            _seed_single_trade(client)

            before_response = client.get("/api/trades")
            assert before_response.status_code == 200
            before_trade_ids = [trade["id"] for trade in before_response.json()]

            invalid_payload = {
                "schema_version": 1,
                "exported_at": "2026-03-15T12:00:00Z",
                "data": {
                    "setups": [{"id": 101, "name": "RESTORE_SETUP", "is_active": True}],
                    "emotions": [{"id": 201, "name": "RESTORE_EMOTION", "is_active": True}],
                    "trades": [
                        {
                            "id": 301,
                            "date": "2026-03-10",
                            "ticker": "   ",
                            "direction": "CALL",
                            "entry_price": 1.2,
                            "exit_price": 1.6,
                            "pnl": 0.4,
                            "quantity": 2,
                            "contract_multiplier": 100,
                            "total_pnl_usd": 80.0,
                            "setup_id": 101,
                            "emotion_id": 201,
                            "rule_followed": None,
                            "fills": [],
                        }
                    ],
                },
            }

            restore_response = client.post("/api/backup/import", json=invalid_payload)
            assert restore_response.status_code == 422
            assert (
                restore_response.json()["detail"]
                == "Invalid trade at index 0: ticker is required."
            )

            after_response = client.get("/api/trades")
            assert after_response.status_code == 200
            after_trade_ids = [trade["id"] for trade in after_response.json()]
            assert after_trade_ids == before_trade_ids
    finally:
        app.dependency_overrides.clear()


def test_backup_import_invalid_fill_rolls_back_existing_data(tmp_path: Path) -> None:
    client = _build_client(tmp_path, "test_backup_import_invalid_fill.db")
    try:
        with client:
            _seed_single_trade(client)

            before_response = client.get("/api/trades", params={"include_fills": "true"})
            assert before_response.status_code == 200
            before_trade_ids = [trade["id"] for trade in before_response.json()]

            invalid_payload = {
                "schema_version": 1,
                "exported_at": "2026-03-15T12:00:00Z",
                "data": {
                    "setups": [{"id": 101, "name": "RESTORE_SETUP", "is_active": True}],
                    "emotions": [{"id": 201, "name": "RESTORE_EMOTION", "is_active": True}],
                    "trades": [
                        {
                            "id": 301,
                            "date": "2026-03-10",
                            "ticker": "NVDA",
                            "direction": "CALL",
                            "entry_price": 1.2,
                            "exit_price": 1.6,
                            "pnl": 0.4,
                            "quantity": 2,
                            "contract_multiplier": 100,
                            "total_pnl_usd": 80.0,
                            "setup_id": 101,
                            "emotion_id": 201,
                            "rule_followed": True,
                            "fills": [
                                {
                                    "filled_at": "2026-03-10T09:35:00Z",
                                    "side": "BUY",
                                    "quantity": 2,
                                    "price": 0,
                                }
                            ],
                        }
                    ],
                },
            }

            restore_response = client.post("/api/backup/import", json=invalid_payload)
            assert restore_response.status_code == 422
            assert "Invalid fill at trade index 0, fill index 0:" in restore_response.json()[
                "detail"
            ]
            assert "price" in restore_response.json()["detail"]

            after_response = client.get("/api/trades", params={"include_fills": "true"})
            assert after_response.status_code == 200
            after_trade_ids = [trade["id"] for trade in after_response.json()]
            assert after_trade_ids == before_trade_ids
    finally:
        app.dependency_overrides.clear()


def test_backup_import_allows_missing_exported_at(tmp_path: Path) -> None:
    client = _build_client(tmp_path, "test_backup_import_missing_exported_at.db")
    try:
        with client:
            payload = {
                "schema_version": 1,
                "data": {
                    "setups": [{"id": 101, "name": "RESTORE_SETUP", "is_active": True}],
                    "emotions": [{"id": 201, "name": "RESTORE_EMOTION", "is_active": True}],
                    "trades": [
                        {
                            "id": 301,
                            "date": "2026-03-10",
                            "ticker": "NVDA",
                            "direction": "CALL",
                            "entry_price": 1.2,
                            "exit_price": 1.6,
                            "pnl": 0.4,
                            "quantity": 2,
                            "contract_multiplier": 100,
                            "total_pnl_usd": 80.0,
                            "setup_id": 101,
                            "emotion_id": 201,
                            "rule_followed": None,
                            "fills": [],
                        }
                    ],
                },
            }

            restore_response = client.post("/api/backup/import", json=payload)
            assert restore_response.status_code == 200
            assert restore_response.json() == {
                "status": "ok",
                "imported": {"trades": 1, "fills": 0, "setups": 1, "emotions": 1},
            }
    finally:
        app.dependency_overrides.clear()
