from datetime import datetime, timezone
from sqlalchemy import select
from app.models import CreditHistoryConsent, CreditHistory
from app.integrations.credit_history import GatewayCreditHistoryProvider


async def active_consent(session, user_id, company_id):
    return await session.scalar(select(CreditHistoryConsent).where(
        CreditHistoryConsent.user_id == user_id,
        CreditHistoryConsent.company_id == company_id,
        CreditHistoryConsent.revoked_at.is_(None),
        CreditHistoryConsent.expires_at > datetime.now(timezone.utc),
    ).order_by(CreditHistoryConsent.granted_at.desc()).limit(1))


async def authorized_provider(session, user_id, company_id, provider):
    if not getattr(provider, "requires_consent", False):
        return provider
    consent = await active_consent(session, user_id, company_id)
    if consent is None:
        return None
    return GatewayCreditHistoryProvider(provider.url, provider.token, str(consent.id), provider.transport)


def unknown_history(company_id):
    return CreditHistory(company_id=company_id, source="CONSENT_REQUIRED", field_sources={},
        updated_at=None)
