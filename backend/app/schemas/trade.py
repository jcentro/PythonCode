from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field

from app.models.trade import TradeDirection
from app.models.trade_fill import TradeFillSide


class TradeFillWrite(BaseModel):
    side: TradeFillSide
    quantity: int = Field(gt=0)
    price: float = Field(gt=0)
    filled_at: datetime | None = None


class TradeBase(BaseModel):
    date: date
    ticker: str = Field(min_length=1)
    direction: TradeDirection
    entry_price: float
    exit_price: float
    quantity: int = Field(default=1, gt=0)
    setup_id: int | None = Field(default=None, gt=0)
    emotion_id: int | None = Field(default=None, gt=0)
    rule_followed: bool | None
    notes: str | None = None
    entry_time: time | None = None
    exit_time: time | None = None


class TradeCreate(TradeBase):
    rule_followed: bool
    pnl: float | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    use_fills: bool = False
    fills: list[TradeFillWrite] | None = None


class TradeBulkUpdateRequest(BaseModel):
    trade_ids: list[int] = Field(min_length=1)
    setup_id: int | None = Field(default=None, gt=0)
    emotion_id: int | None = Field(default=None, gt=0)
    rule_followed: bool | None = None


class TradeBulkUpdateResponse(BaseModel):
    updated_count: int
    errors: list[str] = Field(default_factory=list)


class TradePatch(BaseModel):
    setup_id: int | None = Field(default=None, gt=0)
    emotion_id: int | None = Field(default=None, gt=0)
    rule_followed: bool | None = None


class TradeFillRead(BaseModel):
    id: int
    trade_id: int
    filled_at: datetime | None
    side: TradeFillSide
    quantity: int
    price: float
    source: str | None
    source_id: str | None

    model_config = ConfigDict(from_attributes=True)


class TradeRead(TradeBase):
    id: int
    pnl: float
    contract_multiplier: int
    total_pnl_usd: float
    duration_seconds: int | None
    total_entry_qty: int | None = None
    total_exit_qty: int | None = None
    avg_entry_price: float | None = None
    avg_exit_price: float | None = None
    realized_pnl_usd: float | None = None
    is_partial: bool = False
    use_fills: bool = False
    fills: list[TradeFillRead] | None = None
    setup_name: str
    emotion_name: str
    source: str | None = None
    source_id: str | None = None

    model_config = ConfigDict(from_attributes=True)
