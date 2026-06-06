from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.emotion_option import EmotionOption
from app.schemas.emotion import EmotionOptionCreate, EmotionOptionRead, EmotionOptionUpdate

router = APIRouter(prefix="/api/emotions", tags=["emotions"])


@router.get("", response_model=list[EmotionOptionRead])
def list_emotions(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[EmotionOption]:
    stmt = select(EmotionOption)
    if not include_inactive:
        stmt = stmt.where(EmotionOption.is_active.is_(True))
    stmt = stmt.order_by(
        EmotionOption.sort_order.is_(None),
        EmotionOption.sort_order,
        EmotionOption.name,
    )
    return list(db.scalars(stmt).all())


@router.post("", response_model=EmotionOptionRead, status_code=status.HTTP_201_CREATED)
def create_emotion(payload: EmotionOptionCreate, db: Session = Depends(get_db)) -> EmotionOption:
    normalized_name = payload.name.strip()
    if not normalized_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Name is required"
        )

    existing_emotion = db.scalar(
        select(EmotionOption).where(func.lower(EmotionOption.name) == normalized_name.lower())
    )
    if existing_emotion is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Emotion '{normalized_name}' already exists",
        )

    emotion_option = EmotionOption(
        name=normalized_name,
        is_active=payload.is_active,
        sort_order=payload.sort_order,
    )
    db.add(emotion_option)
    db.commit()
    db.refresh(emotion_option)
    return emotion_option


@router.patch("/{emotion_id}", response_model=EmotionOptionRead)
def update_emotion(
    emotion_id: int,
    payload: EmotionOptionUpdate,
    db: Session = Depends(get_db),
) -> EmotionOption:
    emotion_option = db.get(EmotionOption, emotion_id)
    if emotion_option is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Emotion not found")

    fields_set = payload.model_fields_set
    if not fields_set:
        return emotion_option

    if "name" in fields_set:
        normalized_name = (payload.name or "").strip()
        if not normalized_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Name is required",
            )

        existing_emotion = db.scalar(
            select(EmotionOption).where(
                func.lower(EmotionOption.name) == normalized_name.lower(),
                EmotionOption.id != emotion_option.id,
            )
        )
        if existing_emotion is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Emotion '{normalized_name}' already exists",
            )
        emotion_option.name = normalized_name

    if "is_active" in fields_set:
        if payload.is_active is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="is_active must be true or false",
            )
        emotion_option.is_active = payload.is_active

    if "sort_order" in fields_set:
        emotion_option.sort_order = payload.sort_order

    db.commit()
    db.refresh(emotion_option)
    return emotion_option
