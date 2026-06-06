from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models.import_batch import ImportBatch, ImportBatchStatus


def test_create_and_read_import_batch() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        batch = ImportBatch(
            source="tos_csv",
            original_filename="statement.csv",
            file_hash="a" * 64,
            status=ImportBatchStatus.PREVIEWED,
            parsed_rows_count=42,
            fills_parsed_count=10,
            detected_trades_count=3,
            excluded_count=1,
            warnings_json='["sample warning"]',
            committed_count=0,
            skipped_duplicates_count=0,
            commit_errors_json="[]",
        )
        session.add(batch)
        session.commit()
        session.refresh(batch)

        fetched = session.scalar(select(ImportBatch).where(ImportBatch.id == batch.id))

    assert fetched is not None
    assert fetched.source == "tos_csv"
    assert fetched.original_filename == "statement.csv"
    assert fetched.file_hash == "a" * 64
    assert fetched.status == ImportBatchStatus.PREVIEWED
    assert fetched.created_at is not None
    assert fetched.parsed_rows_count == 42
    assert fetched.fills_parsed_count == 10
    assert fetched.detected_trades_count == 3
    assert fetched.excluded_count == 1
    assert fetched.warnings_json == '["sample warning"]'
    assert fetched.committed_count == 0
    assert fetched.skipped_duplicates_count == 0
    assert fetched.commit_errors_json == "[]"
