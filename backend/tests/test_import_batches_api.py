import json
from datetime import date, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.emotion_option import EmotionOption
from app.models.import_batch import ImportBatch, ImportBatchStatus
from app.models.setup_option import SetupOption
from app.models.trade import Trade, TradeDirection


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


def _seed_setup_and_emotion(session: Session) -> tuple[int, int]:
    setup = SetupOption(name="HOD_BREAK", is_active=True, sort_order=1)
    emotion = EmotionOption(name="CALM", is_active=True, sort_order=1)
    session.add_all([setup, emotion])
    session.commit()
    session.refresh(setup)
    session.refresh(emotion)
    return setup.id, emotion.id


def test_import_batches_list_returns_sorted_batches(tmp_path: Path) -> None:
    client, testing_session_local = _build_client(tmp_path, "test_import_batches_list.db")
    try:
        with testing_session_local() as session:
            older = ImportBatch(
                source="tos_csv",
                original_filename="older.csv",
                status=ImportBatchStatus.PREVIEWED,
                detected_trades_count=2,
                matched_pairs_count=1,
                unmatched_opens_count=1,
                unmatched_closes_count=0,
                committed_count=1,
                skipped_duplicates_count=0,
                warnings_json=json.dumps(["w1"]),
                created_at=datetime(2026, 2, 20, 9, 0, 0),
            )
            newer = ImportBatch(
                source="tos_csv",
                original_filename="newer.csv",
                status=ImportBatchStatus.COMMITTED,
                detected_trades_count=3,
                matched_pairs_count=2,
                unmatched_opens_count=1,
                unmatched_closes_count=1,
                committed_count=2,
                skipped_duplicates_count=1,
                warnings_json=json.dumps(["w1", "w2"]),
                created_at=datetime(2026, 2, 21, 9, 0, 0),
            )
            other_source = ImportBatch(
                source="manual_csv",
                original_filename="other.csv",
                status=ImportBatchStatus.PREVIEWED,
                created_at=datetime(2026, 2, 22, 9, 0, 0),
            )
            session.add_all([older, newer, other_source])
            session.commit()
            session.refresh(older)
            session.refresh(newer)

        with client:
            response = client.get("/api/import/batches", params={"source": "tos_csv"})
            assert response.status_code == 200
            body = response.json()

        assert [item["id"] for item in body] == [newer.id, older.id]
        assert body[0]["original_filename"] == "newer.csv"
        assert body[0]["warnings_count"] == 2
        assert body[0]["matched_pairs_count"] == 2
        assert body[0]["unmatched_opens_count"] == 1
        assert body[0]["unmatched_closes_count"] == 1
        assert body[1]["original_filename"] == "older.csv"
        assert body[1]["warnings_count"] == 1
        assert body[1]["matched_pairs_count"] == 1
        assert body[1]["unmatched_opens_count"] == 1
        assert body[1]["unmatched_closes_count"] == 0
    finally:
        app.dependency_overrides.clear()


def test_import_batch_detail_returns_metrics_warnings_and_pnl_summary(tmp_path: Path) -> None:
    client, testing_session_local = _build_client(tmp_path, "test_import_batch_detail.db")
    try:
        with testing_session_local() as session:
            setup_id, emotion_id = _seed_setup_and_emotion(session)
            batch = ImportBatch(
                source="tos_csv",
                original_filename="detail.csv",
                file_hash="abc123",
                status=ImportBatchStatus.COMMITTED,
                parsed_rows_count=12,
                fills_parsed_count=6,
                detected_trades_count=2,
                matched_pairs_count=2,
                unmatched_opens_count=1,
                unmatched_closes_count=0,
                excluded_count=1,
                warnings_json=json.dumps(["warning 1", "warning 2"]),
                fills_json=json.dumps(
                    [
                        {
                            "exec_datetime": "2026-02-21T09:35:00",
                            "side": "BUY",
                            "pos_effect": "TO OPEN",
                            "qty": 1,
                            "symbol": "SPY",
                            "exp": "02/21/26",
                            "strike": 500.0,
                            "option_type": "CALL",
                            "price": 1.0,
                        }
                    ]
                ),
                unmatched_opens_json=json.dumps(
                    [
                        {
                            "exec_datetime": "2026-02-21T10:15:00",
                            "side": "BUY",
                            "pos_effect": "TO OPEN",
                            "qty": 1,
                            "symbol": "QQQ",
                            "exp": "02/21/26",
                            "strike": 450.0,
                            "option_type": "PUT",
                            "price": 1.2,
                        }
                    ]
                ),
                unmatched_closes_json=json.dumps([]),
                committed_count=2,
                skipped_duplicates_count=1,
                commit_errors_json=json.dumps(["duplicate skipped"]),
            )
            session.add(batch)
            session.commit()
            session.refresh(batch)
            batch_id = batch.id

            session.add_all(
                [
                    Trade(
                        date=date(2026, 2, 21),
                        ticker="SPY",
                        direction=TradeDirection.CALL,
                        entry_price=1.0,
                        exit_price=1.4,
                        pnl=0.4,
                        quantity=1,
                        contract_multiplier=100,
                        total_pnl_usd=40.0,
                        setup_id=setup_id,
                        emotion_id=emotion_id,
                        rule_followed=True,
                        import_batch_id=batch_id,
                    ),
                    Trade(
                        date=date(2026, 2, 21),
                        ticker="QQQ",
                        direction=TradeDirection.CALL,
                        entry_price=2.0,
                        exit_price=2.2,
                        pnl=0.2,
                        quantity=1,
                        contract_multiplier=100,
                        total_pnl_usd=20.0,
                        setup_id=setup_id,
                        emotion_id=emotion_id,
                        rule_followed=True,
                        import_batch_id=batch_id,
                    ),
                ]
            )
            session.commit()

        with client:
            response = client.get(f"/api/import/batches/{batch_id}")
            assert response.status_code == 200
            body = response.json()

        assert body["id"] == batch_id
        assert body["source"] == "tos_csv"
        assert body["original_filename"] == "detail.csv"
        assert body["status"] == "committed"
        assert body["parsed_rows_count"] == 12
        assert body["fills_parsed_count"] == 6
        assert body["detected_trades_count"] == 2
        assert body["matched_pairs_count"] == 2
        assert body["unmatched_opens_count"] == 1
        assert body["unmatched_closes_count"] == 0
        assert body["excluded_count"] == 1
        assert body["warnings"] == ["warning 1", "warning 2"]
        assert body["fills_count"] == 1
        assert len(body["fills"]) == 1
        assert body["fills"][0]["symbol"] == "SPY"
        assert len(body["unmatched_opens"]) == 1
        assert body["unmatched_opens"][0]["symbol"] == "QQQ"
        assert body["unmatched_closes"] == []
        assert body["committed_count"] == 2
        assert body["skipped_duplicates_count"] == 1
        assert body["errors"] == ["duplicate skipped"]
        assert body["pnl_total_committed_usd"] == 60.0
    finally:
        app.dependency_overrides.clear()


def test_import_batch_detail_returns_empty_fill_arrays_when_payload_missing(tmp_path: Path) -> None:
    client, testing_session_local = _build_client(
        tmp_path, "test_import_batch_detail_empty_fills.db"
    )
    try:
        with testing_session_local() as session:
            batch = ImportBatch(
                source="tos_csv",
                original_filename="empty.json.csv",
                status=ImportBatchStatus.PREVIEWED,
                parsed_rows_count=3,
                fills_parsed_count=0,
                detected_trades_count=0,
                matched_pairs_count=0,
                unmatched_opens_count=0,
                unmatched_closes_count=0,
                excluded_count=0,
            )
            session.add(batch)
            session.commit()
            session.refresh(batch)
            batch_id = batch.id

        with client:
            response = client.get(f"/api/import/batches/{batch_id}")
            assert response.status_code == 200
            body = response.json()

        assert body["id"] == batch_id
        assert body["matched_pairs_count"] == 0
        assert body["unmatched_opens_count"] == 0
        assert body["unmatched_closes_count"] == 0
        assert body["fills_count"] == 0
        assert body["fills"] == []
        assert body["unmatched_opens"] == []
        assert body["unmatched_closes"] == []
    finally:
        app.dependency_overrides.clear()
