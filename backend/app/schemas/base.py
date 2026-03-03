"""
Shared Pydantic v2 base schemas and utilities.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    """Base schema with camelCase alias generation disabled (snake_case API)."""

    model_config = ConfigDict(
        from_attributes=True,  # Allow ORM model → schema conversion
        use_enum_values=True,
        populate_by_name=True,
    )


class TimestampMixin(BaseSchema):
    created_at: datetime
    updated_at: datetime | None = None


class UUIDMixin(BaseSchema):
    id: uuid.UUID


class PaginationParams(BaseSchema):
    page: int = 1
    page_size: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PaginatedResponse[T](BaseSchema):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


class MessageResponse(BaseSchema):
    message: str
    success: bool = True
