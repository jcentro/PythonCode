from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app import database


def _create_legacy_option_tables(session: Session) -> None:
    session.execute(
        text(
            """
            CREATE TABLE setup_options (
                id INTEGER PRIMARY KEY,
                name VARCHAR(64) UNIQUE NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                sort_order INTEGER
            )
            """
        )
    )
    session.execute(
        text(
            """
            CREATE TABLE emotion_options (
                id INTEGER PRIMARY KEY,
                name VARCHAR(64) UNIQUE NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                sort_order INTEGER
            )
            """
        )
    )


def test_migrate_legacy_trade_columns_to_fk_ids(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "legacy_trade_fk_migration.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, class_=Session
    )

    with testing_session_local() as session:
        _create_legacy_option_tables(session)
        session.execute(
            text(
                """
                CREATE TABLE trades (
                    id INTEGER PRIMARY KEY,
                    date DATE NOT NULL,
                    ticker VARCHAR(16) NOT NULL,
                    direction VARCHAR(16) NOT NULL,
                    entry_price FLOAT NOT NULL,
                    exit_price FLOAT NOT NULL,
                    pnl FLOAT NOT NULL,
                    setup VARCHAR(32),
                    rule_followed BOOLEAN NOT NULL,
                    emotion VARCHAR(32),
                    notes TEXT
                )
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO trades (
                    id, date, ticker, direction, entry_price, exit_price, pnl, setup,
                    rule_followed, emotion, notes
                )
                VALUES
                    (1, '2026-02-21', 'SPY', 'CALL', 1.0, 1.5, 0.5, 'HOD_BREAK', 1, 'CALM', NULL),
                    (
                        2, '2026-02-21', 'QQQ', 'PUT', 2.0, 1.8, -0.2,
                        'UNKNOWN_SETUP', 0, 'FOMO', NULL
                    ),
                    (3, '2026-02-21', 'IWM', 'CALL', 1.1, 1.2, 0.1, NULL, 1, NULL, NULL),
                    (4, '2026-02-21', 'DIA', 'CALL', 1.1, 1.2, 0.1, 'CHOP', 1, 'UNKNOWN', NULL)
                """
            )
        )
        session.commit()

    monkeypatch.setattr(database, "SessionLocal", testing_session_local)
    database.migrate_legacy_schema()

    with testing_session_local() as session:
        setup_lookup = dict(session.execute(text("SELECT name, id FROM setup_options")).all())
        assert {"HOD_BREAK", "LOD_BREAK", "CHOP", "OTHER"}.issubset(set(setup_lookup))

        emotion_lookup = dict(session.execute(text("SELECT name, id FROM emotion_options")).all())
        assert {"CALM", "FOMO", "REVENGE", "HESITATION", "OTHER"}.issubset(set(emotion_lookup))

        column_names = {row[1] for row in session.execute(text("PRAGMA table_info(trades)")).all()}
        assert "setup_id" in column_names
        assert "emotion_id" in column_names
        assert "quantity" in column_names
        assert "contract_multiplier" in column_names
        assert "total_pnl_usd" in column_names
        assert "setup" not in column_names
        assert "emotion" not in column_names

        migrated_rows = session.execute(
            text(
                """
                SELECT id, setup_id, emotion_id, quantity, contract_multiplier, total_pnl_usd
                FROM trades
                ORDER BY id
                """
            )
        ).all()
        assert migrated_rows[0] == (
            1,
            setup_lookup["HOD_BREAK"],
            emotion_lookup["CALM"],
            1,
            100,
            50.0,
        )
        assert migrated_rows[1] == (
            2,
            setup_lookup["OTHER"],
            emotion_lookup["FOMO"],
            1,
            100,
            -20.0,
        )
        assert migrated_rows[2] == (
            3,
            setup_lookup["OTHER"],
            emotion_lookup["OTHER"],
            1,
            100,
            10.0,
        )
        assert migrated_rows[3] == (
            4,
            setup_lookup["CHOP"],
            emotion_lookup["OTHER"],
            1,
            100,
            10.0,
        )


def test_migration_rebuild_removes_legacy_not_null_constraints(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "legacy_not_null_constraints.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, class_=Session
    )

    with testing_session_local() as session:
        _create_legacy_option_tables(session)
        session.execute(
            text(
                """
                CREATE TABLE trades (
                    id INTEGER PRIMARY KEY,
                    date DATE NOT NULL,
                    ticker VARCHAR(16) NOT NULL,
                    direction VARCHAR(16) NOT NULL,
                    entry_price FLOAT NOT NULL,
                    exit_price FLOAT NOT NULL,
                    pnl FLOAT NOT NULL,
                    setup VARCHAR(32) NOT NULL,
                    rule_followed BOOLEAN NOT NULL,
                    emotion VARCHAR(32) NOT NULL,
                    notes TEXT
                )
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO trades (
                    id, date, ticker, direction, entry_price, exit_price, pnl, setup,
                    rule_followed, emotion, notes
                )
                VALUES
                    (1, '2026-02-21', 'SPY', 'CALL', 1.0, 1.5, 0.5, 'HOD_BREAK', 1, 'CALM', NULL)
                """
            )
        )
        session.commit()

    monkeypatch.setattr(database, "SessionLocal", testing_session_local)
    database.migrate_legacy_schema()

    with testing_session_local() as session:
        column_info = {
            row[1]: row for row in session.execute(text("PRAGMA table_info(trades)")).all()
        }
        assert column_info["rule_followed"][3] == 0

        session.execute(
            text(
                """
                INSERT INTO trades (
                    date, ticker, direction, entry_price, exit_price, pnl,
                    setup_id, emotion_id, rule_followed, notes
                )
                VALUES
                    ('2026-02-22', 'QQQ', 'PUT', 2.0, 1.8, -0.2, 1, 1, 0, 'new trade')
                """
            )
        )
        session.commit()

        trade_count = session.execute(text("SELECT COUNT(*) FROM trades")).scalar_one()
        assert trade_count == 2
