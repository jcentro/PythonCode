from datetime import date, datetime

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models.emotion_option import EmotionOption
from app.models.setup_option import SetupOption
from app.models.trade import Trade, TradeDirection
from app.models.trade_fill import TradeFill, TradeFillSide


def test_trade_fills_persist_and_delete_cascades() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        setup_option = SetupOption(name="HOD_BREAK", is_active=True, sort_order=1)
        emotion_option = EmotionOption(name="CALM", is_active=True, sort_order=1)
        session.add_all([setup_option, emotion_option])
        session.commit()
        session.refresh(setup_option)
        session.refresh(emotion_option)

        trade = Trade(
            date=date(2026, 2, 21),
            ticker="SPY",
            direction=TradeDirection.CALL,
            entry_price=1.0,
            exit_price=1.5,
            pnl=0.5,
            quantity=2,
            contract_multiplier=100,
            total_pnl_usd=100.0,
            setup_id=setup_option.id,
            emotion_id=emotion_option.id,
            rule_followed=True,
            notes="Scaled in and out.",
        )
        session.add(trade)
        session.commit()
        session.refresh(trade)

        session.add_all(
            [
                TradeFill(
                    trade_id=trade.id,
                    filled_at=datetime(2026, 2, 21, 9, 35, 0),
                    side=TradeFillSide.BUY,
                    quantity=1,
                    price=1.0,
                    source="manual",
                ),
                TradeFill(
                    trade_id=trade.id,
                    filled_at=datetime(2026, 2, 21, 9, 42, 0),
                    side=TradeFillSide.SELL,
                    quantity=1,
                    price=1.2,
                    source="manual",
                ),
            ]
        )
        session.commit()

        fill_count = session.execute(
            select(func.count()).select_from(TradeFill).where(TradeFill.trade_id == trade.id)
        ).scalar_one()
        assert fill_count == 2

        session.delete(trade)
        session.commit()

        remaining_fill_count = session.execute(
            select(func.count()).select_from(TradeFill)
        ).scalar_one()
        assert remaining_fill_count == 0
