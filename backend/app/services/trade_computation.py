from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from app.models.trade import Trade
from app.models.trade_fill import TradeFillSide

if TYPE_CHECKING:
    from app.models.trade_fill import TradeFill


class FillLike(Protocol):
    side: TradeFillSide
    quantity: int
    price: float
    filled_at: datetime | None


@dataclass
class FillComputationResult:
    total_entry_qty: int
    total_exit_qty: int
    matched_qty: int
    avg_entry_price: float
    avg_exit_price: float
    realized_pnl_usd: float
    duration_seconds: int | None
    is_partial: bool


@dataclass
class TradeSummaryResult:
    has_fills: bool
    quantity: int
    entry_price: float
    exit_price: float
    pnl: float
    total_pnl_usd: float
    duration_seconds: int | None
    total_entry_qty: int | None
    total_exit_qty: int | None
    avg_entry_price: float | None
    avg_exit_price: float | None
    realized_pnl_usd: float | None
    is_partial: bool


def _compute_fill_result(fills: Iterable[FillLike]) -> FillComputationResult:
    fills_list = list(fills)
    entry_fills = [fill for fill in fills_list if fill.side == TradeFillSide.BUY]
    exit_fills = [fill for fill in fills_list if fill.side == TradeFillSide.SELL]

    total_entry_qty = sum(fill.quantity for fill in entry_fills)
    total_exit_qty = sum(fill.quantity for fill in exit_fills)
    matched_qty = min(total_entry_qty, total_exit_qty)

    avg_entry_price = (
        sum(fill.price * fill.quantity for fill in entry_fills) / total_entry_qty
        if total_entry_qty > 0
        else 0.0
    )
    avg_exit_price = (
        sum(fill.price * fill.quantity for fill in exit_fills) / total_exit_qty
        if total_exit_qty > 0
        else 0.0
    )

    realized_pnl_usd = (
        matched_qty * (avg_exit_price - avg_entry_price) * Trade.DEFAULT_CONTRACT_MULTIPLIER
        if matched_qty > 0
        else 0.0
    )
    realized_pnl_usd = round(realized_pnl_usd, 2)

    filled_timestamps = sorted(fill.filled_at for fill in fills_list if fill.filled_at is not None)
    duration_seconds: int | None = None
    if filled_timestamps:
        first_fill_time: datetime = filled_timestamps[0]
        last_fill_time: datetime = filled_timestamps[-1]
        duration_seconds = max(0, int((last_fill_time - first_fill_time).total_seconds()))

    return FillComputationResult(
        total_entry_qty=total_entry_qty,
        total_exit_qty=total_exit_qty,
        matched_qty=matched_qty,
        avg_entry_price=round(avg_entry_price, 4),
        avg_exit_price=round(avg_exit_price, 4),
        realized_pnl_usd=realized_pnl_usd,
        duration_seconds=duration_seconds,
        is_partial=total_entry_qty != total_exit_qty,
    )


def compute_trade_from_fills(fills: Iterable[FillLike]) -> FillComputationResult:
    return _compute_fill_result(fills)


def computeTradeFromFills(fills: Iterable[TradeFill]) -> FillComputationResult:
    return compute_trade_from_fills(fills)


def compute_trade_summary(trade: Trade) -> TradeSummaryResult:
    if trade.fills:
        fill_result = compute_trade_from_fills(trade.fills)

        entry_price = (
            fill_result.avg_entry_price if fill_result.total_entry_qty > 0 else trade.entry_price
        )
        exit_price = (
            fill_result.avg_exit_price if fill_result.total_exit_qty > 0 else trade.exit_price
        )
        if fill_result.total_entry_qty > 0 and fill_result.total_exit_qty > 0:
            pnl = round(exit_price - entry_price, 4)
        else:
            pnl = trade.pnl

        duration_seconds = (
            fill_result.duration_seconds
            if fill_result.duration_seconds is not None
            else trade.duration_seconds
        )

        return TradeSummaryResult(
            has_fills=True,
            quantity=fill_result.matched_qty if fill_result.matched_qty > 0 else trade.quantity,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl=pnl,
            total_pnl_usd=fill_result.realized_pnl_usd,
            duration_seconds=duration_seconds,
            total_entry_qty=fill_result.total_entry_qty,
            total_exit_qty=fill_result.total_exit_qty,
            avg_entry_price=fill_result.avg_entry_price
            if fill_result.total_entry_qty > 0
            else None,
            avg_exit_price=fill_result.avg_exit_price if fill_result.total_exit_qty > 0 else None,
            realized_pnl_usd=fill_result.realized_pnl_usd,
            is_partial=fill_result.is_partial,
        )

    return TradeSummaryResult(
        has_fills=False,
        quantity=trade.quantity,
        entry_price=trade.entry_price,
        exit_price=trade.exit_price,
        pnl=trade.pnl,
        total_pnl_usd=float(trade.total_pnl_usd),
        duration_seconds=trade.duration_seconds,
        total_entry_qty=None,
        total_exit_qty=None,
        avg_entry_price=None,
        avg_exit_price=None,
        realized_pnl_usd=None,
        is_partial=False,
    )


def trade_total_pnl_usd(trade: Trade) -> float:
    return float(compute_trade_summary(trade).total_pnl_usd)
