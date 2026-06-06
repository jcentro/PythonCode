from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app


def test_create_and_list_emotions(tmp_path: Path) -> None:
    db_path = tmp_path / "test_emotions_api.db"
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
            active_response = client.post(
                "/api/emotions",
                json={"name": "LOCKED_IN", "sort_order": 10},
            )
            assert active_response.status_code == 201
            active_emotion = active_response.json()
            assert active_emotion["name"] == "LOCKED_IN"
            assert active_emotion["is_active"] is True
            assert active_emotion["sort_order"] == 10

            inactive_response = client.post(
                "/api/emotions",
                json={"name": "OVERCONFIDENT", "is_active": False},
            )
            assert inactive_response.status_code == 201
            inactive_emotion = inactive_response.json()
            assert inactive_emotion["name"] == "OVERCONFIDENT"
            assert inactive_emotion["is_active"] is False

            default_list = client.get("/api/emotions")
            assert default_list.status_code == 200
            default_names = [emotion["name"] for emotion in default_list.json()]
            assert "LOCKED_IN" in default_names
            assert "OVERCONFIDENT" not in default_names

            include_inactive_list = client.get("/api/emotions", params={"include_inactive": "true"})
            assert include_inactive_list.status_code == 200
            all_names = [emotion["name"] for emotion in include_inactive_list.json()]
            assert "LOCKED_IN" in all_names
            assert "OVERCONFIDENT" in all_names
    finally:
        app.dependency_overrides.clear()


def test_patch_emotion_updates_fields_and_filters_default_list(tmp_path: Path) -> None:
    db_path = tmp_path / "test_patch_emotions_api.db"
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
            create_response = client.post(
                "/api/emotions",
                json={"name": "TILTED", "sort_order": 10},
            )
            assert create_response.status_code == 201
            created_emotion = create_response.json()

            patch_response = client.patch(
                f"/api/emotions/{created_emotion['id']}",
                json={"name": "DISCIPLINED", "is_active": False, "sort_order": 20},
            )
            assert patch_response.status_code == 200
            updated_emotion = patch_response.json()
            assert updated_emotion["name"] == "DISCIPLINED"
            assert updated_emotion["is_active"] is False
            assert updated_emotion["sort_order"] == 20

            default_list = client.get("/api/emotions")
            assert default_list.status_code == 200
            default_names = [emotion["name"] for emotion in default_list.json()]
            assert "DISCIPLINED" not in default_names

            include_inactive_list = client.get("/api/emotions", params={"include_inactive": "true"})
            assert include_inactive_list.status_code == 200
            inactive_emotion = next(
                (
                    emotion
                    for emotion in include_inactive_list.json()
                    if emotion["id"] == created_emotion["id"]
                ),
                None,
            )
            assert inactive_emotion is not None
            assert inactive_emotion["name"] == "DISCIPLINED"
            assert inactive_emotion["is_active"] is False
    finally:
        app.dependency_overrides.clear()


def test_patch_emotion_returns_404_for_missing_id(tmp_path: Path) -> None:
    db_path = tmp_path / "test_patch_emotions_404.db"
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
            response = client.patch("/api/emotions/9999", json={"is_active": False})
            assert response.status_code == 404
            assert response.json()["detail"] == "Emotion not found"
    finally:
        app.dependency_overrides.clear()


def test_trade_creation_uses_emotion_id(tmp_path: Path) -> None:
    db_path = tmp_path / "test_trade_emotion_id.db"
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
            setup_response = client.post("/api/setups", json={"name": "HOD_BREAK"})
            assert setup_response.status_code == 201
            setup_id = setup_response.json()["id"]

            emotion_response = client.post("/api/emotions", json={"name": "PATIENT"})
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
                    "notes": "Emotion via emotion_id",
                },
            )
            assert trade_response.status_code == 201
            trade = trade_response.json()
            assert trade["emotion_id"] == emotion_id
            assert trade["emotion_name"] == "PATIENT"
    finally:
        app.dependency_overrides.clear()
