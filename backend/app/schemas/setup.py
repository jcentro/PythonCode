from pydantic import BaseModel, ConfigDict, Field


class SetupOptionCreate(BaseModel):
    name: str = Field(min_length=1)
    is_active: bool = True
    sort_order: int | None = None


class SetupOptionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    is_active: bool | None = None
    sort_order: int | None = None


class SetupOptionRead(BaseModel):
    id: int
    name: str
    is_active: bool
    sort_order: int | None

    model_config = ConfigDict(from_attributes=True)
