from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, Field


class FinancialData(BaseModel):
    revenue_annual: Decimal = Field(ge=Decimal("0"))
    profit_annual: Decimal
    expenses_annual: Decimal = Field(ge=Decimal("0"))
    employees: int = Field(ge=0)
    current_debt: Decimal = Field(ge=Decimal("0"))
    source: str = Field(min_length=1, max_length=32)


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


def get_financial_provider() -> FinancialProvider:
    return DemoFinancialProvider()
