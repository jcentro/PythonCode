from pydantic import BaseModel, ConfigDict, Field


class EmotionOptionCreate(BaseModel):
    name: str = Field(min_length=1)
    is_active: bool = True
    sort_order: int | None = None


class EmotionOptionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    is_active: bool | None = None
    sort_order: int | None = None


class EmotionOptionRead(BaseModel):
    id: int
    name: str
    is_active: bool
    sort_order: int | None

    model_config = ConfigDict(from_attributes=True)
