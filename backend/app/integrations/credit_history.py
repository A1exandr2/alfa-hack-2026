from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, Field


class CreditHistoryData(BaseModel):
    active_credits: int = Field(ge=0)
    closed_credits: int = Field(ge=0)
    overdue_count: int = Field(ge=0)
    overdue_amount: Decimal = Field(ge=Decimal("0"))
    source: str = Field(min_length=1, max_length=32)


class CreditHistoryProviderError(Exception):
    """Raised when a credit-history provider cannot return company data."""


class CreditHistoryProvider(Protocol):
    async def get_by_inn(self, inn: str) -> CreditHistoryData: ...


class DemoCreditHistoryProvider:
    async def get_by_inn(self, inn: str) -> CreditHistoryData:
        return CreditHistoryData(
            active_credits=2,
            closed_credits=5,
            overdue_count=0,
            overdue_amount=Decimal("0.00"),
            source="DEMO",
        )


def get_credit_history_provider() -> CreditHistoryProvider:
    return DemoCreditHistoryProvider()
