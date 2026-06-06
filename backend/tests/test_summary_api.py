from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.emotion_option import EmotionOption
from app.models.setup_option import SetupOption


def _seed_default_setups(testing_session_local: sessionmaker[Session]) -> dict[str, int]:
    with testing_session_local() as session:
        session.add_all(
            [
                SetupOption(name="HOD_BREAK", is_active=True, sort_order=1),
                SetupOption(name="LOD_BREAK", is_active=True, sort_order=2),
                SetupOption(name="CHOP", is_active=True, sort_order=3),
                SetupOption(name="OTHER", is_active=True, sort_order=4),
            ]
        )
        session.commit()
        setups = session.query(SetupOption).all()
        return {setup.name: setup.id for setup in setups}


def _seed_default_emotions(testing_session_local: sessionmaker[Session]) -> dict[str, int]:
    with testing_session_local() as session:
        session.add_all(
            [
                EmotionOption(name="CALM", is_active=True, sort_order=1),
                EmotionOption(name="FOMO", is_active=True, sort_order=2),
                EmotionOption(name="REVENGE", is_active=True, sort_order=3),
                EmotionOption(name="HESITATION", is_active=True, sort_order=4),
                EmotionOption(name="OTHER", is_active=True, sort_order=5),
            ]
        )
        session.commit()
        emotions = session.query(EmotionOption).all()
        return {emotion.name: emotion.id for emotion in emotions}


def test_daily_summary_returns_zeros_when_no_trades(tmp_path: Path) -> None:
    db_path = tmp_path / "test_summary_empty.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, class_=Session
    )
    Base.metadata.create_all(bind=engine)
    _seed_default_setups(testing_session_local)
    _seed_default_emotions(testing_session_local)

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            response = client.get("/api/summary/daily", params={"date": "2026-02-22"})
            assert response.status_code == 200
            assert response.json() == {
                "date": "2026-02-22",
                "total_trades": 0,
                "pct_rule_followed": 0.0,
                "discipline_score": 0,
                "total_pnl": 0.0,
                "counts_by_setup": {},
                "counts_by_emotion": {},
            }
    finally:
        app.dependency_overrides.clear()


def test_daily_summary_aggregates_values(tmp_path: Path) -> None:
    db_path = tmp_path / "test_summary_values.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, class_=Session
    )
    Base.metadata.create_all(bind=engine)
    setup_ids = _seed_default_setups(testing_session_local)
    emotion_ids = _seed_default_emotions(testing_session_local)

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            trade_1 = {
                "date": "2026-02-21",
                "ticker": "SPY",
                "direction": "CALL",
                "entry_price": 1.25,
                "exit_price": 1.75,
                "quantity": 1,
                "setup_id": setup_ids["HOD_BREAK"],
                "emotion_id": emotion_ids["CALM"],
                "rule_followed": True,
                "notes": "A setup",
            }
            trade_2 = {
                "date": "2026-02-21",
                "ticker": "QQQ",
                "direction": "PUT",
                "entry_price": 2.0,
                "exit_price": 1.8,
                "quantity": 2,
                "setup_id": setup_ids["CHOP"],
                "emotion_id": emotion_ids["FOMO"],
                "rule_followed": False,
                "notes": "B setup",
            }

            assert client.post("/api/trades", json=trade_1).status_code == 201
            assert client.post("/api/trades", json=trade_2).status_code == 201

            response = client.get("/api/summary/daily", params={"date": "2026-02-21"})
            assert response.status_code == 200
            assert response.json() == {
                "date": "2026-02-21",
                "total_trades": 2,
                "pct_rule_followed": 50.0,
                "discipline_score": -5,
                "total_pnl": 10.0,
                "counts_by_setup": {"HOD_BREAK": 1, "CHOP": 1},
                "counts_by_emotion": {"CALM": 1, "FOMO": 1},
            }
    finally:
        app.dependency_overrides.clear()
