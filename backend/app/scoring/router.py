"""Authenticated bridge between stored company data and the ML facade."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.auth.dependencies import get_current_user
from app.company.router import _get_or_create_credit_history, _get_or_create_financials
from app.database import get_db_session
from app.integrations.credit_history import CreditHistoryProvider, get_credit_history_provider
from app.integrations.financials import FinancialProvider, get_financial_provider
from app.models import Company, User
from ml.facade import score_and_explain
from ml.llm_assistant.schemas import CreditAdvice

router = APIRouter(prefix='/api/v1/company', tags=['scoring'])


class ScoreRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    loan_amount: float = Field(gt=0, le=999_999_999_999, allow_inf_nan=False)
    user_query: str | None = Field(default=None, max_length=500)


class AdviceResponse(BaseModel):
    source: Literal['AI', 'Fallback_Rules']
    data: CreditAdvice


class ScoreResponse(BaseModel):
    risk_score: float
    risk_level: Literal['Low', 'Medium', 'High']
    decision: Literal['APPROVED', 'MANUAL_REVIEW']
    top_factors: list[str]
    ai_advice: AdviceResponse


@router.post('/score', response_model=ScoreResponse)
async def score_company(
    payload: ScoreRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    financial_provider: FinancialProvider = Depends(get_financial_provider),
    credit_provider: CreditHistoryProvider = Depends(get_credit_history_provider),
) -> dict:
    if user.company_id is None:
        raise HTTPException(404, 'Company is not linked')
    company = await session.get(Company, user.company_id)
    if company is None:
        raise HTTPException(404, 'Company not found')
    if company.registration_date is None or company.registration_date > date.today():
        raise HTTPException(422, 'Valid company registration date is required for scoring')
    financials = await _get_or_create_financials(user, session, financial_provider)
    history = await _get_or_create_credit_history(user, session, credit_provider)
    revenue = float(financials.revenue_annual)
    # Ratios cannot be defined at zero revenue; never manufacture inputs for the model.
    if revenue <= 0:
        raise HTTPException(422, 'Positive annual revenue is required for scoring')
    return await run_in_threadpool(
        score_and_explain,
        company={'company_age': (date.today() - company.registration_date).days / 365.25},
        financials={'revenue': revenue, 'profit_margin': float(financials.profit_annual) / revenue},
        credit={
            'has_overdue': int(history.overdue_count > 0 or history.overdue_amount > 0),
            'debt_load': float(financials.current_debt) / revenue,
        },
        loan_amount=payload.loan_amount,
        user_query=payload.user_query,
    )
