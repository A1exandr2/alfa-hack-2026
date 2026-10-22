from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True)
class CompanyData:
    name: str
    inn: str
    ogrn: str | None = None
    registration_date: date | None = None
    status: str = "ACTIVE"
    director_name: str | None = None
    okved: str | None = None
    data_source: str = "DEMO"


class CompanyProviderError(Exception):
    """Raised when a company provider cannot return company data."""


class CompanyProvider(Protocol):
    async def get_by_inn(self, inn: str) -> CompanyData: ...


class DemoCompanyProvider:
    async def get_by_inn(self, inn: str) -> CompanyData:
        return CompanyData(
            name=f"Демо-компания {inn}",
            inn=inn,
            data_source="DEMO",
        )


def get_company_provider() -> CompanyProvider:
    return DemoCompanyProvider()
