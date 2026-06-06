from datetime import date, datetime, time

from pydantic import BaseModel, Field

from app.models.trade import TradeDirection
from app.models.trade_fill import TradeFillSide


class BackupSetupRecord(BaseModel):
    id: int = Field(gt=0)
    name: str = Field(min_length=1)
    is_active: bool = True
    sort_order: int | None = None


class BackupEmotionRecord(BaseModel):
    id: int = Field(gt=0)
    name: str = Field(min_length=1)
    is_active: bool = True
    sort_order: int | None = None


class BackupTradeFillRecord(BaseModel):
    filled_at: datetime | None = None
    side: TradeFillSide
    quantity: int = Field(gt=0)
    price: float = Field(gt=0)
    source: str | None = None
    source_id: str | None = None


class BackupTradeRecord(BaseModel):
    id: int = Field(gt=0)
    date: date
    ticker: str = Field(min_length=1)
    direction: TradeDirection
    entry_price: float
    exit_price: float
    pnl: float
    quantity: int = Field(gt=0)
    contract_multiplier: int = Field(gt=0)
    total_pnl_usd: float
    setup_id: int | None = Field(default=None, gt=0)
    emotion_id: int | None = Field(default=None, gt=0)
    rule_followed: bool | None
    notes: str | None = None
    entry_time: time | None = None
    exit_time: time | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    source: str | None = None
    source_id: str | None = None
    import_batch_id: int | None = None
    fills: list[BackupTradeFillRecord] = Field(default_factory=list)


class BackupPayloadData(BaseModel):
    setups: list[BackupSetupRecord]
    emotions: list[BackupEmotionRecord]
    trades: list[BackupTradeRecord]


class BackupImportRequest(BaseModel):
    schema_version: int
    exported_at: datetime | None = None
    data: BackupPayloadData


class BackupImportCounts(BaseModel):
    trades: int
    fills: int
    setups: int
    emotions: int


class BackupImportResponse(BaseModel):
    status: str
    imported: BackupImportCounts
