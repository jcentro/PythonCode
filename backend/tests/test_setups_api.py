from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.emotion_option import EmotionOption


def test_create_and_list_setups(tmp_path: Path) -> None:
    db_path = tmp_path / "test_setups_api.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, class_=Session
    )
    Base.metadata.create_all(bind=engine)
    with testing_session_local() as session:
        session.add(EmotionOption(name="CALM", is_active=True, sort_order=1))
        session.commit()

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            active_response = client.post(
                "/api/setups",
                json={"name": "BREAKOUT_PULLBACK", "sort_order": 10},
            )
            assert active_response.status_code == 201
            active_setup = active_response.json()
            assert active_setup["name"] == "BREAKOUT_PULLBACK"
            assert active_setup["is_active"] is True
            assert active_setup["sort_order"] == 10

            inactive_response = client.post(
                "/api/setups",
                json={"name": "RETEST", "is_active": False},
            )
            assert inactive_response.status_code == 201
            inactive_setup = inactive_response.json()
            assert inactive_setup["name"] == "RETEST"
            assert inactive_setup["is_active"] is False

            default_list = client.get("/api/setups")
            assert default_list.status_code == 200
            default_names = [setup["name"] for setup in default_list.json()]
            assert "BREAKOUT_PULLBACK" in default_names
            assert "RETEST" not in default_names

            include_inactive_list = client.get("/api/setups", params={"include_inactive": "true"})
            assert include_inactive_list.status_code == 200
            all_names = [setup["name"] for setup in include_inactive_list.json()]
            assert "BREAKOUT_PULLBACK" in all_names
            assert "RETEST" in all_names
    finally:
        app.dependency_overrides.clear()


def test_trade_creation_uses_setup_id(tmp_path: Path) -> None:
    db_path = tmp_path / "test_trade_setup_id.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, class_=Session
    )
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            setup_response = client.post("/api/setups", json={"name": "CUSTOM_SETUP"})
            assert setup_response.status_code == 201
            setup_id = setup_response.json()["id"]
            emotion_response = client.post("/api/emotions", json={"name": "CUSTOM_EMOTION"})
            assert emotion_response.status_code == 201
            emotion_id = emotion_response.json()["id"]

            trade_response = client.post(
                "/api/trades",
                json={
                    "date": "2026-02-21",
                    "ticker": "SPY",
                    "direction": "CALL",
                    "entry_price": 1.25,
                    "exit_price": 1.75,
                    "setup_id": setup_id,
                    "emotion_id": emotion_id,
                    "rule_followed": True,
                    "notes": "Setup via setup_id",
                },
            )
            assert trade_response.status_code == 201
            trade = trade_response.json()
            assert trade["setup_id"] == setup_id
            assert trade["setup_name"] == "CUSTOM_SETUP"
            assert trade["emotion_id"] == emotion_id
            assert trade["emotion_name"] == "CUSTOM_EMOTION"
    finally:
        app.dependency_overrides.clear()


def test_patch_setup_updates_fields_and_filters_default_list(tmp_path: Path) -> None:
    db_path = tmp_path / "test_patch_setups_api.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, class_=Session
    )
    Base.metadata.create_all(bind=engine)
    with testing_session_local() as session:
        session.add(EmotionOption(name="CALM", is_active=True, sort_order=1))
        session.commit()

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            create_response = client.post(
                "/api/setups",
                json={"name": "BREAKOUT_PULLBACK", "sort_order": 10},
            )
            assert create_response.status_code == 201
            created_setup = create_response.json()

            patch_response = client.patch(
                f"/api/setups/{created_setup['id']}",
                json={"name": "BREAKOUT_RETEST", "is_active": False, "sort_order": 20},
            )
            assert patch_response.status_code == 200
            updated_setup = patch_response.json()
            assert updated_setup["name"] == "BREAKOUT_RETEST"
            assert updated_setup["is_active"] is False
            assert updated_setup["sort_order"] == 20

            default_list = client.get("/api/setups")
            assert default_list.status_code == 200
            default_names = [setup["name"] for setup in default_list.json()]
            assert "BREAKOUT_RETEST" not in default_names

            include_inactive_list = client.get("/api/setups", params={"include_inactive": "true"})
            assert include_inactive_list.status_code == 200
            inactive_setup = next(
                (
                    setup
                    for setup in include_inactive_list.json()
                    if setup["id"] == created_setup["id"]
                ),
                None,
            )
            assert inactive_setup is not None
            assert inactive_setup["name"] == "BREAKOUT_RETEST"
            assert inactive_setup["is_active"] is False
    finally:
        app.dependency_overrides.clear()


def test_patch_setup_returns_404_for_missing_id(tmp_path: Path) -> None:
    db_path = tmp_path / "test_patch_setups_404.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, class_=Session
    )
    Base.metadata.create_all(bind=engine)
    with testing_session_local() as session:
        session.add(EmotionOption(name="CALM", is_active=True, sort_order=1))
        session.commit()

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            response = client.patch("/api/setups/9999", json={"is_active": False})
            assert response.status_code == 404
            assert response.json()["detail"] == "Setup not found"
    finally:
        app.dependency_overrides.clear()


def test_trade_keeps_setup_name_after_setup_deactivation(tmp_path: Path) -> None:
    db_path = tmp_path / "test_setup_deactivation_trade_display.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, class_=Session
    )
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            setup_response = client.post("/api/setups", json={"name": "OPEN_RANGE_BREAK"})
            assert setup_response.status_code == 201
            setup_id = setup_response.json()["id"]
            emotion_response = client.post("/api/emotions", json={"name": "OPEN_RANGE"})
            assert emotion_response.status_code == 201
            emotion_id = emotion_response.json()["id"]

            trade_response = client.post(
                "/api/trades",
                json={
                    "date": "2026-02-21",
                    "ticker": "SPY",
                    "direction": "CALL",
                    "entry_price": 1.25,
                    "exit_price": 1.75,
                    "setup_id": setup_id,
                    "emotion_id": emotion_id,
                    "rule_followed": True,
                    "notes": "Before setup deactivation",
                },
            )
            assert trade_response.status_code == 201
            created_trade = trade_response.json()
            assert created_trade["setup_name"] == "OPEN_RANGE_BREAK"

            deactivate_response = client.patch(f"/api/setups/{setup_id}", json={"is_active": False})
            assert deactivate_response.status_code == 200

            list_response = client.get("/api/trades", params={"date": "2026-02-21"})
            assert list_response.status_code == 200
            listed_trades = list_response.json()
            assert len(listed_trades) == 1
            assert listed_trades[0]["setup_id"] == setup_id
            assert listed_trades[0]["setup_name"] == "OPEN_RANGE_BREAK"
            assert listed_trades[0]["emotion_id"] == emotion_id
            assert listed_trades[0]["emotion_name"] == "OPEN_RANGE"
    finally:
        app.dependency_overrides.clear()
