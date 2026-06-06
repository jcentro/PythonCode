from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Index, Integer, String, Text, desc, func
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.trade import Trade


class ImportBatchStatus(str, Enum):
    PREVIEWED = "previewed"
    COMMITTED = "committed"
    FAILED = "failed"


class ImportBatch(Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        Index("ix_import_batches_created_at_desc", desc("created_at")),
        Index("ix_import_batches_source_file_hash", "source", "file_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
    status: Mapped[ImportBatchStatus] = mapped_column(
        SqlEnum(ImportBatchStatus, name="import_batch_status", native_enum=False),
        nullable=False,
        default=ImportBatchStatus.PREVIEWED,
        server_default=ImportBatchStatus.PREVIEWED.value,
    )

    parsed_rows_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    fills_parsed_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    detected_trades_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    matched_pairs_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    unmatched_opens_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    unmatched_closes_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    excluded_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    warnings_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    fills_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    unmatched_opens_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    unmatched_closes_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    committed_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    skipped_duplicates_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    commit_errors_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    trades: Mapped[list["Trade"]] = relationship("Trade", back_populates="import_batch")
