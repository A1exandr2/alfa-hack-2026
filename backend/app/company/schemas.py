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
    full_name: str | None = None
    kpp: str | None = None
    address: str | None = None


class FinancialsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    revenue_annual: float | None
    profit_annual: float | None
    expenses_annual: float | None
    employees: int | None
    current_debt: float | None
    updated_at: datetime
    source: str
    report_year: int | None = None
    field_sources: dict[str, object] = Field(default_factory=dict)


class CreditHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    active_credits: int | None
    closed_credits: int | None
    overdue_count: int | None
    overdue_amount: float | None
    updated_at: datetime | None
    source: str


    field_sources: dict[str, object] = Field(default_factory=dict)
    report_year: int | None = None
    as_of: datetime | None = None


class FinancialsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_year: int | None = Field(default=None, ge=1900, le=date.today().year)
    revenue_annual: Decimal | None = Field(default=None, ge=Decimal("0"), max_digits=15, decimal_places=2)
    profit_annual: Decimal | None = Field(default=None, max_digits=15, decimal_places=2)
    expenses_annual: Decimal | None = Field(default=None, ge=Decimal("0"), max_digits=15, decimal_places=2)
    employees: int | None = Field(default=None, ge=0, le=2147483647)
    current_debt: Decimal | None = Field(default=None, ge=Decimal("0"), max_digits=15, decimal_places=2)

    @model_validator(mode="after")
    def validate_changes(self) -> "FinancialsUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one financial field must be provided")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Financial fields cannot be null")
        return self

class CreditHistoryUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active_credits: int | None = Field(default=None, ge=0, le=2147483647)
    closed_credits: int | None = Field(default=None, ge=0, le=2147483647)
    overdue_count: int | None = Field(default=None, ge=0, le=2147483647)
    overdue_amount: Decimal | None = Field(default=None, ge=Decimal("0"), max_digits=15, decimal_places=2)

    @model_validator(mode="after")
    def validate_changes(self):
        if not self.model_fields_set or any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Provide at least one non-null credit history field")
        return self


class CreditHistoryConsentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepted: bool
    text_version: str = "credit-report-v1"
