from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app


def test_ticker_normalization_and_recent_distinct_ordering(tmp_path: Path) -> None:
    db_path = tmp_path / "test_tickers_api.db"
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

    try:
        with TestClient(app) as client:
            setup_response = client.post("/api/setups", json={"name": "HOD_BREAK"})
            assert setup_response.status_code == 201
            setup_id = setup_response.json()["id"]

            emotion_response = client.post("/api/emotions", json={"name": "CALM"})
            assert emotion_response.status_code == 201
            emotion_id = emotion_response.json()["id"]

            trade_payload = {
                "direction": "CALL",
                "entry_price": 1.0,
                "exit_price": 1.2,
                "setup_id": setup_id,
                "emotion_id": emotion_id,
                "rule_followed": True,
                "notes": "ticker test",
            }

            first_trade = client.post(
                "/api/trades",
                json={**trade_payload, "date": "2026-02-20", "ticker": "  nvda  "},
            )
            assert first_trade.status_code == 201
            assert first_trade.json()["ticker"] == "NVDA"

            assert (
                client.post(
                    "/api/trades",
                    json={**trade_payload, "date": "2026-02-21", "ticker": "aapl"},
                ).status_code
                == 201
            )
            assert (
                client.post(
                    "/api/trades",
                    json={**trade_payload, "date": "2026-02-22", "ticker": "NvDa"},
                ).status_code
                == 201
            )
            assert (
                client.post(
                    "/api/trades",
                    json={**trade_payload, "date": "2026-02-22", "ticker": " msft "},
                ).status_code
                == 201
            )

            recent_tickers = client.get("/api/tickers")
            assert recent_tickers.status_code == 200
            assert recent_tickers.json()[:3] == ["MSFT", "NVDA", "AAPL"]

            limited_tickers = client.get("/api/tickers", params={"limit": 2})
            assert limited_tickers.status_code == 200
            assert limited_tickers.json() == ["MSFT", "NVDA"]
    finally:
        app.dependency_overrides.clear()
