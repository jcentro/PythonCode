import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from textwrap import dedent

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.emotion_option import EmotionOption
from app.models.import_batch import ImportBatch, ImportBatchStatus
from app.models.setup_option import SetupOption
from app.models.trade import Trade, TradeDirection
from app.routers import import_tos as import_tos_router
from app.schemas.import_preview import DetectedTradePreview, DetectedTradePreviewFill


def _build_client(tmp_path: Path, db_name: str) -> tuple[TestClient, sessionmaker[Session]]:
    db_path = tmp_path / db_name
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        class_=Session,
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


def _post_preview_csv(client: TestClient, csv_text: str):
    return client.post(
        "/api/import/tos/preview",
        files={"file": ("statement.csv", csv_text, "text/csv")},
    )


def _seed_trade_dependencies(testing_session_local: sessionmaker[Session]) -> tuple[int, int]:
    with testing_session_local() as session:
        setup = SetupOption(name="OTHER", is_active=True, sort_order=1)
        emotion = EmotionOption(name="OTHER", is_active=True, sort_order=1)
        session.add_all([setup, emotion])
        session.commit()
        session.refresh(setup)
        session.refresh(emotion)
        return setup.id, emotion.id


def test_tos_preview_detects_single_completed_trade_and_persists_batch(tmp_path: Path) -> None:
    csv_text = dedent(
        """
        Account Statement

        Account Trade History
        ,Exec Time,Spread,Side,Qty,Pos Effect,Symbol,Exp,Strike,Type,Price
        ,02/21/26 09:35:00,SINGLE,BUY,+1,TO OPEN,NVDA,02/21/26,500,CALL,1.00
        ,02/21/26 10:05:00,SINGLE,SELL,-1,TO CLOSE,NVDA,02/21/26,500,CALL,1.40

        Cash & Sweep Vehicle
        """
    ).strip()
    expected_file_hash = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()

    client, testing_session_local = _build_client(tmp_path, "test_tos_preview_single_trade.db")
    try:
        with client:
            response = _post_preview_csv(client, csv_text)
            assert response.status_code == 200
            body = response.json()

            assert isinstance(body["batch_id"], int)
            detected_trades = body["detected_trades"]
            warnings = body["warnings"]
            assert len(detected_trades) == 1
            assert warnings == []

            trade = detected_trades[0]
            assert trade["temp_id"]
            assert trade["date"] == "2026-02-21"
            assert trade["symbol"] == "NVDA"
            assert trade["option_type"] == "CALL"
            assert trade["entry_fills_count"] == 1
            assert trade["exit_fills_count"] == 1
            assert trade["total_entry_qty"] == 1
            assert trade["total_exit_qty"] == 1
            assert trade["matched_qty"] == 1
            assert trade["avg_entry_price"] == 1.0
            assert trade["avg_exit_price"] == 1.4
            assert trade["is_partial"] is False
            assert len(trade["fills"]) == 2
            assert trade["fills"][0]["side"] == "BUY"
            assert trade["fills"][1]["side"] == "SELL"
            assert trade["ticker"] == "NVDA"
            assert trade["direction"] == "CALL"
            assert trade["quantity"] == 1
            assert trade["entry_time"] == "09:35:00"
            assert trade["exit_time"] == "10:05:00"
            assert trade["entry_price"] == 1.0
            assert trade["exit_price"] == 1.4
            assert trade["duration_seconds"] == 1800
            assert trade["total_pnl_usd"] == 40.0
            assert trade["exp"] == "02/21/26"
            assert trade["strike"] == 500.0
            assert trade["duplicate_status"] == "new"
            assert trade["duplicate_reason"] is None
            assert trade["existing_trade_id"] is None

            with testing_session_local() as session:
                batch = session.scalar(
                    select(ImportBatch).where(ImportBatch.id == body["batch_id"])
                )

            assert batch is not None
            assert batch.source == "tos_csv"
            assert batch.original_filename == "statement.csv"
            assert batch.file_hash == expected_file_hash
            assert batch.status == ImportBatchStatus.PREVIEWED
            assert batch.parsed_rows_count == len(csv_text.splitlines())
            assert batch.fills_parsed_count == 2
            assert batch.detected_trades_count == 1
            assert batch.matched_pairs_count == 1
            assert batch.unmatched_opens_count == 0
            assert batch.unmatched_closes_count == 0
            assert batch.excluded_count == 0
            assert json.loads(batch.warnings_json or "[]") == []
            assert json.loads(batch.commit_errors_json or "[]") == []
    finally:
        app.dependency_overrides.clear()


def test_tos_preview_marks_existing_saved_trade_as_duplicate(tmp_path: Path) -> None:
    csv_text = dedent(
        """
        Account Statement

        Account Trade History
        ,Exec Time,Spread,Side,Qty,Pos Effect,Symbol,Exp,Strike,Type,Price
        ,02/21/26 09:35:00,SINGLE,BUY,+1,TO OPEN,NVDA,02/21/26,500,CALL,1.00
        ,02/21/26 10:05:00,SINGLE,SELL,-1,TO CLOSE,NVDA,02/21/26,500,CALL,1.40

        Cash & Sweep Vehicle
        """
    ).strip()

    client, testing_session_local = _build_client(tmp_path, "test_tos_preview_duplicate_saved.db")
    setup_id, emotion_id = _seed_trade_dependencies(testing_session_local)
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
                setup_id=setup_id,
                emotion_id=emotion_id,
                rule_followed=True,
                entry_time=datetime.strptime("09:35:00", "%H:%M:%S").time(),
                exit_time=datetime.strptime("10:05:00", "%H:%M:%S").time(),
                duration_seconds=1800,
                source="manual",
                source_id=None,
            )
            session.add(existing_trade)
            session.commit()
            session.refresh(existing_trade)
            existing_trade_id = existing_trade.id

        with client:
            response = _post_preview_csv(client, csv_text)
            assert response.status_code == 200
            trade = response.json()["detected_trades"][0]
            assert trade["duplicate_status"] == "duplicate"
            assert trade["existing_trade_id"] == existing_trade_id
            assert "already appears to exist in your journal" in trade["duplicate_reason"]
    finally:
        app.dependency_overrides.clear()


def test_tos_preview_marks_duplicate_rows_within_same_csv(tmp_path: Path) -> None:
    csv_text = "Account Statement\n\nAccount Trade History\n"

    def _fake_preview(_: str):
        trade_a = DetectedTradePreview(
            temp_id="preview-a",
            date="2026-02-21",
            symbol="NVDA",
            exp="02/21/26",
            strike=500.0,
            option_type="CALL",
            entry_fills_count=1,
            exit_fills_count=1,
            total_entry_qty=1,
            total_exit_qty=1,
            matched_qty=1,
            avg_entry_price=1.0,
            avg_exit_price=1.4,
            is_partial=False,
            fills=[
                DetectedTradePreviewFill(
                    side="BUY", qty=1, price=1.0, exec_datetime="2026-02-21T09:35:00"
                ),
                DetectedTradePreviewFill(
                    side="SELL", qty=1, price=1.4, exec_datetime="2026-02-21T10:05:00"
                ),
            ],
            ticker="NVDA",
            direction="CALL",
            quantity=1,
            entry_time="09:35:00",
            exit_time="10:05:00",
            entry_price=1.0,
            exit_price=1.4,
            duration_seconds=1800,
            total_pnl_usd=40.0,
        )
        trade_b = trade_a.model_copy(update={"temp_id": "preview-b"})
        return ([trade_a, trade_b], [], 2, [], [], [])

    client, _ = _build_client(tmp_path, "test_tos_preview_duplicate_csv.db")
    try:
        with client:
            original_parser = import_tos_router.preview_tos_statement_with_metrics
            import_tos_router.preview_tos_statement_with_metrics = _fake_preview
            try:
                response = _post_preview_csv(client, csv_text)
            finally:
                import_tos_router.preview_tos_statement_with_metrics = original_parser

            assert response.status_code == 200
            trades = response.json()["detected_trades"]
            assert trades[0]["duplicate_status"] == "new"
            assert trades[1]["duplicate_status"] == "duplicate"
            assert (
                trades[1]["duplicate_reason"]
                == "Duplicate: matches another detected trade in this CSV."
            )
    finally:
        app.dependency_overrides.clear()


def test_tos_preview_groups_scaled_fills_and_computes_weighted_pnl(tmp_path: Path) -> None:
    csv_text = dedent(
        """
        Account Statement

        Account Trade History
        ,Exec Time,Spread,Side,Qty,Pos Effect,Symbol,Exp,Strike,Type,Price
        ,02/21/26 09:30:00,SINGLE,BUY,+1,TO OPEN,NVDA,02/21/26,500,CALL,1.00
        ,02/21/26 09:35:00,SINGLE,BUY,+1,TO OPEN,NVDA,02/21/26,500,CALL,1.20
        ,02/21/26 09:50:00,SINGLE,SELL,-1,TO CLOSE,NVDA,02/21/26,500,CALL,1.40
        ,02/21/26 10:00:00,SINGLE,SELL,-1,TO CLOSE,NVDA,02/21/26,500,CALL,1.60

        Cash & Sweep Vehicle
        """
    ).strip()

    client, _ = _build_client(tmp_path, "test_tos_preview_scaled_group.db")
    try:
        with client:
            response = _post_preview_csv(client, csv_text)
            assert response.status_code == 200
            body = response.json()
            assert body["warnings"] == []
            assert len(body["detected_trades"]) == 1

            trade = body["detected_trades"][0]
            assert trade["entry_fills_count"] == 2
            assert trade["exit_fills_count"] == 2
            assert trade["total_entry_qty"] == 2
            assert trade["total_exit_qty"] == 2
            assert trade["matched_qty"] == 2
            assert trade["avg_entry_price"] == 1.1
            assert trade["avg_exit_price"] == 1.5
            assert trade["total_pnl_usd"] == 80.0
            assert trade["duration_seconds"] == 1800
            assert trade["is_partial"] is False
            assert [fill["side"] for fill in trade["fills"]] == ["BUY", "BUY", "SELL", "SELL"]
    finally:
        app.dependency_overrides.clear()


def test_tos_preview_flags_partial_group_when_exit_qty_less_than_entry_qty(tmp_path: Path) -> None:
    csv_text = dedent(
        """
        Account Statement

        Account Trade History
        ,Exec Time,Spread,Side,Qty,Pos Effect,Symbol,Exp,Strike,Type,Price
        ,02/21/26 09:30:00,SINGLE,BUY,+1,TO OPEN,NVDA,02/21/26,500,CALL,1.00
        ,02/21/26 09:35:00,SINGLE,BUY,+1,TO OPEN,NVDA,02/21/26,500,CALL,1.20
        ,02/21/26 09:50:00,SINGLE,SELL,-1,TO CLOSE,NVDA,02/21/26,500,CALL,1.30

        Cash & Sweep Vehicle
        """
    ).strip()

    client, _ = _build_client(tmp_path, "test_tos_preview_partial_group.db")
    try:
        with client:
            response = _post_preview_csv(client, csv_text)
            assert response.status_code == 200
            body = response.json()
            assert len(body["detected_trades"]) == 1

            trade = body["detected_trades"][0]
            assert trade["total_entry_qty"] == 2
            assert trade["total_exit_qty"] == 1
            assert trade["matched_qty"] == 1
            assert trade["is_partial"] is True
            assert trade["total_pnl_usd"] == 30.0
            assert any("Partial grouped trade detected" in warning for warning in body["warnings"])
    finally:
        app.dependency_overrides.clear()


def test_tos_preview_warns_on_unmatched_open_fill_and_persists_batch_metrics(
    tmp_path: Path,
) -> None:
    csv_text = dedent(
        """
        Account Statement

        Account Trade History
        ,Exec Time,Spread,Side,Qty,Pos Effect,Symbol,Exp,Strike,Type,Price
        ,02/21/26 09:35:00,SINGLE,BUY,+1,TO OPEN,NVDA,02/21/26,500,CALL,1.00

        Cash & Sweep Vehicle
        """
    ).strip()

    client, testing_session_local = _build_client(tmp_path, "test_tos_preview_unmatched_open.db")
    try:
        with client:
            response = _post_preview_csv(client, csv_text)

            assert response.status_code == 200
            body = response.json()
            assert isinstance(body["batch_id"], int)
            assert body["detected_trades"] == []
            assert any("Unmatched open fill" in warning for warning in body["warnings"])

            with testing_session_local() as session:
                batch = session.scalar(
                    select(ImportBatch).where(ImportBatch.id == body["batch_id"])
                )

            assert batch is not None
            assert batch.status == ImportBatchStatus.PREVIEWED
            assert batch.parsed_rows_count == len(csv_text.splitlines())
            assert batch.fills_parsed_count == 1
            assert batch.detected_trades_count == 0
            assert batch.matched_pairs_count == 0
            assert batch.unmatched_opens_count == 1
            assert batch.unmatched_closes_count == 0
            stored_warnings = json.loads(batch.warnings_json or "[]")
            assert any("Unmatched open fill" in warning for warning in stored_warnings)
            stored_fills = json.loads(batch.fills_json or "[]")
            assert len(stored_fills) == 1
            assert stored_fills[0]["pos_effect"] == "TO OPEN"
            unmatched_opens = json.loads(batch.unmatched_opens_json or "[]")
            assert len(unmatched_opens) == 1
            assert unmatched_opens[0]["symbol"] == "NVDA"
            unmatched_closes = json.loads(batch.unmatched_closes_json or "[]")
            assert unmatched_closes == []
            committed_trade_count = session.execute(
                select(func.count()).select_from(Trade)
            ).scalar_one()
            assert committed_trade_count == 0
    finally:
        app.dependency_overrides.clear()


def test_tos_preview_warns_on_unmatched_close_fill_and_persists_batch_metrics(
    tmp_path: Path,
) -> None:
    csv_text = dedent(
        """
        Account Statement

        Account Trade History
        ,Exec Time,Spread,Side,Qty,Pos Effect,Symbol,Exp,Strike,Type,Price
        ,02/21/26 10:05:00,SINGLE,SELL,-1,TO CLOSE,NVDA,02/21/26,500,CALL,1.40

        Cash & Sweep Vehicle
        """
    ).strip()

    client, testing_session_local = _build_client(tmp_path, "test_tos_preview_unmatched_close.db")
    try:
        with client:
            response = _post_preview_csv(client, csv_text)

            assert response.status_code == 200
            body = response.json()
            assert isinstance(body["batch_id"], int)
            assert body["detected_trades"] == []
            assert any(
                "Close fill without matching open" in warning for warning in body["warnings"]
            )

            with testing_session_local() as session:
                batch = session.scalar(
                    select(ImportBatch).where(ImportBatch.id == body["batch_id"])
                )

                assert batch is not None
                assert batch.status == ImportBatchStatus.PREVIEWED
                assert batch.parsed_rows_count == len(csv_text.splitlines())
                assert batch.fills_parsed_count == 1
                assert batch.detected_trades_count == 0
                assert batch.matched_pairs_count == 0
                assert batch.unmatched_opens_count == 0
                assert batch.unmatched_closes_count == 1
                stored_warnings = json.loads(batch.warnings_json or "[]")
                assert any(
                    "Close fill without matching open" in warning for warning in stored_warnings
                )
                stored_fills = json.loads(batch.fills_json or "[]")
                assert len(stored_fills) == 1
                assert stored_fills[0]["pos_effect"] == "TO CLOSE"
                unmatched_opens = json.loads(batch.unmatched_opens_json or "[]")
                assert unmatched_opens == []
                unmatched_closes = json.loads(batch.unmatched_closes_json or "[]")
                assert len(unmatched_closes) == 1
                assert unmatched_closes[0]["symbol"] == "NVDA"
                committed_trade_count = session.execute(
                    select(func.count()).select_from(Trade)
                ).scalar_one()
                assert committed_trade_count == 0
    finally:
        app.dependency_overrides.clear()


def test_tos_preview_parse_failure_creates_failed_batch(tmp_path: Path) -> None:
    csv_text = dedent(
        """
        Account Statement

        Account Trade History
        ,Exec Time,Spread,Side,Qty,Pos Effect,Symbol,Exp,Strike,Type,Price
        ,02/21/26 09:35:00,SINGLE,BUY,+1,TO OPEN,NVDA,02/21/26,500,CALL,1.00
        """
    ).strip()

    def _raise_parse_error(_: str) -> tuple[list, list[str], int]:
        raise RuntimeError("forced preview failure for test")

    client, testing_session_local = _build_client(tmp_path, "test_tos_preview_parse_failure.db")
    try:
        with client:
            original_parser = import_tos_router.preview_tos_statement_with_metrics
            import_tos_router.preview_tos_statement_with_metrics = _raise_parse_error
            try:
                response = _post_preview_csv(client, csv_text)
            finally:
                import_tos_router.preview_tos_statement_with_metrics = original_parser

            assert response.status_code == 200
            body = response.json()
            assert isinstance(body["batch_id"], int)
            assert body["detected_trades"] == []
            assert body["warnings"] == [
                "Failed to parse uploaded statement. Please verify CSV format."
            ]

            with testing_session_local() as session:
                batch = session.scalar(
                    select(ImportBatch).where(ImportBatch.id == body["batch_id"])
                )

            assert batch is not None
            assert batch.status == ImportBatchStatus.FAILED
            assert batch.parsed_rows_count == len(csv_text.splitlines())
            assert batch.fills_parsed_count == 0
            assert batch.detected_trades_count == 0
            assert batch.matched_pairs_count == 0
            assert batch.unmatched_opens_count == 0
            assert batch.unmatched_closes_count == 0
            assert "forced preview failure for test" in (batch.commit_errors_json or "")
    finally:
        app.dependency_overrides.clear()
