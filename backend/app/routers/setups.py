from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.setup_option import SetupOption
from app.schemas.setup import SetupOptionCreate, SetupOptionRead, SetupOptionUpdate

router = APIRouter(prefix="/api/setups", tags=["setups"])


@router.get("", response_model=list[SetupOptionRead])
def list_setups(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[SetupOption]:
    stmt = select(SetupOption)
    if not include_inactive:
        stmt = stmt.where(SetupOption.is_active.is_(True))
    stmt = stmt.order_by(
        SetupOption.sort_order.is_(None),
        SetupOption.sort_order,
        SetupOption.name,
    )
    return list(db.scalars(stmt).all())


@router.post("", response_model=SetupOptionRead, status_code=status.HTTP_201_CREATED)
def create_setup(payload: SetupOptionCreate, db: Session = Depends(get_db)) -> SetupOption:
    normalized_name = payload.name.strip()
    if not normalized_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Name is required"
        )

    existing_setup = db.scalar(
        select(SetupOption).where(func.lower(SetupOption.name) == normalized_name.lower())
    )
    if existing_setup is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Setup '{normalized_name}' already exists",
        )

    setup_option = SetupOption(
        name=normalized_name,
        is_active=payload.is_active,
        sort_order=payload.sort_order,
    )
    db.add(setup_option)
    db.commit()
    db.refresh(setup_option)
    return setup_option


@router.patch("/{setup_id}", response_model=SetupOptionRead)
def update_setup(
    setup_id: int,
    payload: SetupOptionUpdate,
    db: Session = Depends(get_db),
) -> SetupOption:
    setup_option = db.get(SetupOption, setup_id)
    if setup_option is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Setup not found")

    fields_set = payload.model_fields_set
    if not fields_set:
        return setup_option

    if "name" in fields_set:
        normalized_name = (payload.name or "").strip()
        if not normalized_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Name is required",
            )

        existing_setup = db.scalar(
            select(SetupOption).where(
                func.lower(SetupOption.name) == normalized_name.lower(),
                SetupOption.id != setup_option.id,
            )
        )
        if existing_setup is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Setup '{normalized_name}' already exists",
            )
        setup_option.name = normalized_name

    if "is_active" in fields_set:
        if payload.is_active is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="is_active must be true or false",
            )
        setup_option.is_active = payload.is_active

    if "sort_order" in fields_set:
        setup_option.sort_order = payload.sort_order

    db.commit()
    db.refresh(setup_option)
    return setup_option
