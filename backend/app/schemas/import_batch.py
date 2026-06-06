from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.import_batch import ImportBatchStatus


class ImportBatchListItemRead(BaseModel):
    id: int
    created_at: datetime
    source: str
    original_filename: str | None
    status: ImportBatchStatus
    detected_trades_count: int
    matched_pairs_count: int
    unmatched_opens_count: int
    unmatched_closes_count: int
    committed_count: int
    skipped_duplicates_count: int
    warnings_count: int


class ImportBatchDetailRead(BaseModel):
    id: int
    created_at: datetime
    source: str
    original_filename: str | None
    file_hash: str | None
    status: ImportBatchStatus
    parsed_rows_count: int
    fills_parsed_count: int
    detected_trades_count: int
    matched_pairs_count: int
    unmatched_opens_count: int
    unmatched_closes_count: int
    excluded_count: int
    warnings: list[str]
    fills_count: int
    fills: list[dict[str, Any]] = Field(default_factory=list)
    unmatched_opens: list[dict[str, Any]] = Field(default_factory=list)
    unmatched_closes: list[dict[str, Any]] = Field(default_factory=list)
    committed_count: int
    skipped_duplicates_count: int
    errors: list[str]
    pnl_total_committed_usd: float
