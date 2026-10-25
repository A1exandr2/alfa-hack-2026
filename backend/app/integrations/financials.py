from decimal import Decimal
import os
import httpx
from typing import Protocol

from pydantic import BaseModel, Field


class FinancialData(BaseModel):
    revenue_annual: Decimal | None = Field(default=None, ge=Decimal("0"))
    profit_annual: Decimal | None = None
    expenses_annual: Decimal | None = Field(default=None, ge=Decimal("0"))
    employees: int | None = Field(default=None, ge=0)
    current_debt: Decimal | None = Field(default=None, ge=Decimal("0"))
    source: str = Field(min_length=1, max_length=32)
    report_year: int | None = None


class FinancialProviderError(Exception):
    """Raised when a financial provider cannot return company data."""


class FinancialProvider(Protocol):
    async def get_by_inn(self, inn: str) -> FinancialData: ...


class DemoFinancialProvider:
    async def get_by_inn(self, inn: str) -> FinancialData:
        return FinancialData(
            revenue_annual=Decimal("12500000.00"),
            profit_annual=Decimal("2100000.00"),
            expenses_annual=Decimal("10400000.00"),
            employees=8,
            current_debt=Decimal("800000.00"),
            source="DEMO",
        )


class DadataFinancialProvider:
    def __init__(self, token, transport=None):
        self.token, self.transport = token, transport

    async def get_by_inn(self, inn: str) -> FinancialData:
        try:
            async with httpx.AsyncClient(timeout=20, transport=self.transport) as client:
                response = await client.post(
                    "https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party",
                    headers={"Authorization": f"Token {self.token}"},
                    json={"query": inn, "branch_type": "MAIN", "count": 1})
                response.raise_for_status()
                results = response.json().get("suggestions", [])
                if not results or results[0]["data"].get("inn") != inn:
                    raise FinancialProviderError("Company not found")
                data = results[0]["data"]
                finance = data.get("finance") or {}
                # income is not revenue; tax debt is not outstanding loan debt.
                # No estimate of net profit is fabricated from income/expenses.
                return FinancialData(revenue_annual=finance.get("revenue"),
                    expenses_annual=finance.get("expense"), employees=data.get("employee_count"),
                    report_year=finance.get("year"), source="DADATA")
        except FinancialProviderError:
            raise
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise FinancialProviderError("Financial registry unavailable") from error


class UnavailableFinancialProvider:
    async def get_by_inn(self, inn: str) -> FinancialData:
        return FinancialData(source="UNAVAILABLE")


def get_financial_provider() -> FinancialProvider:
    token = os.getenv("DADATA_API_KEY", "").strip()
    if os.getenv("DATA_MODE", "real") == "demo":
        return DemoFinancialProvider()
    return DadataFinancialProvider(token) if token else UnavailableFinancialProvider()
