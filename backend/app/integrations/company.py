from dataclasses import dataclass
from datetime import date, datetime, timezone
import os

import httpx
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
    full_name: str | None = None
    kpp: str | None = None
    address: str | None = None


class CompanyProviderError(Exception):
    """Raised when a company provider cannot return company data."""


class CompanyNotFoundError(CompanyProviderError):
    pass


class CompanyProvider(Protocol):
    async def get_by_inn(self, inn: str) -> CompanyData: ...


class DemoCompanyProvider:
    async def get_by_inn(self, inn: str) -> CompanyData:
        return CompanyData(
            name=f"Демо-компания {inn}",
            inn=inn,
            # Explicit synthetic fixture, not a fetched registry date.
            registration_date=date(2019, 1, 1),
            data_source="DEMO",
        )


class DadataCompanyProvider:
    def __init__(self, token: str, transport=None):
        self.token = token
        self.transport = transport

    async def get_by_inn(self, inn: str) -> CompanyData:
        try:
            async with httpx.AsyncClient(timeout=15, transport=self.transport) as client:
                response = await client.post(
                    "https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party",
                    headers={"Authorization": f"Token {self.token}", "Accept": "application/json"},
                    json={"query": inn, "branch_type": "MAIN", "count": 1},
                )
                response.raise_for_status()
                suggestions = response.json().get("suggestions", [])
                if not suggestions:
                    raise CompanyNotFoundError()
                item = suggestions[0]
                data = item["data"]
                if data.get("inn") != inn:
                    raise CompanyProviderError("Mismatched INN")
                state = data.get("state") or {}
                registered = state.get("registration_date")
                names = data.get("name") or {}
                return CompanyData(
                    name=names.get("short_with_opf") or item["value"],
                    inn=inn, ogrn=data.get("ogrn"),
                    registration_date=datetime.fromtimestamp(registered / 1000, tz=timezone.utc).date() if registered else None,
                    status=state.get("status") or "UNKNOWN",
                    director_name=(data.get("management") or {}).get("name"),
                    okved=data.get("okved"), data_source="DADATA",
                    full_name=names.get("full_with_opf"), kpp=data.get("kpp"),
                    address=(data.get("address") or {}).get("unrestricted_value") or (data.get("address") or {}).get("value"),
                )
        except CompanyProviderError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError, OverflowError) as error:
            raise CompanyProviderError("Company registry unavailable") from error


def get_company_provider() -> CompanyProvider:
    token = os.getenv("DADATA_API_KEY", "").strip()
    return DadataCompanyProvider(token) if token else DemoCompanyProvider()
