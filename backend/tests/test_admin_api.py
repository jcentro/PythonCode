from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.emotion_option import EmotionOption
from app.models.import_batch import ImportBatch
from app.models.setup_option import SetupOption
from app.models.trade import Trade
from app.models.trade_fill import TradeFill


def _build_client(tmp_path: Path, db_name: str) -> tuple[TestClient, sessionmaker[Session]]:
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
    return TestClient(app), testing_session_local


def _seed_test_data(client: TestClient, testing_session_local: sessionmaker[Session]) -> None:
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
    trade_id = trade_response.json()["id"]

    fill_response = client.post(
        f"/api/trades/{trade_id}/fills",
        json={
            "side": "BUY",
            "quantity": 1,
            "price": 1.0,
            "filled_at": "2026-03-01T09:35:00Z",
        },
    )
    assert fill_response.status_code == 201

    with testing_session_local() as db:
        db.add(
            ImportBatch(
                source="tos_csv",
                original_filename="seed.csv",
                detected_trades_count=1,
            )
        )
        db.commit()


def test_admin_wipe_removes_all_data(tmp_path: Path) -> None:
    client, testing_session_local = _build_client(tmp_path, "test_admin_wipe_removes_all_data.db")
    try:
        with client:
            _seed_test_data(client, testing_session_local)

            with testing_session_local() as db:
                assert db.query(SetupOption).count() == 1
                assert db.query(EmotionOption).count() == 1
                assert db.query(Trade).count() == 1
                assert db.query(TradeFill).count() == 1
                assert db.query(ImportBatch).count() == 1

            wipe_response = client.post("/api/admin/wipe")
            assert wipe_response.status_code == 200
            assert wipe_response.json() == {"status": "ok"}

            with testing_session_local() as db:
                assert db.query(SetupOption).count() == 0
                assert db.query(EmotionOption).count() == 0
                assert db.query(Trade).count() == 0
                assert db.query(TradeFill).count() == 0
                assert db.query(ImportBatch).count() == 0
    finally:
        app.dependency_overrides.clear()
