import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.import_batch import ImportBatch
from app.models.trade import Trade
from app.schemas.import_batch import ImportBatchDetailRead, ImportBatchListItemRead

router = APIRouter(prefix="/api/import/batches", tags=["import"])


def _parse_json_messages(raw_json: str | None) -> list[str]:
    if not raw_json:
        return []

    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError:
        return []

    if not isinstance(parsed, list):
        return []

    return [str(item) for item in parsed]


def _parse_json_objects(raw_json: str | None) -> list[dict[str, object]]:
    if not raw_json:
        return []

    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError:
        return []

    if not isinstance(parsed, list):
        return []

    items: list[dict[str, object]] = []
    for value in parsed:
        if isinstance(value, dict):
            items.append(value)
    return items


@router.get("", response_model=list[ImportBatchListItemRead])
def list_import_batches(
    source: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[ImportBatchListItemRead]:
    stmt = (
        select(ImportBatch)
        .order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc())
        .limit(limit)
    )
    if source is not None:
        stmt = stmt.where(ImportBatch.source == source)

    batches = list(db.scalars(stmt).all())
    return [
        ImportBatchListItemRead(
            id=batch.id,
            created_at=batch.created_at,
            source=batch.source,
            original_filename=batch.original_filename,
            status=batch.status,
            detected_trades_count=batch.detected_trades_count,
            matched_pairs_count=batch.matched_pairs_count,
            unmatched_opens_count=batch.unmatched_opens_count,
            unmatched_closes_count=batch.unmatched_closes_count,
            committed_count=batch.committed_count,
            skipped_duplicates_count=batch.skipped_duplicates_count,
            warnings_count=len(_parse_json_messages(batch.warnings_json)),
        )
        for batch in batches
    ]


@router.get("/{batch_id}", response_model=ImportBatchDetailRead)
def get_import_batch_detail(batch_id: int, db: Session = Depends(get_db)) -> ImportBatchDetailRead:
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Import batch not found",
        )

    pnl_total_committed_usd = db.execute(
        select(func.coalesce(func.sum(Trade.total_pnl_usd), 0.0)).where(
            Trade.import_batch_id == batch.id
        )
    ).scalar_one()

    fills = _parse_json_objects(batch.fills_json)
    unmatched_opens = _parse_json_objects(batch.unmatched_opens_json)
    unmatched_closes = _parse_json_objects(batch.unmatched_closes_json)

    return ImportBatchDetailRead(
        id=batch.id,
        created_at=batch.created_at,
        source=batch.source,
        original_filename=batch.original_filename,
        file_hash=batch.file_hash,
        status=batch.status,
        parsed_rows_count=batch.parsed_rows_count,
        fills_parsed_count=batch.fills_parsed_count,
        detected_trades_count=batch.detected_trades_count,
        matched_pairs_count=batch.matched_pairs_count,
        unmatched_opens_count=batch.unmatched_opens_count,
        unmatched_closes_count=batch.unmatched_closes_count,
        excluded_count=batch.excluded_count,
        warnings=_parse_json_messages(batch.warnings_json),
        fills_count=len(fills),
        fills=fills,
        unmatched_opens=unmatched_opens,
        unmatched_closes=unmatched_closes,
        committed_count=batch.committed_count,
        skipped_duplicates_count=batch.skipped_duplicates_count,
        errors=_parse_json_messages(batch.commit_errors_json),
        pnl_total_committed_usd=round(float(pnl_total_committed_usd), 2),
    )
