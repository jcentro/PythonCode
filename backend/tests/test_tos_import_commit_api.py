from datetime import date, datetime
from pathlib import Path
from textwrap import dedent

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.emotion_option import EmotionOption
from app.models.import_batch import ImportBatch, ImportBatchStatus
from app.models.setup_option import SetupOption
from app.models.trade import Trade, TradeDirection
from app.models.trade_fill import TradeFill
from app.services.tos_import import cache_detected_trades


def _seed_default_setups(testing_session_local: sessionmaker[Session]) -> dict[str, int]:
    with testing_session_local() as session:
        session.add_all(
            [
                SetupOption(name="HOD_BREAK", is_active=True, sort_order=1),
                SetupOption(name="OTHER", is_active=True, sort_order=2),
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
                EmotionOption(name="OTHER", is_active=True, sort_order=2),
            ]
        )
        session.commit()
        emotions = session.query(EmotionOption).all()
        return {emotion.name: emotion.id for emotion in emotions}


def _build_client(
    tmp_path: Path, db_name: str
) -> tuple[TestClient, dict[str, int], dict[str, int], sessionmaker[Session]]:
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
    return TestClient(app), setup_ids, emotion_ids, testing_session_local


def _build_preview_csv() -> str:
    return dedent(
        """
        Account Statement

        Account Trade History
        ,Exec Time,Spread,Side,Qty,Pos Effect,Symbol,Exp,Strike,Type,Price
        ,02/21/26 09:35:00,SINGLE,BUY,+1,TO OPEN,NVDA,02/21/26,500,CALL,1.00
        ,02/21/26 10:05:00,SINGLE,SELL,-1,TO CLOSE,NVDA,02/21/26,500,CALL,1.40

        Cash & Sweep Vehicle
        """
    ).strip()


def _build_scaled_preview_csv() -> str:
    return dedent(
        """
        Account Statement

        Account Trade History
        ,Exec Time,Spread,Side,Qty,Pos Effect,Symbol,Exp,Strike,Type,Price
        ,02/21/26 09:35:00,SINGLE,BUY,+1,TO OPEN,NVDA,02/21/26,500,CALL,1.00
        ,02/21/26 09:40:00,SINGLE,BUY,+1,TO OPEN,NVDA,02/21/26,500,CALL,1.20
        ,02/21/26 10:00:00,SINGLE,SELL,-1,TO CLOSE,NVDA,02/21/26,500,CALL,1.40
        ,02/21/26 10:05:00,SINGLE,SELL,-1,TO CLOSE,NVDA,02/21/26,500,CALL,1.60

        Cash & Sweep Vehicle
        """
    ).strip()


def test_commit_import_inserts_trade_with_server_computed_totals(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids, testing_session_local = _build_client(
        tmp_path, "test_tos_commit_insert.db"
    )
    try:
        with client:
            preview_response = client.post(
                "/api/import/tos/preview",
                files={"file": ("statement.csv", _build_preview_csv(), "text/csv")},
            )
            assert preview_response.status_code == 200
            preview_body = preview_response.json()
            preview_trade = preview_body["detected_trades"][0]
            batch_id = preview_body["batch_id"]
            cache_detected_trades([])

            commit_response = client.post(
                "/api/import/tos/commit",
                json={
                    "batch_id": batch_id,
                    "items": [
                        {
                            "temp_id": preview_trade["temp_id"],
                            "setup_id": setup_ids["HOD_BREAK"],
                            "emotion_id": emotion_ids["CALM"],
                            "rule_followed": False,
                            "notes": "Imported from statement",
                        }
                    ],
                },
            )
            assert commit_response.status_code == 200
            commit_body = commit_response.json()
            assert commit_body == {"imported": 1, "skipped_duplicates": 0, "errors": []}

            trades_response = client.get(
                "/api/trades", params={"date": "2026-02-21", "include_fills": "true"}
            )
            assert trades_response.status_code == 200
            trades = trades_response.json()
            assert len(trades) == 1
            trade = trades[0]
            assert trade["ticker"] == "NVDA"
            assert trade["direction"] == "CALL"
            assert trade["entry_price"] == 1.0
            assert trade["exit_price"] == 1.4
            assert abs(trade["pnl"] - 0.4) < 1e-9
            assert trade["quantity"] == 1
            assert trade["contract_multiplier"] == 100
            assert abs(trade["total_pnl_usd"] - 40.0) < 1e-9
            assert trade["entry_time"] == "09:35:00"
            assert trade["exit_time"] == "10:05:00"
            assert trade["duration_seconds"] == 1800
            assert trade["setup_id"] == setup_ids["HOD_BREAK"]
            assert trade["emotion_id"] == emotion_ids["CALM"]
            assert trade["rule_followed"] is False
            assert trade["notes"] == "Imported from statement"
            assert len(trade["fills"]) == 2
            assert [fill["side"] for fill in trade["fills"]] == ["BUY", "SELL"]

            trades_by_batch_response = client.get(
                "/api/trades",
                params={"import_batch_id": batch_id},
            )
            assert trades_by_batch_response.status_code == 200
            trades_by_batch = trades_by_batch_response.json()
            assert len(trades_by_batch) == 1
            assert trades_by_batch[0]["id"] == trade["id"]

            trades_by_other_batch_response = client.get(
                "/api/trades",
                params={"import_batch_id": batch_id + 1},
            )
            assert trades_by_other_batch_response.status_code == 200
            assert trades_by_other_batch_response.json() == []

            with testing_session_local() as session:
                batch = session.scalar(select(ImportBatch).where(ImportBatch.id == batch_id))
                stored_trade = session.scalar(select(Trade).where(Trade.id == trade["id"]))
                stored_fills = list(
                    session.scalars(
                        select(TradeFill).where(TradeFill.trade_id == trade["id"])
                    ).all()
                )

            assert batch is not None
            assert batch.status == ImportBatchStatus.COMMITTED
            assert batch.committed_count == 1
            assert batch.skipped_duplicates_count == 0
            assert stored_trade is not None
            assert stored_trade.import_batch_id == batch_id
            assert len(stored_fills) == 2
    finally:
        app.dependency_overrides.clear()


def test_commit_import_scaled_trade_inserts_all_fills_and_uses_fill_totals(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids, testing_session_local = _build_client(
        tmp_path, "test_tos_commit_scaled.db"
    )
    try:
        with client:
            preview_response = client.post(
                "/api/import/tos/preview",
                files={"file": ("statement.csv", _build_scaled_preview_csv(), "text/csv")},
            )
            assert preview_response.status_code == 200
            preview_body = preview_response.json()
            preview_trade = preview_body["detected_trades"][0]
            batch_id = preview_body["batch_id"]

            commit_response = client.post(
                "/api/import/tos/commit",
                json={
                    "batch_id": batch_id,
                    "items": [
                        {
                            "temp_id": preview_trade["temp_id"],
                            "setup_id": setup_ids["HOD_BREAK"],
                            "emotion_id": emotion_ids["CALM"],
                        }
                    ],
                },
            )
            assert commit_response.status_code == 200
            assert commit_response.json() == {"imported": 1, "skipped_duplicates": 0, "errors": []}

            trades_response = client.get(
                "/api/trades", params={"date": "2026-02-21", "include_fills": "true"}
            )
            assert trades_response.status_code == 200
            trades = trades_response.json()
            assert len(trades) == 1
            trade = trades[0]
            assert trade["quantity"] == 2
            assert trade["entry_price"] == 1.1
            assert trade["exit_price"] == 1.5
            assert trade["pnl"] == 0.4
            assert trade["total_pnl_usd"] == 80.0
            assert len(trade["fills"]) == 4
            assert [fill["side"] for fill in trade["fills"]] == ["BUY", "BUY", "SELL", "SELL"]

            with testing_session_local() as session:
                stored_trade = session.scalar(select(Trade).where(Trade.id == trade["id"]))
                stored_fills = list(
                    session.scalars(
                        select(TradeFill).where(TradeFill.trade_id == trade["id"])
                    ).all()
                )

            assert stored_trade is not None
            assert stored_trade.total_pnl_usd == 80.0
            assert len(stored_fills) == 4
    finally:
        app.dependency_overrides.clear()


def test_commit_import_skips_duplicate_source_id(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids, testing_session_local = _build_client(
        tmp_path, "test_tos_commit_duplicate.db"
    )
    try:
        with client:
            preview_response = client.post(
                "/api/import/tos/preview",
                files={"file": ("statement.csv", _build_preview_csv(), "text/csv")},
            )
            assert preview_response.status_code == 200
            preview_body = preview_response.json()
            preview_trade = preview_body["detected_trades"][0]
            batch_id = preview_body["batch_id"]
            item_payload = {
                "temp_id": preview_trade["temp_id"],
                "setup_id": setup_ids["HOD_BREAK"],
                "emotion_id": emotion_ids["CALM"],
            }

            first_commit = client.post(
                "/api/import/tos/commit",
                json={"batch_id": batch_id, "items": [item_payload]},
            )
            assert first_commit.status_code == 200
            assert first_commit.json() == {"imported": 1, "skipped_duplicates": 0, "errors": []}

            second_commit = client.post(
                "/api/import/tos/commit",
                json={"batch_id": batch_id, "items": [item_payload]},
            )
            assert second_commit.status_code == 200
            assert second_commit.json() == {"imported": 0, "skipped_duplicates": 1, "errors": []}

            trades_response = client.get("/api/trades", params={"date": "2026-02-21"})
            assert trades_response.status_code == 200
            trades = trades_response.json()
            assert len(trades) == 1

            with testing_session_local() as session:
                batch = session.scalar(select(ImportBatch).where(ImportBatch.id == batch_id))
                trades_in_batch = list(
                    session.scalars(select(Trade).where(Trade.import_batch_id == batch_id)).all()
                )

            assert batch is not None
            assert batch.status == ImportBatchStatus.COMMITTED
            assert batch.committed_count == 0
            assert batch.skipped_duplicates_count == 1
            assert len(trades_in_batch) == 1
    finally:
        app.dependency_overrides.clear()


def test_commit_import_skips_existing_trade_with_matching_signature(tmp_path: Path) -> None:
    client, setup_ids, emotion_ids, testing_session_local = _build_client(
        tmp_path, "test_tos_commit_signature_duplicate.db"
    )
    try:
        with testing_session_local() as session:
            existing_trade = Trade(
                date=date(2026, 2, 21),
                ticker="NVDA",
                direction=TradeDirection.CALL,
                entry_price=1.0,
                exit_price=1.4,
                pnl=0.4,
                quantity=1,
                contract_multiplier=100,
                total_pnl_usd=40.0,
                setup_id=setup_ids["HOD_BREAK"],
                emotion_id=emotion_ids["CALM"],
                rule_followed=True,
                entry_time=datetime.strptime("09:35:00", "%H:%M:%S").time(),
                exit_time=datetime.strptime("10:05:00", "%H:%M:%S").time(),
                duration_seconds=1800,
                source="manual",
                source_id=None,
            )
            session.add(existing_trade)
            session.commit()

        with client:
            preview_response = client.post(
                "/api/import/tos/preview",
                files={"file": ("statement.csv", _build_preview_csv(), "text/csv")},
            )
            assert preview_response.status_code == 200
            preview_trade = preview_response.json()["detected_trades"][0]
            assert preview_trade["duplicate_status"] == "duplicate"

            commit_response = client.post(
                "/api/import/tos/commit",
                json={
                    "batch_id": preview_response.json()["batch_id"],
                    "items": [
                        {
                            "temp_id": preview_trade["temp_id"],
                            "setup_id": setup_ids["HOD_BREAK"],
                            "emotion_id": emotion_ids["CALM"],
                        }
                    ],
                },
            )
            assert commit_response.status_code == 200
            assert commit_response.json() == {"imported": 0, "skipped_duplicates": 1, "errors": []}

            trades_response = client.get("/api/trades", params={"date": "2026-02-21"})
            assert trades_response.status_code == 200
            assert len(trades_response.json()) == 1
    finally:
        app.dependency_overrides.clear()
