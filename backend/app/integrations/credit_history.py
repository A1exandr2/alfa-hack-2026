from decimal import Decimal
from datetime import datetime
import os
from typing import Protocol

from pydantic import BaseModel, Field


class CreditHistoryData(BaseModel):
    active_credits: int | None = Field(default=None, ge=0)
    closed_credits: int | None = Field(default=None, ge=0)
    overdue_count: int | None = Field(default=None, ge=0)
    overdue_amount: Decimal | None = Field(default=None, ge=Decimal("0"))
    source: str = Field(min_length=1, max_length=32)
    as_of: datetime | None = None
    consent_id: str | None = None


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


class UnavailableCreditHistoryProvider:
    async def get_by_inn(self, inn: str) -> CreditHistoryData:
        return CreditHistoryData(source="UNAVAILABLE")


def get_credit_history_provider() -> CreditHistoryProvider:
    if os.getenv("DATA_MODE", "real") == "demo":
        return DemoCreditHistoryProvider()
    url, token = os.getenv("CREDIT_HISTORY_API_URL", "").strip(), os.getenv("CREDIT_HISTORY_API_TOKEN", "").strip()
    return GatewayCreditHistoryProvider(url, token) if url and token else UnavailableCreditHistoryProvider()


class GatewayCreditHistoryProvider:
    """Adapter for an organization's BKI gateway, not an undocumented bureau API.

    The configured HTTPS endpoint implements our normalized report contract.
    A valid consent id must be attached by the authenticated backend first.
    """
    requires_consent = True

    def __init__(self, url: str, token: str, consent_id: str | None = None, transport=None):
        from urllib.parse import urlsplit
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.fragment:
            raise ValueError("Credit history gateway must use HTTPS without URL credentials")
        self.url, self.token, self.consent_id, self.transport = url, token, consent_id, transport

    async def get_by_inn(self, inn: str) -> CreditHistoryData:
        import httpx
        from datetime import datetime, timezone
        if not self.consent_id:
            raise CreditHistoryProviderError("Credit history consent is required")
        try:
            async with httpx.AsyncClient(timeout=20, transport=self.transport, follow_redirects=False) as client:
                response = await client.post(self.url, headers={"Authorization": f"Bearer {self.token}"},
                    json={"schema_version":1,"inn":inn,"consent_id":self.consent_id,"purpose":"credit_application"})
                response.raise_for_status()
                body = response.json()
                if body.get("inn") != inn:
                    raise ValueError("Mismatched company INN")
                as_of = datetime.fromisoformat(body["as_of"].replace("Z", "+00:00"))
                if as_of.tzinfo is None or as_of > datetime.now(timezone.utc):
                    raise ValueError("Invalid report timestamp")
                return CreditHistoryData(**{f:body.get(f) for f in ("active_credits","closed_credits","overdue_count","overdue_amount")},
                    source="BKI_GATEWAY", as_of=as_of, consent_id=self.consent_id)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            raise CreditHistoryProviderError("Credit history gateway unavailable") from error
