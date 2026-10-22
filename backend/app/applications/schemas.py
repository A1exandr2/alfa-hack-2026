from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ApplicationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    requested_amount: Decimal = Field(
        gt=Decimal("0"), max_digits=15, decimal_places=2
    )
    term_months: int = Field(gt=0)
    purpose: str = Field(min_length=1, max_length=500)

    @field_validator("purpose")
    @classmethod
    def normalize_purpose(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Purpose cannot be blank")
        return value


class ApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    product_id: UUID
    requested_amount: Decimal
    term_months: int
    purpose: str
    status: str
    created_at: datetime
    updated_at: datetime


class ApplicationUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID | None = None
    requested_amount: Decimal | None = Field(
        default=None,
        gt=Decimal("0"),
        max_digits=15,
        decimal_places=2,
    )
    term_months: int | None = Field(default=None, gt=0)
    purpose: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("purpose")
    @classmethod
    def normalize_purpose(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Purpose cannot be blank")
        return value

    @model_validator(mode="after")
    def validate_changes(self) -> "ApplicationUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one application field must be provided")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Application fields cannot be null")
        return self


class ApplicationEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sequence: int
    event_type: str
    from_status: str | None
    to_status: str | None
    actor_type: str
    actor_user_id: UUID | None
    occurred_at: datetime
    details: dict[str, object]
