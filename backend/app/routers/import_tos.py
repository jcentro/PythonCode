import hashlib
import json
from datetime import date, datetime, time
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.emotion_option import EmotionOption
from app.models.import_batch import ImportBatch, ImportBatchStatus
from app.models.setup_option import SetupOption
from app.models.trade import Trade, TradeDirection
from app.models.trade_fill import TradeFill, TradeFillSide
from app.schemas.import_preview import (
    DetectedTradePreview,
    DetectedTradePreviewFill,
    ToSCommitRequest,
    ToSCommitResponse,
    ToSPreviewResponse,
)
from app.services.tos_import import (
    cache_detected_trades,
    get_cached_detected_trade,
    get_detected_trade_from_batch_fills,
    preview_tos_statement_with_metrics,
)
from app.services.trade_computation import compute_trade_summary

router = APIRouter(prefix="/api/import/tos", tags=["import"])
TOS_CSV_SOURCE = "tos_csv"
MAX_BATCH_MESSAGE_ITEMS = 100
MAX_BATCH_MESSAGE_CHARS = 500
MAX_BATCH_FILLS_ITEMS = 200
DuplicateStatus = Literal["new", "duplicate", "possible_duplicate"]


def _serialize_messages(messages: list[str]) -> str:
    compact_messages = [
        message[:MAX_BATCH_MESSAGE_CHARS] for message in messages[:MAX_BATCH_MESSAGE_ITEMS]
    ]
    if len(messages) > MAX_BATCH_MESSAGE_ITEMS:
        compact_messages.append(
            f"... truncated {len(messages) - MAX_BATCH_MESSAGE_ITEMS} additional messages ..."
        )
    return json.dumps(compact_messages)


def _serialize_json_items(items: list[object] | None) -> str | None:
    if items is None:
        return None
    return json.dumps(items)


def _create_preview_batch(
    db: Session,
    *,
    source: str,
    original_filename: str | None,
    file_hash: str | None,
    status: ImportBatchStatus,
    parsed_rows_count: int,
    fills_parsed_count: int,
    detected_trades_count: int,
    matched_pairs_count: int,
    unmatched_opens_count: int,
    unmatched_closes_count: int,
    excluded_count: int,
    warnings: list[str],
    fills: list[dict[str, str | int | float]] | None = None,
    unmatched_opens: list[dict[str, str | int | float]] | None = None,
    unmatched_closes: list[dict[str, str | int | float]] | None = None,
    commit_errors: list[str] | None = None,
) -> ImportBatch:
    batch = ImportBatch(
        source=source,
        original_filename=original_filename,
        file_hash=file_hash,
        status=status,
        parsed_rows_count=parsed_rows_count,
        fills_parsed_count=fills_parsed_count,
        detected_trades_count=detected_trades_count,
        matched_pairs_count=matched_pairs_count,
        unmatched_opens_count=unmatched_opens_count,
        unmatched_closes_count=unmatched_closes_count,
        excluded_count=excluded_count,
        warnings_json=_serialize_messages(warnings),
        fills_json=_serialize_json_items(fills),
        unmatched_opens_json=_serialize_json_items(unmatched_opens),
        unmatched_closes_json=_serialize_json_items(unmatched_closes),
        commit_errors_json=_serialize_messages(commit_errors or []),
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def _update_commit_batch(
    db: Session,
    *,
    batch: ImportBatch,
    imported: int,
    skipped_duplicates: int,
    errors: list[str],
) -> None:
    batch.committed_count = imported
    batch.skipped_duplicates_count = skipped_duplicates
    batch.commit_errors_json = _serialize_messages(errors)
    batch.status = ImportBatchStatus.FAILED if errors else ImportBatchStatus.COMMITTED
    db.add(batch)


@router.post("/preview", response_model=ToSPreviewResponse)
async def preview_tos_import(
    file: UploadFile = File(...), db: Session = Depends(get_db)
) -> ToSPreviewResponse:
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File upload is required.",
        )

    raw_content = await file.read()
    file_hash = hashlib.sha256(raw_content).hexdigest() if raw_content else None
    if not raw_content:
        warnings = ["Uploaded file is empty."]
        batch = _create_preview_batch(
            db,
            source=TOS_CSV_SOURCE,
            original_filename=file.filename,
            file_hash=file_hash,
            status=ImportBatchStatus.PREVIEWED,
            parsed_rows_count=0,
            fills_parsed_count=0,
            detected_trades_count=0,
            matched_pairs_count=0,
            unmatched_opens_count=0,
            unmatched_closes_count=0,
            excluded_count=0,
            warnings=warnings,
            fills=[],
            unmatched_opens=[],
            unmatched_closes=[],
        )
        return ToSPreviewResponse(batch_id=batch.id, detected_trades=[], warnings=warnings)

    try:
        csv_text = raw_content.decode("utf-8-sig")
    except UnicodeDecodeError:
        csv_text = raw_content.decode("latin-1")
    parsed_rows_count = len(csv_text.splitlines())

    try:
        (
            detected_trades,
            warnings,
            fills_parsed_count,
            trimmed_fills,
            unmatched_opens,
            unmatched_closes,
        ) = preview_tos_statement_with_metrics(csv_text)
    except Exception as exc:
        warnings = ["Failed to parse uploaded statement. Please verify CSV format."]
        batch = _create_preview_batch(
            db,
            source=TOS_CSV_SOURCE,
            original_filename=file.filename,
            file_hash=file_hash,
            status=ImportBatchStatus.FAILED,
            parsed_rows_count=parsed_rows_count,
            fills_parsed_count=0,
            detected_trades_count=0,
            matched_pairs_count=0,
            unmatched_opens_count=0,
            unmatched_closes_count=0,
            excluded_count=0,
            warnings=warnings,
            fills=[],
            unmatched_opens=[],
            unmatched_closes=[],
            commit_errors=[f"Preview parse failed: {exc!s}"],
        )
        return ToSPreviewResponse(batch_id=batch.id, detected_trades=[], warnings=warnings)

    stored_fills = trimmed_fills
    if len(trimmed_fills) > MAX_BATCH_FILLS_ITEMS:
        stored_fills = trimmed_fills[:MAX_BATCH_FILLS_ITEMS]
        warnings.append(
            "Stored first "
            f"{MAX_BATCH_FILLS_ITEMS} fills in batch detail. "
            f"{len(trimmed_fills) - MAX_BATCH_FILLS_ITEMS} additional fills were omitted."
        )

    detected_trades = _annotate_preview_duplicates(db, detected_trades)
    cache_detected_trades(detected_trades)
    batch = _create_preview_batch(
        db,
        source=TOS_CSV_SOURCE,
        original_filename=file.filename,
        file_hash=file_hash,
        status=ImportBatchStatus.PREVIEWED,
        parsed_rows_count=parsed_rows_count,
        fills_parsed_count=fills_parsed_count,
        detected_trades_count=len(detected_trades),
        matched_pairs_count=len(detected_trades),
        unmatched_opens_count=len(unmatched_opens),
        unmatched_closes_count=len(unmatched_closes),
        excluded_count=0,
        warnings=warnings,
        fills=stored_fills,
        unmatched_opens=unmatched_opens,
        unmatched_closes=unmatched_closes,
    )
    return ToSPreviewResponse(batch_id=batch.id, detected_trades=detected_trades, warnings=warnings)


def _get_default_setup_id(db: Session) -> int | None:
    other_id = db.execute(
        select(SetupOption.id).where(SetupOption.name == "OTHER")
    ).scalar_one_or_none()
    if other_id is not None:
        return int(other_id)

    first_id = db.execute(
        select(SetupOption.id).order_by(SetupOption.id.asc())
    ).scalar_one_or_none()
    return int(first_id) if first_id is not None else None


def _get_default_emotion_id(db: Session) -> int | None:
    other_id = db.execute(
        select(EmotionOption.id).where(EmotionOption.name == "OTHER")
    ).scalar_one_or_none()
    if other_id is not None:
        return int(other_id)

    first_id = db.execute(
        select(EmotionOption.id).order_by(EmotionOption.id.asc())
    ).scalar_one_or_none()
    return int(first_id) if first_id is not None else None


def _format_signature_float(value: float, decimals: int) -> str:
    return f"{round(float(value), decimals):.{decimals}f}"


def _normalize_time_value(value: time | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    return value.strip()


def _build_preview_duplicate_signature(preview_trade: DetectedTradePreview) -> str:
    quantity = (
        preview_trade.matched_qty if preview_trade.matched_qty > 0 else preview_trade.quantity
    )
    return "|".join(
        [
            preview_trade.date,
            _normalize_time_value(preview_trade.entry_time),
            preview_trade.symbol.strip().upper(),
            preview_trade.option_type,
            str(quantity),
            _format_signature_float(preview_trade.entry_price, 4),
            _format_signature_float(preview_trade.exit_price, 4),
            _format_signature_float(preview_trade.total_pnl_usd, 2),
        ]
    )


def _build_trade_duplicate_signature(trade: Trade) -> str:
    return "|".join(
        [
            trade.date.isoformat(),
            _normalize_time_value(trade.entry_time),
            trade.ticker.strip().upper(),
            trade.direction.value,
            str(trade.quantity),
            _format_signature_float(trade.entry_price, 4),
            _format_signature_float(trade.exit_price, 4),
            _format_signature_float(trade.total_pnl_usd, 2),
        ]
    )


def _build_existing_trade_duplicate_maps(
    db: Session,
) -> tuple[dict[str, Trade], dict[str, Trade]]:
    trades = list(db.scalars(select(Trade)).all())
    source_id_map: dict[str, Trade] = {}
    signature_map: dict[str, Trade] = {}

    for trade in trades:
        if (
            trade.source == TOS_CSV_SOURCE
            and trade.source_id
            and trade.source_id not in source_id_map
        ):
            source_id_map[trade.source_id] = trade

        signature = _build_trade_duplicate_signature(trade)
        if signature not in signature_map:
            signature_map[signature] = trade

    return source_id_map, signature_map


def _annotate_preview_duplicates(
    db: Session, detected_trades: list[DetectedTradePreview]
) -> list[DetectedTradePreview]:
    source_id_map, signature_map = _build_existing_trade_duplicate_maps(db)
    seen_temp_ids: set[str] = set()
    seen_signatures: set[str] = set()
    annotated_trades: list[DetectedTradePreview] = []

    for trade in detected_trades:
        duplicate_status: DuplicateStatus = "new"
        duplicate_reason: str | None = None
        existing_trade_id: int | None = None
        signature = _build_preview_duplicate_signature(trade)

        if trade.temp_id in source_id_map:
            duplicate_status = "duplicate"
            duplicate_reason = (
                "Duplicate: already appears to exist in your journal (exact import match)."
            )
            existing_trade_id = source_id_map[trade.temp_id].id
        elif signature in signature_map:
            duplicate_status = "duplicate"
            duplicate_reason = (
                "Duplicate: already appears to exist in your journal "
                "(matching date/time, ticker, prices, quantity, and PnL)."
            )
            existing_trade_id = signature_map[signature].id
        elif trade.temp_id in seen_temp_ids or signature in seen_signatures:
            duplicate_status = "duplicate"
            duplicate_reason = "Duplicate: matches another detected trade in this CSV."

        annotated_trades.append(
            trade.model_copy(
                update={
                    "duplicate_status": duplicate_status,
                    "duplicate_reason": duplicate_reason,
                    "existing_trade_id": existing_trade_id,
                }
            )
        )
        seen_temp_ids.add(trade.temp_id)
        seen_signatures.add(signature)

    return annotated_trades


def _parse_hhmmss_or_none(value: str | None) -> time | None:
    if not value:
        return None

    parts = value.split(":")
    if len(parts) != 3:
        return None

    try:
        hour = int(parts[0])
        minute = int(parts[1])
        second = int(parts[2])
        return time(hour=hour, minute=minute, second=second)
    except ValueError:
        return None


def _parse_iso_datetime_or_none(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _build_fill_source_id(temp_id: str, fill: DetectedTradePreviewFill) -> str:
    raw = "|".join(
        [
            temp_id,
            fill.exec_datetime,
            fill.side,
            str(fill.qty),
            f"{fill.price:.8f}",
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


def _load_preview_trade_from_batch(batch: ImportBatch, temp_id: str) -> DetectedTradePreview | None:
    preview_trade, _ = get_detected_trade_from_batch_fills(batch.fills_json, temp_id)
    if preview_trade is not None:
        return preview_trade
    return get_cached_detected_trade(temp_id)


@router.post("/commit", response_model=ToSCommitResponse)
def commit_tos_import(
    payload: ToSCommitRequest, db: Session = Depends(get_db)
) -> ToSCommitResponse:
    imported = 0
    skipped_duplicates = 0
    errors: list[str] = []
    pending_source_ids: set[str] = set()
    pending_signatures: set[str] = set()

    batch = db.get(ImportBatch, payload.batch_id)
    if batch is None:
        return ToSCommitResponse(
            imported=0,
            skipped_duplicates=0,
            errors=[f"Import batch not found: {payload.batch_id}"],
        )
    if batch.source != TOS_CSV_SOURCE:
        return ToSCommitResponse(
            imported=0,
            skipped_duplicates=0,
            errors=[f"Import batch source mismatch for batch_id={payload.batch_id}"],
        )

    default_setup_id = _get_default_setup_id(db)
    default_emotion_id = _get_default_emotion_id(db)
    existing_source_id_map, existing_signature_map = _build_existing_trade_duplicate_maps(db)

    if default_setup_id is None:
        errors.append("No setup options exist. Create at least one setup before importing.")
    if default_emotion_id is None:
        errors.append("No emotion options exist. Create at least one emotion before importing.")
    if errors:
        _update_commit_batch(
            db,
            batch=batch,
            imported=0,
            skipped_duplicates=0,
            errors=errors,
        )
        db.commit()
        return ToSCommitResponse(imported=0, skipped_duplicates=0, errors=errors)

    for item in payload.items:
        preview_trade = _load_preview_trade_from_batch(batch, item.temp_id)
        if preview_trade is None:
            errors.append(f"Preview trade not found for temp_id={item.temp_id}")
            continue

        preview_signature = _build_preview_duplicate_signature(preview_trade)
        if (
            item.temp_id in pending_source_ids
            or item.temp_id in existing_source_id_map
            or preview_signature in pending_signatures
            or preview_signature in existing_signature_map
        ):
            skipped_duplicates += 1
            continue

        setup_id = item.setup_id if item.setup_id is not None else default_setup_id
        emotion_id = item.emotion_id if item.emotion_id is not None else default_emotion_id

        setup_option = db.get(SetupOption, setup_id)
        if setup_option is None:
            errors.append(f"Invalid setup_id for temp_id={item.temp_id}: {setup_id}")
            continue

        emotion_option = db.get(EmotionOption, emotion_id)
        if emotion_option is None:
            errors.append(f"Invalid emotion_id for temp_id={item.temp_id}: {emotion_id}")
            continue

        try:
            trade_date = date.fromisoformat(preview_trade.date)
        except ValueError:
            errors.append(f"Invalid preview date for temp_id={item.temp_id}: {preview_trade.date}")
            continue

        if not preview_trade.fills:
            errors.append(f"Preview trade has no fills for temp_id={item.temp_id}")
            continue

        try:
            direction = TradeDirection(preview_trade.option_type)
        except ValueError:
            errors.append(
                f"Invalid preview direction for temp_id={item.temp_id}: {preview_trade.option_type}"
            )
            continue

        trade_fill_rows: list[TradeFill] = []
        fill_times: list[datetime] = []
        invalid_fill = False
        for fill in preview_trade.fills:
            filled_at = _parse_iso_datetime_or_none(fill.exec_datetime)
            if filled_at is None:
                errors.append(
                    f"Invalid fill exec_datetime for temp_id={item.temp_id}: {fill.exec_datetime}"
                )
                invalid_fill = True
                break

            try:
                fill_side = TradeFillSide(fill.side)
            except ValueError:
                errors.append(f"Invalid fill side for temp_id={item.temp_id}: {fill.side}")
                invalid_fill = True
                break

            if fill.qty <= 0:
                errors.append(f"Invalid fill quantity for temp_id={item.temp_id}: {fill.qty}")
                invalid_fill = True
                break
            if fill.price < 0:
                errors.append(f"Invalid fill price for temp_id={item.temp_id}: {fill.price}")
                invalid_fill = True
                break

            trade_fill_rows.append(
                TradeFill(
                    side=fill_side,
                    quantity=fill.qty,
                    price=fill.price,
                    filled_at=filled_at,
                    source=TOS_CSV_SOURCE,
                    source_id=_build_fill_source_id(item.temp_id, fill),
                )
            )
            fill_times.append(filled_at)

        if invalid_fill:
            continue

        trade = Trade(
            date=trade_date,
            ticker=preview_trade.symbol.strip().upper(),
            direction=direction,
            entry_price=preview_trade.entry_price,
            exit_price=preview_trade.exit_price,
            pnl=preview_trade.exit_price - preview_trade.entry_price,
            quantity=preview_trade.matched_qty if preview_trade.matched_qty > 0 else 1,
            contract_multiplier=Trade.DEFAULT_CONTRACT_MULTIPLIER,
            total_pnl_usd=preview_trade.total_pnl_usd,
            setup_id=setup_option.id,
            emotion_id=emotion_option.id,
            rule_followed=item.rule_followed if item.rule_followed is not None else True,
            notes=item.notes,
            entry_time=_parse_hhmmss_or_none(preview_trade.entry_time),
            exit_time=_parse_hhmmss_or_none(preview_trade.exit_time),
            duration_seconds=preview_trade.duration_seconds,
            source=TOS_CSV_SOURCE,
            source_id=item.temp_id,
            import_batch_id=batch.id,
        )

        db.add(trade)
        db.flush()
        for fill_row in trade_fill_rows:
            fill_row.trade_id = trade.id
            db.add(fill_row)

        trade.entry_time = min(fill_times).time() if fill_times else trade.entry_time
        trade.exit_time = max(fill_times).time() if fill_times else trade.exit_time
        trade.fills = trade_fill_rows
        summary = compute_trade_summary(trade)
        trade.entry_price = summary.entry_price
        trade.exit_price = summary.exit_price
        trade.pnl = summary.pnl
        trade.quantity = summary.quantity if summary.quantity > 0 else 1
        trade.total_pnl_usd = summary.total_pnl_usd
        trade.duration_seconds = summary.duration_seconds
        pending_source_ids.add(item.temp_id)
        pending_signatures.add(preview_signature)
        imported += 1

    _update_commit_batch(
        db,
        batch=batch,
        imported=imported,
        skipped_duplicates=skipped_duplicates,
        errors=errors,
    )
    db.commit()
    return ToSCommitResponse(
        imported=imported,
        skipped_duplicates=skipped_duplicates,
        errors=errors,
    )
