from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
