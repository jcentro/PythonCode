import warnings
from datetime import date, datetime, time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models.emotion_option import EmotionOption
from app.models.setup_option import SetupOption
from app.models.trade import Trade
from app.models.trade_fill import TradeFill
from app.schemas.trade import (
    TradeBulkUpdateRequest,
    TradeBulkUpdateResponse,
    TradeCreate,
    TradeFillRead,
    TradeFillWrite,
    TradePatch,
    TradeRead,
)
from app.services.trade_computation import (
    compute_trade_summary,
    trade_total_pnl_usd,
)
from app.services.trade_validation import validate_trade_payload

router = APIRouter(prefix="/api/trades", tags=["trades"])

def _get_setup_option_or_422(db: Session, setup_id: int) -> SetupOption:
    setup_option = db.get(SetupOption, setup_id)
    if setup_option is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid setup_id: {setup_id}",
        )
    return setup_option


def _compute_duration_seconds(entry_time: time | None, exit_time: time | None) -> int | None:
    if entry_time is None or exit_time is None:
        return None

    if exit_time < entry_time:
        warnings.warn(
            "exit_time is earlier than entry_time on the same trade date; "
            "duration_seconds set to null.",
            stacklevel=2,
        )
        return None

    entry_dt = datetime.combine(date.min, entry_time)
    exit_dt = datetime.combine(date.min, exit_time)
    return int((exit_dt - entry_dt).total_seconds())


def _unclassified_trade_filter():
    return or_(
        Trade.setup_id.is_(None),
        Trade.emotion_id.is_(None),
        Trade.rule_followed.is_(None),
    )


def _trade_total_pnl_usd(trade: Trade) -> float:
    return trade_total_pnl_usd(trade)


def _to_trade_read(trade: Trade, *, include_fills: bool) -> TradeRead:
    summary = compute_trade_summary(trade)
    fill_rows = None
    if include_fills:
        fill_rows = [TradeFillRead.model_validate(fill) for fill in (trade.fills or [])]

    return TradeRead(
        id=trade.id,
        date=trade.date,
        ticker=trade.ticker,
        direction=trade.direction,
        entry_price=summary.entry_price,
        exit_price=summary.exit_price,
        pnl=summary.pnl,
        quantity=summary.quantity,
        contract_multiplier=trade.contract_multiplier,
        total_pnl_usd=summary.total_pnl_usd,
        duration_seconds=summary.duration_seconds,
        total_entry_qty=summary.total_entry_qty,
        total_exit_qty=summary.total_exit_qty,
        avg_entry_price=summary.avg_entry_price,
        avg_exit_price=summary.avg_exit_price,
        realized_pnl_usd=summary.realized_pnl_usd,
        is_partial=summary.is_partial,
        use_fills=bool(trade.fills),
        fills=fill_rows,
        setup_id=trade.setup_id,
        setup_name=trade.setup_name,
        emotion_id=trade.emotion_id,
        emotion_name=trade.emotion_name,
        rule_followed=trade.rule_followed,
        notes=trade.notes,
        source=trade.source,
        source_id=trade.source_id,
        entry_time=trade.entry_time,
        exit_time=trade.exit_time,
    )


def _load_trade_or_404(db: Session, trade_id: int) -> Trade:
    trade = db.scalar(
        select(Trade)
        .options(
            selectinload(Trade.setup_option),
            selectinload(Trade.emotion_option),
            selectinload(Trade.fills),
        )
        .where(Trade.id == trade_id)
    )
    if trade is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")
    return trade


def _load_trade_fill_or_404(db: Session, trade_id: int, fill_id: int) -> TradeFill:
    fill = db.get(TradeFill, fill_id)
    if fill is None or fill.trade_id != trade_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade fill not found")
    return fill


def _trade_chronological_sort_key(trade: Trade) -> tuple[date, int, time, int]:
    return (
        trade.date,
        1 if trade.entry_time is None else 0,
        trade.entry_time or time.max,
        trade.id,
    )


def _apply_trade_index_bucket_filter(
    trades: list[Trade], trade_index_bucket: Literal["first_3", "after_3"]
) -> list[Trade]:
    allowed_ids: set[int] = set()
    trades_by_date: dict[date, list[Trade]] = {}
    for trade in trades:
        trades_by_date.setdefault(trade.date, []).append(trade)

    for day_trades in trades_by_date.values():
        sorted_day_trades = sorted(day_trades, key=_trade_chronological_sort_key)
        for trade_index, trade in enumerate(sorted_day_trades, start=1):
            if trade_index_bucket == "first_3" and trade_index <= 3:
                allowed_ids.add(trade.id)
            if trade_index_bucket == "after_3" and trade_index >= 4:
                allowed_ids.add(trade.id)

    return [trade for trade in trades if trade.id in allowed_ids]


def _apply_after_two_losses_pattern_filter(trades: list[Trade]) -> list[Trade]:
    sorted_trades = sorted(trades, key=_trade_chronological_sort_key)
    matching_ids: set[int] = set()
    for index in range(2, len(sorted_trades)):
        first_loss = _trade_total_pnl_usd(sorted_trades[index - 2]) < 0
        second_loss = _trade_total_pnl_usd(sorted_trades[index - 1]) < 0
        if first_loss and second_loss:
            matching_ids.add(sorted_trades[index].id)

    return [trade for trade in trades if trade.id in matching_ids]


def _assign_trade_fields(
    trade: Trade,
    payload: TradeCreate,
    *,
    normalized_ticker: str,
    preserve_existing_times_if_missing: bool = False,
    fill_summary=None,
) -> None:
    provided_fields = payload.model_fields_set
    timing_fields = {"entry_time", "exit_time", "duration_seconds"}
    timing_fields_provided = bool(provided_fields & timing_fields)

    trade.date = payload.date
    trade.ticker = normalized_ticker
    trade.direction = payload.direction
    if fill_summary is not None:
        trade.entry_price = fill_summary.avg_entry_price
        trade.exit_price = fill_summary.avg_exit_price
        trade.pnl = round(fill_summary.avg_exit_price - fill_summary.avg_entry_price, 4)
        trade.quantity = fill_summary.total_entry_qty
    else:
        trade.entry_price = payload.entry_price
        trade.exit_price = payload.exit_price
        trade.pnl = (
            payload.pnl if payload.pnl is not None else payload.exit_price - payload.entry_price
        )
        trade.quantity = payload.quantity
    trade.contract_multiplier = Trade.DEFAULT_CONTRACT_MULTIPLIER
    if fill_summary is not None:
        trade.total_pnl_usd = fill_summary.realized_pnl_usd
    else:
        trade.total_pnl_usd = trade.pnl * trade.quantity * trade.contract_multiplier
    trade.rule_followed = payload.rule_followed
    trade.notes = payload.notes

    if not preserve_existing_times_if_missing or timing_fields_provided:
        trade.entry_time = payload.entry_time
        trade.exit_time = payload.exit_time

        if "duration_seconds" in provided_fields:
            trade.duration_seconds = payload.duration_seconds
        elif fill_summary is not None and fill_summary.duration_seconds is not None:
            trade.duration_seconds = fill_summary.duration_seconds
        else:
            trade.duration_seconds = _compute_duration_seconds(
                payload.entry_time, payload.exit_time
            )
    elif trade.duration_seconds is None:
        trade.duration_seconds = _compute_duration_seconds(trade.entry_time, trade.exit_time)


def _get_emotion_option_or_422(db: Session, emotion_id: int) -> EmotionOption:
    emotion_option = db.get(EmotionOption, emotion_id)
    if emotion_option is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid emotion_id: {emotion_id}",
        )
    return emotion_option


def _assign_trade_relations(
    trade: Trade,
    setup_option: SetupOption | None,
    emotion_option: EmotionOption | None,
) -> None:
    if setup_option is None:
        trade.setup_id = None
        trade.setup_option = None
    else:
        trade.setup_id = setup_option.id
        trade.setup_option = setup_option

    if emotion_option is None:
        trade.emotion_id = None
        trade.emotion_option = None
    else:
        trade.emotion_id = emotion_option.id
        trade.emotion_option = emotion_option

def _replace_trade_fills(trade: Trade, fills: list[TradeFillWrite]) -> None:
    trade.fills.clear()
    for fill in fills:
        trade.fills.append(
            TradeFill(
                side=fill.side,
                quantity=fill.quantity,
                price=fill.price,
                filled_at=fill.filled_at,
                source="manual",
            )
        )


@router.post("", response_model=TradeRead, status_code=status.HTTP_201_CREATED)
def create_trade(payload: TradeCreate, db: Session = Depends(get_db)) -> Trade:
    trade = Trade()
    setup_option = _get_setup_option_or_422(db, payload.setup_id) if payload.setup_id else None
    emotion_option = (
        _get_emotion_option_or_422(db, payload.emotion_id) if payload.emotion_id else None
    )
    validation = validate_trade_payload(payload)
    _assign_trade_fields(
        trade,
        payload,
        normalized_ticker=validation.normalized_ticker,
        fill_summary=validation.fill_summary,
    )
    _assign_trade_relations(trade, setup_option, emotion_option)
    if validation.fills:
        _replace_trade_fills(trade, validation.fills)
    db.add(trade)
    db.commit()
    trade = _load_trade_or_404(db, trade.id)
    return _to_trade_read(trade, include_fills=bool(validation.fills))


@router.get("", response_model=list[TradeRead])
def list_trades(
    date: date | None = Query(default=None),
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    ticker: str | None = Query(default=None),
    setup_id: int | None = Query(default=None, gt=0),
    emotion_id: int | None = Query(default=None, gt=0),
    rule_followed: Literal["true", "false", "unknown"] | None = Query(default=None),
    outcome: Literal["win", "loss", "breakeven"] | None = Query(default=None),
    source: Literal["tos_csv", "manual"] | None = Query(default=None),
    import_batch_id: int | None = Query(default=None, gt=0),
    classification: Literal["all", "unclassified", "classified"] | None = Query(default=None),
    entry_time_start_minute: int | None = Query(default=None, ge=0, le=1439),
    entry_time_end_minute: int | None = Query(default=None, ge=1, le=1440),
    hold_time_min_seconds: int | None = Query(default=None, ge=0),
    hold_time_max_seconds: int | None = Query(default=None, ge=1),
    trade_index_bucket: Literal["first_3", "after_3"] | None = Query(default=None),
    pattern: Literal["after_2_losses_next_trade"] | None = Query(default=None),
    include_fills: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[TradeRead]:
    if start is not None and end is not None and start > end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start must be less than or equal to end",
        )
    if (
        entry_time_start_minute is not None
        and entry_time_end_minute is not None
        and entry_time_start_minute >= entry_time_end_minute
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="entry_time_start_minute must be less than entry_time_end_minute",
        )
    if (
        hold_time_min_seconds is not None
        and hold_time_max_seconds is not None
        and hold_time_min_seconds >= hold_time_max_seconds
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="hold_time_min_seconds must be less than hold_time_max_seconds",
        )

    stmt = (
        select(Trade)
        .options(
            selectinload(Trade.setup_option),
            selectinload(Trade.emotion_option),
            selectinload(Trade.fills),
        )
        .order_by(Trade.date.desc(), Trade.id.desc())
    )

    if date is not None:
        stmt = stmt.where(Trade.date == date)
    if start is not None:
        stmt = stmt.where(Trade.date >= start)
    if end is not None:
        stmt = stmt.where(Trade.date <= end)
    if ticker is not None and ticker.strip():
        stmt = stmt.where(Trade.ticker.ilike(f"%{ticker.strip()}%"))
    if setup_id is not None:
        stmt = stmt.where(Trade.setup_id == setup_id)
    if emotion_id is not None:
        stmt = stmt.where(Trade.emotion_id == emotion_id)
    if rule_followed == "true":
        stmt = stmt.where(Trade.rule_followed.is_(True))
    elif rule_followed == "false":
        stmt = stmt.where(Trade.rule_followed.is_(False))
    elif rule_followed == "unknown":
        stmt = stmt.where(Trade.rule_followed.is_(None))
    if source == "tos_csv":
        stmt = stmt.where(Trade.source == "tos_csv")
    elif source == "manual":
        stmt = stmt.where(or_(Trade.source.is_(None), Trade.source == "", Trade.source == "manual"))
    if import_batch_id is not None:
        stmt = stmt.where(Trade.import_batch_id == import_batch_id)
    if classification == "unclassified":
        stmt = stmt.where(_unclassified_trade_filter())
    elif classification == "classified":
        stmt = stmt.where(
            Trade.setup_id.is_not(None),
            Trade.emotion_id.is_not(None),
            Trade.rule_followed.is_not(None),
        )

    trades = list(db.scalars(stmt).all())

    if entry_time_start_minute is not None or entry_time_end_minute is not None:
        filtered: list[Trade] = []
        for trade in trades:
            if trade.entry_time is None:
                continue
            minutes_since_midnight = (trade.entry_time.hour * 60) + trade.entry_time.minute
            if (
                entry_time_start_minute is not None
                and minutes_since_midnight < entry_time_start_minute
            ):
                continue
            if (
                entry_time_end_minute is not None
                and minutes_since_midnight >= entry_time_end_minute
            ):
                continue
            filtered.append(trade)
        trades = filtered

    if hold_time_min_seconds is not None or hold_time_max_seconds is not None:
        filtered = []
        for trade in trades:
            if trade.duration_seconds is None:
                continue
            if hold_time_min_seconds is not None and trade.duration_seconds < hold_time_min_seconds:
                continue
            if (
                hold_time_max_seconds is not None
                and trade.duration_seconds >= hold_time_max_seconds
            ):
                continue
            filtered.append(trade)
        trades = filtered

    if outcome is not None:
        if outcome == "win":
            trades = [trade for trade in trades if _trade_total_pnl_usd(trade) > 0]
        elif outcome == "loss":
            trades = [trade for trade in trades if _trade_total_pnl_usd(trade) < 0]
        else:
            trades = [trade for trade in trades if _trade_total_pnl_usd(trade) == 0]

    if trade_index_bucket is not None:
        trades = _apply_trade_index_bucket_filter(trades, trade_index_bucket)

    if pattern == "after_2_losses_next_trade":
        trades = _apply_after_two_losses_pattern_filter(trades)

    return [_to_trade_read(trade, include_fills=include_fills) for trade in trades]


@router.get("/unclassified-count")
def get_unclassified_trades_count(db: Session = Depends(get_db)) -> dict[str, int]:
    count = db.scalar(select(func.count()).select_from(Trade).where(_unclassified_trade_filter()))
    return {"count": int(count or 0)}


@router.patch("/bulk", response_model=TradeBulkUpdateResponse)
def bulk_update_trades(
    payload: TradeBulkUpdateRequest, db: Session = Depends(get_db)
) -> TradeBulkUpdateResponse:
    update_fields = payload.model_fields_set - {"trade_ids"}
    if not update_fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one field must be provided for update.",
        )

    errors: list[str] = []
    updates: dict[str, int | bool | None] = {}

    if "setup_id" in update_fields:
        if payload.setup_id is None:
            errors.append("setup_id cannot be null.")
        else:
            setup_option = db.get(SetupOption, payload.setup_id)
            if setup_option is None:
                errors.append(f"Invalid setup_id: {payload.setup_id}")
            elif not setup_option.is_active:
                errors.append(f"Inactive setup_id: {payload.setup_id}")
            else:
                updates["setup_id"] = setup_option.id

    if "emotion_id" in update_fields:
        if payload.emotion_id is None:
            errors.append("emotion_id cannot be null.")
        else:
            emotion_option = db.get(EmotionOption, payload.emotion_id)
            if emotion_option is None:
                errors.append(f"Invalid emotion_id: {payload.emotion_id}")
            elif not emotion_option.is_active:
                errors.append(f"Inactive emotion_id: {payload.emotion_id}")
            else:
                updates["emotion_id"] = emotion_option.id

    if "rule_followed" in update_fields:
        updates["rule_followed"] = payload.rule_followed

    if not updates:
        return TradeBulkUpdateResponse(updated_count=0, errors=errors)

    requested_trade_ids = sorted(set(payload.trade_ids))
    trades = list(db.scalars(select(Trade).where(Trade.id.in_(requested_trade_ids))).all())
    found_ids = {trade.id for trade in trades}

    for trade_id in requested_trade_ids:
        if trade_id not in found_ids:
            errors.append(f"Trade not found: {trade_id}")

    for trade in trades:
        for field_name, field_value in updates.items():
            setattr(trade, field_name, field_value)

    if trades:
        db.commit()

    return TradeBulkUpdateResponse(updated_count=len(trades), errors=errors)


@router.post("/{trade_id}/fills", response_model=TradeRead, status_code=status.HTTP_201_CREATED)
def create_trade_fill(
    trade_id: int, payload: TradeFillWrite, db: Session = Depends(get_db)
) -> TradeRead:
    _load_trade_or_404(db, trade_id)

    fill = TradeFill(
        trade_id=trade_id,
        side=payload.side,
        quantity=payload.quantity,
        price=payload.price,
        filled_at=payload.filled_at,
        source="manual",
    )
    db.add(fill)
    db.commit()

    trade = _load_trade_or_404(db, trade_id)
    return _to_trade_read(trade, include_fills=True)


@router.put("/{trade_id}/fills/{fill_id}", response_model=TradeRead)
def update_trade_fill(
    trade_id: int, fill_id: int, payload: TradeFillWrite, db: Session = Depends(get_db)
) -> TradeRead:
    _load_trade_or_404(db, trade_id)
    fill = _load_trade_fill_or_404(db, trade_id, fill_id)

    fill.side = payload.side
    fill.quantity = payload.quantity
    fill.price = payload.price
    fill.filled_at = payload.filled_at
    db.commit()

    trade = _load_trade_or_404(db, trade_id)
    return _to_trade_read(trade, include_fills=True)


@router.delete("/{trade_id}/fills/{fill_id}", response_model=TradeRead)
def delete_trade_fill(trade_id: int, fill_id: int, db: Session = Depends(get_db)) -> TradeRead:
    _load_trade_or_404(db, trade_id)
    fill = _load_trade_fill_or_404(db, trade_id, fill_id)

    db.delete(fill)
    db.commit()

    trade = _load_trade_or_404(db, trade_id)
    return _to_trade_read(trade, include_fills=True)


@router.delete("/{trade_id}", response_model=TradeRead)
def delete_trade(trade_id: int, db: Session = Depends(get_db)) -> TradeRead:
    trade = _load_trade_or_404(db, trade_id)

    response = _to_trade_read(trade, include_fills=False)
    db.delete(trade)
    db.commit()
    return response


@router.put("/{trade_id}", response_model=TradeRead)
def update_trade(trade_id: int, payload: TradeCreate, db: Session = Depends(get_db)) -> Trade:
    trade = _load_trade_or_404(db, trade_id)

    setup_option = _get_setup_option_or_422(db, payload.setup_id) if payload.setup_id else None
    emotion_option = (
        _get_emotion_option_or_422(db, payload.emotion_id) if payload.emotion_id else None
    )
    validation = validate_trade_payload(payload)
    _assign_trade_fields(
        trade,
        payload,
        normalized_ticker=validation.normalized_ticker,
        preserve_existing_times_if_missing=True,
        fill_summary=validation.fill_summary,
    )
    _assign_trade_relations(trade, setup_option, emotion_option)
    if validation.fills:
        _replace_trade_fills(trade, validation.fills)
    elif payload.use_fills:
        trade.fills.clear()
    db.commit()
    trade = _load_trade_or_404(db, trade_id)
    return _to_trade_read(trade, include_fills=bool(validation.fills))


@router.patch("/{trade_id}", response_model=TradeRead)
def patch_trade(trade_id: int, payload: TradePatch, db: Session = Depends(get_db)) -> TradeRead:
    provided_fields = payload.model_fields_set
    if not provided_fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one field must be provided for update.",
        )

    trade = _load_trade_or_404(db, trade_id)

    if "setup_id" in provided_fields:
        if payload.setup_id is None:
            trade.setup_id = None
            trade.setup_option = None
        else:
            setup_option = _get_setup_option_or_422(db, payload.setup_id)
            trade.setup_id = setup_option.id
            trade.setup_option = setup_option

    if "emotion_id" in provided_fields:
        if payload.emotion_id is None:
            trade.emotion_id = None
            trade.emotion_option = None
        else:
            emotion_option = _get_emotion_option_or_422(db, payload.emotion_id)
            trade.emotion_id = emotion_option.id
            trade.emotion_option = emotion_option

    if "rule_followed" in provided_fields:
        trade.rule_followed = payload.rule_followed

    db.commit()
    db.refresh(trade)
    trade = _load_trade_or_404(db, trade_id)
    return _to_trade_read(trade, include_fills=False)
