import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = BASE_DIR / "discipline_tracker.db"
configured_db_path = os.getenv("DISCIPLINE_DB_PATH")

if configured_db_path:
    candidate_path = Path(configured_db_path)
    DB_PATH = candidate_path if candidate_path.is_absolute() else BASE_DIR / candidate_path
else:
    DB_PATH = DEFAULT_DB_PATH

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")
DEFAULT_SETUP_OPTIONS: list[tuple[str, int]] = [
    ("HOD_BREAK", 1),
    ("LOD_BREAK", 2),
    ("CHOP", 3),
    ("OTHER", 4),
]
DEFAULT_EMOTION_OPTIONS: list[tuple[str, int]] = [
    ("CALM", 1),
    ("FOMO", 2),
    ("REVENGE", 3),
    ("HESITATION", 4),
    ("OTHER", 5),
]

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


class Base(DeclarativeBase):
    pass


def _table_exists(db_session: Session, table_name: str) -> bool:
    query = text("SELECT name FROM sqlite_master WHERE type = 'table' AND name = :table_name")
    return db_session.execute(query, {"table_name": table_name}).scalar_one_or_none() is not None


def _seed_default_setup_options(db_session: Session) -> None:
    for name, sort_order in DEFAULT_SETUP_OPTIONS:
        db_session.execute(
            text(
                """
                INSERT INTO setup_options (name, is_active, sort_order)
                SELECT :name, 1, :sort_order
                WHERE NOT EXISTS (SELECT 1 FROM setup_options WHERE name = :name)
                """
            ),
            {"name": name, "sort_order": sort_order},
        )


def _seed_default_emotion_options(db_session: Session) -> None:
    for name, sort_order in DEFAULT_EMOTION_OPTIONS:
        db_session.execute(
            text(
                """
                INSERT INTO emotion_options (name, is_active, sort_order)
                SELECT :name, 1, :sort_order
                WHERE NOT EXISTS (SELECT 1 FROM emotion_options WHERE name = :name)
                """
            ),
            {"name": name, "sort_order": sort_order},
        )


def _get_table_columns(db_session: Session, table_name: str) -> set[str]:
    column_rows = db_session.execute(
        text(f"PRAGMA table_info({table_name})")  # noqa: S608 - trusted internal table name
    ).all()
    return {row[1] for row in column_rows}


def _is_column_not_null(db_session: Session, table_name: str, column_name: str) -> bool:
    column_rows = db_session.execute(
        text(f"PRAGMA table_info({table_name})")  # noqa: S608 - trusted internal table name
    ).all()
    for row in column_rows:
        if row[1] == column_name:
            return bool(row[3])
    return False


def _migrate_trades_setup_column(db_session: Session) -> None:
    if not _table_exists(db_session, "trades"):
        return

    columns = _get_table_columns(db_session, "trades")
    if "setup_id" not in columns:
        db_session.execute(text("ALTER TABLE trades ADD COLUMN setup_id INTEGER"))
        columns.add("setup_id")

    if "setup" in columns:
        db_session.execute(
            text(
                """
                UPDATE trades
                SET setup_id = (
                    SELECT id
                    FROM setup_options
                    WHERE setup_options.name = trades.setup
                )
                WHERE setup_id IS NULL AND setup IS NOT NULL
                """
            )
        )

    other_setup_id = db_session.execute(
        text("SELECT id FROM setup_options WHERE name = 'OTHER'")
    ).scalar_one_or_none()
    if other_setup_id is not None:
        db_session.execute(
            text("UPDATE trades SET setup_id = :other_setup_id WHERE setup_id IS NULL"),
            {"other_setup_id": other_setup_id},
        )


def _migrate_trades_emotion_column(db_session: Session) -> None:
    if not _table_exists(db_session, "trades"):
        return

    columns = _get_table_columns(db_session, "trades")
    if "emotion_id" not in columns:
        db_session.execute(text("ALTER TABLE trades ADD COLUMN emotion_id INTEGER"))
        columns.add("emotion_id")

    if "emotion" in columns:
        db_session.execute(
            text(
                """
                UPDATE trades
                SET emotion_id = (
                    SELECT id
                    FROM emotion_options
                    WHERE emotion_options.name = trades.emotion
                )
                WHERE emotion_id IS NULL AND emotion IS NOT NULL
                """
            )
        )

    other_emotion_id = db_session.execute(
        text("SELECT id FROM emotion_options WHERE name = 'OTHER'")
    ).scalar_one_or_none()
    if other_emotion_id is not None:
        db_session.execute(
            text("UPDATE trades SET emotion_id = :other_emotion_id WHERE emotion_id IS NULL"),
            {"other_emotion_id": other_emotion_id},
        )


def _rebuild_trades_table_with_fk_columns(db_session: Session) -> None:
    if not _table_exists(db_session, "trades"):
        return
    if not _table_exists(db_session, "setup_options") or not _table_exists(
        db_session, "emotion_options"
    ):
        return

    columns = _get_table_columns(db_session, "trades")
    if "setup" not in columns and "emotion" not in columns:
        return

    other_setup_id = db_session.execute(
        text("SELECT id FROM setup_options WHERE name = 'OTHER'")
    ).scalar_one_or_none()
    other_emotion_id = db_session.execute(
        text("SELECT id FROM emotion_options WHERE name = 'OTHER'")
    ).scalar_one_or_none()
    if other_setup_id is None or other_emotion_id is None:
        return

    db_session.execute(
        text(
            """
            CREATE TABLE trades__new (
                id INTEGER PRIMARY KEY,
                date DATE NOT NULL,
                ticker VARCHAR(16) NOT NULL,
                direction VARCHAR(16) NOT NULL,
                entry_price FLOAT NOT NULL,
                exit_price FLOAT NOT NULL,
                pnl FLOAT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                contract_multiplier INTEGER NOT NULL DEFAULT 100,
                total_pnl_usd FLOAT NOT NULL DEFAULT 0,
                setup_id INTEGER NOT NULL,
                emotion_id INTEGER NOT NULL,
                rule_followed BOOLEAN,
                notes TEXT,
                entry_time TIME,
                exit_time TIME,
                duration_seconds INTEGER,
                source VARCHAR(32),
                source_id VARCHAR(64),
                import_batch_id INTEGER
            )
            """
        )
    )
    db_session.execute(
        text(
            """
            INSERT INTO trades__new (
                id, date, ticker, direction, entry_price, exit_price, pnl,
                quantity, contract_multiplier, total_pnl_usd,
                setup_id, emotion_id, rule_followed, notes,
                entry_time, exit_time, duration_seconds, source, source_id, import_batch_id
            )
            SELECT
                id, date, ticker, direction, entry_price, exit_price, pnl,
                1, 100, pnl * 1 * 100,
                COALESCE(setup_id, :other_setup_id),
                COALESCE(emotion_id, :other_emotion_id),
                rule_followed, notes, NULL, NULL, NULL, NULL, NULL, NULL
            FROM trades
            """
        ),
        {"other_setup_id": other_setup_id, "other_emotion_id": other_emotion_id},
    )
    db_session.execute(text("DROP TABLE trades"))
    db_session.execute(text("ALTER TABLE trades__new RENAME TO trades"))
    db_session.execute(text("CREATE INDEX IF NOT EXISTS ix_trades_id ON trades (id)"))
    db_session.execute(text("CREATE INDEX IF NOT EXISTS ix_trades_ticker ON trades (ticker)"))
    db_session.execute(text("CREATE INDEX IF NOT EXISTS ix_trades_setup_id ON trades (setup_id)"))
    db_session.execute(
        text("CREATE INDEX IF NOT EXISTS ix_trades_emotion_id ON trades (emotion_id)")
    )
    db_session.execute(
        text("CREATE INDEX IF NOT EXISTS ix_trades_import_batch_id ON trades (import_batch_id)")
    )
    db_session.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_trades_source_source_id "
            "ON trades (source, source_id)"
        )
    )


def _migrate_trade_rule_followed_nullable(db_session: Session) -> None:
    if not _table_exists(db_session, "trades"):
        return
    if not _is_column_not_null(db_session, "trades", "rule_followed"):
        return

    db_session.execute(text("PRAGMA foreign_keys=OFF"))
    try:
        db_session.execute(
            text(
                """
                CREATE TABLE trades__rule_followed_nullable (
                    id INTEGER PRIMARY KEY,
                    date DATE NOT NULL,
                    ticker VARCHAR(16) NOT NULL,
                    direction VARCHAR(16) NOT NULL,
                    entry_price FLOAT NOT NULL,
                    exit_price FLOAT NOT NULL,
                    pnl FLOAT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    contract_multiplier INTEGER NOT NULL DEFAULT 100,
                    total_pnl_usd FLOAT NOT NULL DEFAULT 0,
                    setup_id INTEGER NOT NULL,
                    emotion_id INTEGER NOT NULL,
                    rule_followed BOOLEAN,
                    notes TEXT,
                    entry_time TIME,
                    exit_time TIME,
                    duration_seconds INTEGER,
                    source VARCHAR(32),
                    source_id VARCHAR(64),
                    import_batch_id INTEGER
                )
                """
            )
        )
        db_session.execute(
            text(
                """
                INSERT INTO trades__rule_followed_nullable (
                    id, date, ticker, direction, entry_price, exit_price, pnl,
                    quantity, contract_multiplier, total_pnl_usd,
                    setup_id, emotion_id, rule_followed, notes,
                    entry_time, exit_time, duration_seconds, source, source_id, import_batch_id
                )
                SELECT
                    id, date, ticker, direction, entry_price, exit_price, pnl,
                    quantity, contract_multiplier, total_pnl_usd,
                    setup_id, emotion_id, rule_followed, notes,
                    entry_time, exit_time, duration_seconds, source, source_id, import_batch_id
                FROM trades
                """
            )
        )
        db_session.execute(text("DROP TABLE trades"))
        db_session.execute(text("ALTER TABLE trades__rule_followed_nullable RENAME TO trades"))
        db_session.execute(text("CREATE INDEX IF NOT EXISTS ix_trades_id ON trades (id)"))
        db_session.execute(text("CREATE INDEX IF NOT EXISTS ix_trades_ticker ON trades (ticker)"))
        db_session.execute(
            text("CREATE INDEX IF NOT EXISTS ix_trades_setup_id ON trades (setup_id)")
        )
        db_session.execute(
            text("CREATE INDEX IF NOT EXISTS ix_trades_emotion_id ON trades (emotion_id)")
        )
        db_session.execute(
            text("CREATE INDEX IF NOT EXISTS ix_trades_import_batch_id ON trades (import_batch_id)")
        )
        db_session.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_trades_source_source_id "
                "ON trades (source, source_id)"
            )
        )
    finally:
        db_session.execute(text("PRAGMA foreign_keys=ON"))


def _migrate_trade_classification_columns_nullable(db_session: Session) -> None:
    if not _table_exists(db_session, "trades"):
        return
    if not _is_column_not_null(db_session, "trades", "setup_id") and not _is_column_not_null(
        db_session, "trades", "emotion_id"
    ):
        return

    db_session.execute(text("PRAGMA foreign_keys=OFF"))
    try:
        db_session.execute(
            text(
                """
                CREATE TABLE trades__classification_nullable (
                    id INTEGER PRIMARY KEY,
                    date DATE NOT NULL,
                    ticker VARCHAR(16) NOT NULL,
                    direction VARCHAR(16) NOT NULL,
                    entry_price FLOAT NOT NULL,
                    exit_price FLOAT NOT NULL,
                    pnl FLOAT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    contract_multiplier INTEGER NOT NULL DEFAULT 100,
                    total_pnl_usd FLOAT NOT NULL DEFAULT 0,
                    setup_id INTEGER,
                    emotion_id INTEGER,
                    rule_followed BOOLEAN,
                    notes TEXT,
                    entry_time TIME,
                    exit_time TIME,
                    duration_seconds INTEGER,
                    source VARCHAR(32),
                    source_id VARCHAR(64),
                    import_batch_id INTEGER
                )
                """
            )
        )
        db_session.execute(
            text(
                """
                INSERT INTO trades__classification_nullable (
                    id, date, ticker, direction, entry_price, exit_price, pnl,
                    quantity, contract_multiplier, total_pnl_usd,
                    setup_id, emotion_id, rule_followed, notes,
                    entry_time, exit_time, duration_seconds, source, source_id, import_batch_id
                )
                SELECT
                    id, date, ticker, direction, entry_price, exit_price, pnl,
                    quantity, contract_multiplier, total_pnl_usd,
                    setup_id, emotion_id, rule_followed, notes,
                    entry_time, exit_time, duration_seconds, source, source_id, import_batch_id
                FROM trades
                """
            )
        )
        db_session.execute(text("DROP TABLE trades"))
        db_session.execute(text("ALTER TABLE trades__classification_nullable RENAME TO trades"))
        db_session.execute(text("CREATE INDEX IF NOT EXISTS ix_trades_id ON trades (id)"))
        db_session.execute(text("CREATE INDEX IF NOT EXISTS ix_trades_ticker ON trades (ticker)"))
        db_session.execute(
            text("CREATE INDEX IF NOT EXISTS ix_trades_setup_id ON trades (setup_id)")
        )
        db_session.execute(
            text("CREATE INDEX IF NOT EXISTS ix_trades_emotion_id ON trades (emotion_id)")
        )
        db_session.execute(
            text("CREATE INDEX IF NOT EXISTS ix_trades_import_batch_id ON trades (import_batch_id)")
        )
        db_session.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_trades_source_source_id "
                "ON trades (source, source_id)"
            )
        )
    finally:
        db_session.execute(text("PRAGMA foreign_keys=ON"))


def _migrate_trade_pnl_quantity_columns(db_session: Session) -> None:
    if not _table_exists(db_session, "trades"):
        return

    columns = _get_table_columns(db_session, "trades")
    if "quantity" not in columns:
        db_session.execute(text("ALTER TABLE trades ADD COLUMN quantity INTEGER DEFAULT 1"))
    if "contract_multiplier" not in columns:
        db_session.execute(
            text("ALTER TABLE trades ADD COLUMN contract_multiplier INTEGER DEFAULT 100")
        )
    if "total_pnl_usd" not in columns:
        db_session.execute(text("ALTER TABLE trades ADD COLUMN total_pnl_usd FLOAT DEFAULT 0"))

    db_session.execute(
        text(
            """
            UPDATE trades
            SET
                quantity = COALESCE(quantity, 1),
                contract_multiplier = COALESCE(contract_multiplier, 100),
                total_pnl_usd = (
                    COALESCE(pnl, 0) * COALESCE(quantity, 1) * COALESCE(contract_multiplier, 100)
                )
            """
        )
    )


def _migrate_trade_source_columns(db_session: Session) -> None:
    if not _table_exists(db_session, "trades"):
        return

    columns = _get_table_columns(db_session, "trades")
    if "source" not in columns:
        db_session.execute(text("ALTER TABLE trades ADD COLUMN source VARCHAR(32)"))
    if "source_id" not in columns:
        db_session.execute(text("ALTER TABLE trades ADD COLUMN source_id VARCHAR(64)"))

    db_session.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_trades_source_source_id "
            "ON trades (source, source_id)"
        )
    )


def _migrate_trade_time_columns(db_session: Session) -> None:
    if not _table_exists(db_session, "trades"):
        return

    columns = _get_table_columns(db_session, "trades")
    if "entry_time" not in columns:
        db_session.execute(text("ALTER TABLE trades ADD COLUMN entry_time TIME"))
    if "exit_time" not in columns:
        db_session.execute(text("ALTER TABLE trades ADD COLUMN exit_time TIME"))
    if "duration_seconds" not in columns:
        db_session.execute(text("ALTER TABLE trades ADD COLUMN duration_seconds INTEGER"))

    db_session.execute(
        text(
            """
            UPDATE trades
            SET duration_seconds = CAST(
                strftime('%s', '1970-01-01 ' || exit_time)
                - strftime('%s', '1970-01-01 ' || entry_time)
                AS INTEGER
            )
            WHERE duration_seconds IS NULL
              AND entry_time IS NOT NULL
              AND exit_time IS NOT NULL
              AND exit_time >= entry_time
            """
        )
    )


def _migrate_trade_import_batch_column(db_session: Session) -> None:
    if not _table_exists(db_session, "trades"):
        return

    columns = _get_table_columns(db_session, "trades")
    if "import_batch_id" not in columns:
        db_session.execute(text("ALTER TABLE trades ADD COLUMN import_batch_id INTEGER"))

    db_session.execute(
        text("CREATE INDEX IF NOT EXISTS ix_trades_import_batch_id ON trades (import_batch_id)")
    )


def _migrate_trade_fills_table(db_session: Session) -> None:
    db_session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS trade_fills (
                id INTEGER PRIMARY KEY,
                trade_id INTEGER NOT NULL,
                filled_at DATETIME,
                side VARCHAR(16) NOT NULL,
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                price FLOAT NOT NULL CHECK (price >= 0),
                source VARCHAR(32),
                source_id VARCHAR(64),
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                FOREIGN KEY (trade_id) REFERENCES trades(id) ON DELETE CASCADE
            )
            """
        )
    )
    db_session.execute(
        text("CREATE INDEX IF NOT EXISTS ix_trade_fills_trade_id ON trade_fills (trade_id)")
    )
    db_session.execute(
        text("CREATE INDEX IF NOT EXISTS ix_trade_fills_filled_at ON trade_fills (filled_at)")
    )


def _migrate_import_batch_indexes(db_session: Session) -> None:
    if not _table_exists(db_session, "import_batches"):
        return

    db_session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_import_batches_created_at_desc "
            "ON import_batches (created_at DESC)"
        )
    )
    db_session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_import_batches_source_file_hash "
            "ON import_batches (source, file_hash)"
        )
    )


def _migrate_import_batch_payload_columns(db_session: Session) -> None:
    if not _table_exists(db_session, "import_batches"):
        return

    columns = _get_table_columns(db_session, "import_batches")
    if "matched_pairs_count" not in columns:
        db_session.execute(
            text(
                "ALTER TABLE import_batches "
                "ADD COLUMN matched_pairs_count INTEGER NOT NULL DEFAULT 0"
            )
        )
    if "unmatched_opens_count" not in columns:
        db_session.execute(
            text(
                "ALTER TABLE import_batches "
                "ADD COLUMN unmatched_opens_count INTEGER NOT NULL DEFAULT 0"
            )
        )
    if "unmatched_closes_count" not in columns:
        db_session.execute(
            text(
                "ALTER TABLE import_batches "
                "ADD COLUMN unmatched_closes_count INTEGER NOT NULL DEFAULT 0"
            )
        )
    if "fills_json" not in columns:
        db_session.execute(text("ALTER TABLE import_batches ADD COLUMN fills_json TEXT"))
    if "unmatched_opens_json" not in columns:
        db_session.execute(text("ALTER TABLE import_batches ADD COLUMN unmatched_opens_json TEXT"))
    if "unmatched_closes_json" not in columns:
        db_session.execute(text("ALTER TABLE import_batches ADD COLUMN unmatched_closes_json TEXT"))


def migrate_legacy_schema() -> None:
    with SessionLocal() as db_session:
        if _table_exists(db_session, "setup_options"):
            _seed_default_setup_options(db_session)
            _migrate_trades_setup_column(db_session)

        if _table_exists(db_session, "emotion_options"):
            _seed_default_emotion_options(db_session)
            _migrate_trades_emotion_column(db_session)

        _rebuild_trades_table_with_fk_columns(db_session)
        _migrate_trade_pnl_quantity_columns(db_session)
        _migrate_trade_source_columns(db_session)
        _migrate_trade_time_columns(db_session)
        _migrate_trade_import_batch_column(db_session)
        _migrate_trade_classification_columns_nullable(db_session)
        _migrate_trade_rule_followed_nullable(db_session)
        _migrate_trade_fills_table(db_session)
        _migrate_import_batch_payload_columns(db_session)
        _migrate_import_batch_indexes(db_session)
        db_session.commit()


def create_db_and_tables() -> None:
    # Ensure model modules are imported before create_all so metadata is populated.
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    migrate_legacy_schema()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
