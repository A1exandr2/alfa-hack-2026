from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest

from app.integrations.financials import DadataFinancialProvider, FinancialProviderError, get_financial_provider
from app.integrations.credit_history import get_credit_history_provider
from app.company.data_quality import missing_fields


@pytest.mark.asyncio
async def test_dadata_mapping_never_invents_profit_or_credit_debt():
    def handle(request):
        assert request.headers['Authorization'] == 'Token test-key'
        return httpx.Response(200, json={'suggestions':[{'data':{'inn':'7707083893','employee_count':12,
            'finance':{'revenue':0,'expense':500,'income':9999,'debt':777,'year':2025}}}]})
    result=await DadataFinancialProvider('test-key',httpx.MockTransport(handle)).get_by_inn('7707083893')
    assert result.revenue_annual == Decimal('0')
    assert result.expenses_annual == Decimal('500')
    assert result.profit_annual is None
    assert result.current_debt is None
    assert result.report_year == 2025
    assert result.employees == 12


@pytest.mark.asyncio
async def test_unavailable_tariff_fields_remain_unknown():
    provider=DadataFinancialProvider('test-key',httpx.MockTransport(lambda req: httpx.Response(200,json={
        'suggestions':[{'data':{'inn':'7325115310','finance':None,'employee_count':None}}]})))
    data=await provider.get_by_inn('7325115310')
    assert data.source=='DADATA'
    assert data.revenue_annual is None and data.employees is None


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [401,403,429,500])
async def test_provider_failure_does_not_fall_back_to_demo(status):
    provider=DadataFinancialProvider('test-key',httpx.MockTransport(lambda req: httpx.Response(status)))
    with pytest.raises(FinancialProviderError):
        await provider.get_by_inn('7325115310')


@pytest.mark.asyncio
async def test_real_mode_without_credentials_has_no_synthetic_finance_or_bki(monkeypatch):
    monkeypatch.delenv('DATA_MODE',raising=False)
    monkeypatch.delenv('DADATA_API_KEY',raising=False)
    financials=await get_financial_provider().get_by_inn('7325115310')
    history=await get_credit_history_provider().get_by_inn('7325115310')
    assert financials.source == history.source == 'UNAVAILABLE'
    assert financials.revenue_annual is None
    assert history.overdue_count is None


def test_zero_overdue_is_known_but_null_is_missing():
    from datetime import date
    company=SimpleNamespace(registration_date=date(2010,1,1))
    financials=SimpleNamespace(revenue_annual=100,profit_annual=10,expenses_annual=90,employees=0,current_debt=0)
    history=SimpleNamespace(active_credits=0,closed_credits=0,overdue_count=0,overdue_amount=0)
    assert missing_fields(company,financials,history)==[]
    history.overdue_amount=None
    assert missing_fields(company,financials,history)==['credit_history.overdue_amount']


@pytest.mark.asyncio
async def test_bki_gateway_requires_consent_and_rejects_mismatched_inn():
    from app.integrations.credit_history import GatewayCreditHistoryProvider, CreditHistoryProviderError
    calls=[]
    def handle(request):
        calls.append(request)
        return httpx.Response(200,json={'inn':'different','as_of':'2025-01-01T00:00:00Z'})
    provider=GatewayCreditHistoryProvider('https://example.test/report','test',transport=httpx.MockTransport(handle))
    with pytest.raises(CreditHistoryProviderError):
        await provider.get_by_inn('7325115310')
    assert calls==[]
    provider.consent_id='consent-id'
    with pytest.raises(CreditHistoryProviderError):
        await provider.get_by_inn('7325115310')
    assert len(calls)==1


@pytest.mark.asyncio
async def test_bki_gateway_preserves_unknowns_and_checks_report_time():
    from app.integrations.credit_history import GatewayCreditHistoryProvider, CreditHistoryProviderError
    body={'inn':'7325115310','as_of':'2025-01-01T00:00:00Z','active_credits':0,'closed_credits':None,'overdue_count':0,'overdue_amount':0}
    provider=GatewayCreditHistoryProvider('https://example.test/report','test','consent-id',httpx.MockTransport(lambda request:httpx.Response(200,json=body)))
    data=await provider.get_by_inn('7325115310')
    assert data.active_credits==0 and data.closed_credits is None
    assert data.source=='BKI_GATEWAY'
    body['as_of']='2099-01-01T00:00:00Z'
    with pytest.raises(CreditHistoryProviderError):
        await provider.get_by_inn('7325115310')
