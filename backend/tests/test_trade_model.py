from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models.emotion_option import EmotionOption
from app.models.setup_option import SetupOption
from app.models.trade import Trade, TradeDirection


def test_create_and_read_trade() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        setup_option = SetupOption(name="HOD_BREAK", is_active=True, sort_order=1)
        emotion_option = EmotionOption(name="CALM", is_active=True, sort_order=1)
        session.add_all([setup_option, emotion_option])
        session.commit()
        session.refresh(setup_option)
        session.refresh(emotion_option)
        emotion_option_id = emotion_option.id

        trade = Trade(
            date=date(2026, 2, 20),
            ticker="SPY",
            direction=TradeDirection.CALL,
            entry_price=1.25,
            exit_price=1.75,
            pnl=0.5,
            quantity=2,
            contract_multiplier=100,
            total_pnl_usd=100.0,
            setup_id=setup_option.id,
            emotion_id=emotion_option.id,
            rule_followed=True,
            notes="Followed plan.",
        )
        session.add(trade)
        session.commit()
        session.refresh(trade)

        fetched = session.scalar(select(Trade).where(Trade.id == trade.id))

    assert fetched is not None
    assert fetched.ticker == "SPY"
    assert fetched.direction == TradeDirection.CALL
    assert fetched.emotion_id == emotion_option_id
    assert fetched.quantity == 2
    assert fetched.total_pnl_usd == 100.0
