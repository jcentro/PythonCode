from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from fastapi import HTTPException, status

from app.models.trade import Trade
from app.schemas.trade import TradeCreate, TradeFillWrite
from app.services.trade_computation import FillComputationResult, compute_trade_from_fills


@dataclass
class TradeValidationResult:
    normalized_ticker: str
    fills: list[TradeFillWrite]
    fill_summary: FillComputationResult | None


def _raise_trade_validation_error(errors: list[str]) -> None:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=" ".join(errors),
    )


def validate_trade_payload(payload: TradeCreate) -> TradeValidationResult:
    errors: list[str] = []
    normalized_ticker = payload.ticker.strip().upper()
    if not normalized_ticker:
        errors.append("Ticker is required.")

    if not isfinite(payload.entry_price) or payload.entry_price <= 0:
        errors.append("Entry price must be greater than zero.")

    if not isfinite(payload.exit_price) or payload.exit_price <= 0:
        errors.append("Exit price must be greater than zero.")

    if payload.quantity <= 0:
        errors.append("Quantity must be a whole number greater than zero.")

    if payload.setup_id is not None and payload.setup_id <= 0:
        errors.append("Setup must be a positive id when provided.")

    if payload.emotion_id is not None and payload.emotion_id <= 0:
        errors.append("Emotion must be a positive id when provided.")

    computed_pnl = (
        payload.pnl
        if payload.pnl is not None
        else payload.exit_price - payload.entry_price
    )
    if not isfinite(computed_pnl):
        errors.append("Computed PnL must be finite.")

    computed_total_pnl_usd = computed_pnl * payload.quantity * Trade.DEFAULT_CONTRACT_MULTIPLIER
    if not isfinite(computed_total_pnl_usd):
        errors.append("Total PnL must be finite.")

    use_fills = payload.use_fills or payload.fills is not None
    if not use_fills:
        if errors:
            _raise_trade_validation_error(errors)
        return TradeValidationResult(
            normalized_ticker=normalized_ticker,
            fills=[],
            fill_summary=None,
        )

    fills = payload.fills or []
    if not fills:
        errors.append("Add at least one BUY fill and one SELL fill.")
        _raise_trade_validation_error(errors)

    buy_fills = [fill for fill in fills if fill.side == "BUY"]
    sell_fills = [fill for fill in fills if fill.side == "SELL"]
    if not buy_fills or not sell_fills:
        errors.append("Add at least one BUY fill and one SELL fill.")

    total_buy_qty = sum(fill.quantity for fill in buy_fills)
    total_sell_qty = sum(fill.quantity for fill in sell_fills)
    if buy_fills and sell_fills and total_buy_qty != total_sell_qty:
        errors.append(
            "Open positions are not supported yet. Total BUY quantity "
            "must equal total SELL quantity."
        )

    if errors:
        deduped_errors: list[str] = []
        for error in errors:
            if error not in deduped_errors:
                deduped_errors.append(error)
        _raise_trade_validation_error(deduped_errors)

    fill_summary = compute_trade_from_fills(fills)
    if fill_summary.total_entry_qty <= 0:
        errors.append("Avg Entry must be a finite value greater than zero.")
    if fill_summary.total_exit_qty <= 0:
        errors.append("Avg Exit must be a finite value greater than zero.")
    if not isfinite(fill_summary.avg_entry_price) or fill_summary.avg_entry_price <= 0:
        errors.append("Avg Entry must be a finite value greater than zero.")
    if not isfinite(fill_summary.avg_exit_price) or fill_summary.avg_exit_price <= 0:
        errors.append("Avg Exit must be a finite value greater than zero.")
    if fill_summary.matched_qty <= 0:
        errors.append("Total Quantity must be a whole number greater than zero.")
    if not isfinite(fill_summary.realized_pnl_usd):
        errors.append("Total PnL must be finite.")

    if errors:
        deduped_errors: list[str] = []
        for error in errors:
            if error not in deduped_errors:
                deduped_errors.append(error)
        _raise_trade_validation_error(deduped_errors)

    return TradeValidationResult(
        normalized_ticker=normalized_ticker,
        fills=fills,
        fill_summary=fill_summary,
    )
