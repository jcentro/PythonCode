from datetime import UTC, datetime
from math import isfinite
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.emotion_option import EmotionOption
from app.models.setup_option import SetupOption
from app.models.trade import Trade
from app.models.trade_fill import TradeFill
from app.schemas.backup import BackupImportCounts, BackupImportRequest, BackupImportResponse

router = APIRouter(prefix="/api/backup", tags=["backup"])

SUPPORTED_BACKUP_SCHEMA_VERSION = 1


def _raise_backup_error(detail: str) -> None:
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


def _validate_unique_ids(values: list[int], field_name: str) -> None:
    if len(values) != len(set(values)):
        _raise_backup_error(f"{field_name} contains duplicate ids")


def _humanize_field_name(field_name: str) -> str:
    return field_name.replace("_", " ")


def _format_validation_error(exc: ValidationError) -> str:
    first_error = exc.errors()[0]
    location = list(first_error.get("loc", ()))
    message = first_error.get("msg", "is invalid")

    if location[:2] == ["data", "trades"] and len(location) >= 3 and isinstance(location[2], int):
        trade_index = location[2]
        if (
            len(location) >= 5
            and location[3] == "fills"
            and isinstance(location[4], int)
        ):
            fill_index = location[4]
            field_name = _humanize_field_name(str(location[5])) if len(location) >= 6 else "fill"
            return (
                f"Invalid fill at trade index {trade_index}, fill index {fill_index}: "
                f"{field_name} {message}."
            )
        field_name = _humanize_field_name(str(location[3])) if len(location) >= 4 else "trade"
        return f"Invalid trade at index {trade_index}: {field_name} {message}."

    if location[:2] == ["data", "setups"] and len(location) >= 3 and isinstance(location[2], int):
        setup_index = location[2]
        field_name = _humanize_field_name(str(location[3])) if len(location) >= 4 else "setup"
        return f"Invalid setup at index {setup_index}: {field_name} {message}."

    if location[:2] == ["data", "emotions"] and len(location) >= 3 and isinstance(location[2], int):
        emotion_index = location[2]
        field_name = _humanize_field_name(str(location[3])) if len(location) >= 4 else "emotion"
        return f"Invalid emotion at index {emotion_index}: {field_name} {message}."

    if location and location[0] == "schema_version":
        return f"Invalid schema_version: {message}."
    if location and location[0] == "exported_at":
        return f"Invalid exported_at: {message}."
    return "Invalid backup file format."


def _parse_backup_payload(raw_payload: Any) -> BackupImportRequest:
    if not isinstance(raw_payload, dict):
        _raise_backup_error("Backup file must be a JSON object.")

    schema_version = raw_payload.get("schema_version")
    if schema_version is None:
        _raise_backup_error("Missing schema_version.")
    if not isinstance(schema_version, int):
        _raise_backup_error("Invalid schema_version.")
    if schema_version != SUPPORTED_BACKUP_SCHEMA_VERSION:
        _raise_backup_error(
            "Unsupported backup version: "
            f"{schema_version}. Expected {SUPPORTED_BACKUP_SCHEMA_VERSION}."
        )

    data = raw_payload.get("data")
    if not isinstance(data, dict):
        _raise_backup_error("Missing data object.")
    if not isinstance(data.get("trades"), list):
        _raise_backup_error("Missing trades array.")
    if not isinstance(data.get("setups"), list):
        _raise_backup_error("Missing setups array.")
    if not isinstance(data.get("emotions"), list):
        _raise_backup_error("Missing emotions array.")

    normalized_payload = {
        "schema_version": schema_version,
        "exported_at": raw_payload.get("exported_at") or datetime.now(UTC).isoformat(),
        "data": data,
    }

    try:
        return BackupImportRequest.model_validate(normalized_payload)
    except ValidationError as exc:
        _raise_backup_error(_format_validation_error(exc))


def _validate_backup_payload(payload: BackupImportRequest) -> None:
    setup_ids = [setup.id for setup in payload.data.setups]
    emotion_ids = [emotion.id for emotion in payload.data.emotions]
    trade_ids = [trade.id for trade in payload.data.trades]

    _validate_unique_ids(setup_ids, "setups")
    _validate_unique_ids(emotion_ids, "emotions")
    _validate_unique_ids(trade_ids, "trades")

    setup_id_set = set(setup_ids)
    emotion_id_set = set(emotion_ids)

    for setup in payload.data.setups:
        if not setup.name.strip():
            _raise_backup_error(f"Setup {setup.id} has an empty name")

    for emotion in payload.data.emotions:
        if not emotion.name.strip():
            _raise_backup_error(f"Emotion {emotion.id} has an empty name")

    for index, trade in enumerate(payload.data.trades):
        if not trade.ticker.strip():
            _raise_backup_error(f"Invalid trade at index {index}: ticker is required.")
        if not isfinite(trade.entry_price) or trade.entry_price <= 0:
            _raise_backup_error(
                f"Invalid trade at index {index}: entry price must be greater than zero."
            )
        if not isfinite(trade.exit_price) or trade.exit_price <= 0:
            _raise_backup_error(
                f"Invalid trade at index {index}: exit price must be greater than zero."
            )
        if not isfinite(trade.pnl):
            _raise_backup_error(f"Invalid trade at index {index}: pnl must be finite.")
        if not isfinite(trade.total_pnl_usd):
            _raise_backup_error(f"Invalid trade at index {index}: total pnl usd must be finite.")
        if trade.setup_id is not None and trade.setup_id not in setup_id_set:
            _raise_backup_error(
                f"Invalid trade at index {index}: references missing setup_id {trade.setup_id}."
            )
        if trade.emotion_id is not None and trade.emotion_id not in emotion_id_set:
            _raise_backup_error(
                f"Invalid trade at index {index}: references missing emotion_id {trade.emotion_id}."
            )
        for fill_index, fill in enumerate(trade.fills):
            if not isfinite(fill.price) or fill.price <= 0:
                _raise_backup_error(
                    f"Invalid fill at trade index {index}, fill index {fill_index}: "
                    "price must be greater than zero."
                )
            if fill.quantity <= 0:
                _raise_backup_error(
                    f"Invalid fill at trade index {index}, fill index {fill_index}: "
                    "quantity must be greater than zero."
                )


@router.post("/import", response_model=BackupImportResponse)
def import_backup(payload: dict[str, Any], db: Session = Depends(get_db)) -> BackupImportResponse:
    parsed_payload = _parse_backup_payload(payload)
    _validate_backup_payload(parsed_payload)

    fill_count = sum(len(trade.fills) for trade in parsed_payload.data.trades)

    try:
        with db.begin():
            db.query(TradeFill).delete(synchronize_session=False)
            db.query(Trade).delete(synchronize_session=False)
            db.query(SetupOption).delete(synchronize_session=False)
            db.query(EmotionOption).delete(synchronize_session=False)

            for setup in parsed_payload.data.setups:
                db.add(
                    SetupOption(
                        id=setup.id,
                        name=setup.name.strip(),
                        is_active=setup.is_active,
                        sort_order=setup.sort_order,
                    )
                )

            for emotion in parsed_payload.data.emotions:
                db.add(
                    EmotionOption(
                        id=emotion.id,
                        name=emotion.name.strip(),
                        is_active=emotion.is_active,
                        sort_order=emotion.sort_order,
                    )
                )

            for trade in parsed_payload.data.trades:
                trade_model = Trade(
                    id=trade.id,
                    date=trade.date,
                    ticker=trade.ticker.strip().upper(),
                    direction=trade.direction,
                    entry_price=trade.entry_price,
                    exit_price=trade.exit_price,
                    pnl=trade.pnl,
                    quantity=trade.quantity,
                    contract_multiplier=trade.contract_multiplier,
                    total_pnl_usd=trade.total_pnl_usd,
                    setup_id=trade.setup_id,
                    emotion_id=trade.emotion_id,
                    rule_followed=trade.rule_followed,
                    notes=trade.notes,
                    entry_time=trade.entry_time,
                    exit_time=trade.exit_time,
                    duration_seconds=trade.duration_seconds,
                    source=trade.source,
                    source_id=trade.source_id,
                    import_batch_id=None,
                )
                db.add(trade_model)

                for fill in trade.fills:
                    db.add(
                        TradeFill(
                            trade_id=trade.id,
                            filled_at=fill.filled_at,
                            side=fill.side,
                            quantity=fill.quantity,
                            price=fill.price,
                            source=fill.source,
                            source_id=fill.source_id,
                        )
                    )
    except IntegrityError:
        db.rollback()
        _raise_backup_error("Invalid backup data. Import aborted.")

    return BackupImportResponse(
        status="ok",
        imported=BackupImportCounts(
            trades=len(parsed_payload.data.trades),
            fills=fill_count,
            setups=len(parsed_payload.data.setups),
            emotions=len(parsed_payload.data.emotions),
        ),
    )
