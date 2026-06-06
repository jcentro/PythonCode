from typing import Literal

from pydantic import BaseModel


class DetectedTradePreviewFill(BaseModel):
    side: str
    qty: int
    price: float
    exec_datetime: str


class DetectedTradePreview(BaseModel):
    temp_id: str
    date: str
    symbol: str
    exp: str
    strike: float
    option_type: str
    entry_fills_count: int
    exit_fills_count: int
    total_entry_qty: int
    total_exit_qty: int
    matched_qty: int
    avg_entry_price: float
    avg_exit_price: float
    is_partial: bool
    fills: list[DetectedTradePreviewFill]

    # Backward-compatible fields used by existing import commit/UI code.
    ticker: str
    direction: str
    quantity: int
    entry_time: str | None
    exit_time: str | None
    entry_price: float
    exit_price: float
    duration_seconds: int | None
    total_pnl_usd: float
    duplicate_status: Literal["new", "duplicate", "possible_duplicate"] = "new"
    duplicate_reason: str | None = None
    existing_trade_id: int | None = None


class ToSPreviewResponse(BaseModel):
    batch_id: int
    detected_trades: list[DetectedTradePreview]
    warnings: list[str]


class ToSCommitItem(BaseModel):
    temp_id: str
    setup_id: int | None = None
    emotion_id: int | None = None
    rule_followed: bool | None = None
    notes: str | None = None


class ToSCommitRequest(BaseModel):
    batch_id: int
    items: list[ToSCommitItem]


class ToSCommitResponse(BaseModel):
    imported: int
    skipped_duplicates: int
    errors: list[str]
