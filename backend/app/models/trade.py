from datetime import date as dt_date
from datetime import time as dt_time
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.emotion_option import EmotionOption
    from app.models.import_batch import ImportBatch
    from app.models.setup_option import SetupOption
    from app.models.trade_fill import TradeFill


class TradeDirection(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_trades_source_source_id"),)

    DEFAULT_CONTRACT_MULTIPLIER = 100

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    date: Mapped[dt_date] = mapped_column(Date, nullable=False)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    direction: Mapped[TradeDirection] = mapped_column(
        SqlEnum(TradeDirection, name="trade_direction", native_enum=False),
        nullable=False,
    )
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[float] = mapped_column(Float, nullable=False)
    pnl: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    contract_multiplier: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=DEFAULT_CONTRACT_MULTIPLIER,
    )
    total_pnl_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    setup_id: Mapped[int | None] = mapped_column(
        ForeignKey("setup_options.id"),
        nullable=True,
        index=True,
    )
    emotion_id: Mapped[int | None] = mapped_column(
        ForeignKey("emotion_options.id"),
        nullable=True,
        index=True,
    )
    rule_followed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    entry_time: Mapped[dt_time | None] = mapped_column(Time, nullable=True)
    exit_time: Mapped[dt_time | None] = mapped_column(Time, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    import_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_batches.id"),
        nullable=True,
        index=True,
    )

    setup_option: Mapped["SetupOption | None"] = relationship(
        "SetupOption", back_populates="trades"
    )
    emotion_option: Mapped["EmotionOption | None"] = relationship(
        "EmotionOption", back_populates="trades"
    )
    import_batch: Mapped["ImportBatch | None"] = relationship(
        "ImportBatch", back_populates="trades"
    )
    fills: Mapped[list["TradeFill"]] = relationship(
        "TradeFill",
        back_populates="trade",
        cascade="all, delete-orphan",
    )

    @property
    def setup_name(self) -> str:
        return self.setup_option.name if self.setup_option else ""

    @property
    def emotion_name(self) -> str:
        return self.emotion_option.name if self.emotion_option else ""
