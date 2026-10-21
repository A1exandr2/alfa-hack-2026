from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LinkCompanyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inn: str = Field(pattern=r"^\d{10}(\d{2})?$", min_length=10, max_length=12)

    @field_validator("inn", mode="before")
    @classmethod
    def normalize_inn(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class CompanyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    inn: str
    ogrn: str | None
    registration_date: date | None
    status: str
    director_name: str | None
    okved: str | None
    data_source: str


class FinancialsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    revenue_annual: float
    profit_annual: float
    expenses_annual: float
    employees: int
    current_debt: float
    updated_at: datetime
    source: str


class FinancialsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revenue_annual: Decimal | None = Field(default=None, ge=Decimal("0"))
    profit_annual: Decimal | None = None
    expenses_annual: Decimal | None = Field(default=None, ge=Decimal("0"))
    employees: int | None = Field(default=None, ge=0)
    current_debt: Decimal | None = Field(default=None, ge=Decimal("0"))

    @model_validator(mode="after")
    def validate_changes(self) -> "FinancialsUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one financial field must be provided")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Financial fields cannot be null")
        return self
