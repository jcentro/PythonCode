from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.trade import Trade


class TradeFillSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class TradeFill(Base):
    __tablename__ = "trade_fills"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_trade_fills_quantity_gt_zero"),
        CheckConstraint("price >= 0", name="ck_trade_fills_price_ge_zero"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    trade_id: Mapped[int] = mapped_column(
        ForeignKey("trades.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    side: Mapped[TradeFillSide] = mapped_column(
        SqlEnum(TradeFillSide, name="trade_fill_side", native_enum=False),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
    )

    trade: Mapped["Trade"] = relationship("Trade", back_populates="fills")
