from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from ml.facade import score_and_explain

from app.applications.schemas import ApplicationRiskAssessment
from app.applications.service import (
    ApplicationDataMissingError,
    ApplicationDataProviderError,
    ApplicationNotFoundError,
    ApplicationScoringError,
    ApplicationSubmissionConflictError,
    _validate_terms,
    get_application,
)
from app.integrations.credit_history import (
    CreditHistoryProvider,
    CreditHistoryProviderError,
)
from app.integrations.financials import FinancialProvider, FinancialProviderError
from app.models import (
    Application,
    ApplicationEvent,
    ApplicationSnapshot,
    Company,
    CreditHistory,
    CreditProduct,
    Financials,
)


def _build_scoring_input(
    application: Application,
    company: Company,
    financials: Financials,
    credit_history: CreditHistory,
) -> tuple[dict[str, float], dict[str, float], dict[str, float | int], float, str]:
    registration_date = company.registration_date
    today = date.today()
    revenue = float(financials.revenue_annual)
    if registration_date is None or registration_date > today or revenue <= 0:
        raise ApplicationDataMissingError()

    company_features = {
        "company_age": (today - registration_date).days / 365.25,
    }
    financial_features = {
        "revenue": revenue,
        "profit_margin": float(financials.profit_annual) / revenue,
    }
    credit_features: dict[str, float | int] = {
        "has_overdue": int(
            credit_history.overdue_count > 0 or credit_history.overdue_amount > 0
        ),
        "debt_load": float(financials.current_debt) / revenue,
    }
    return (
        company_features,
        financial_features,
        credit_features,
        float(application.requested_amount),
        application.purpose,
    )


async def _score_application(
    application: Application,
    company: Company,
    financials: Financials,
    credit_history: CreditHistory,
) -> ApplicationRiskAssessment:
    (
        company_features,
        financial_features,
        credit_features,
        loan_amount,
        user_query,
    ) = _build_scoring_input(application, company, financials, credit_history)
    try:
        result = await run_in_threadpool(
            score_and_explain,
            company=company_features,
            financials=financial_features,
            credit=credit_features,
            loan_amount=loan_amount,
            user_query=user_query,
        )
        return ApplicationRiskAssessment.model_validate(result)
    except Exception as error:
        raise ApplicationScoringError() from error


async def _get_or_fetch_financials(
    session: AsyncSession,
    company: Company,
    provider: FinancialProvider,
) -> tuple[Financials, bool]:
    existing = await session.get(Financials, company.id)
    if existing is not None:
        return existing, False
    try:
        data = await provider.get_by_inn(company.inn)
    except FinancialProviderError as error:
        raise ApplicationDataProviderError(
            "Financial provider is unavailable"
        ) from error
    return (
        Financials(
            company_id=company.id,
            revenue_annual=data.revenue_annual,
            profit_annual=data.profit_annual,
            expenses_annual=data.expenses_annual,
            employees=data.employees,
            current_debt=data.current_debt,
            source=data.source,
        ),
        True,
    )


async def _get_or_fetch_credit_history(
    session: AsyncSession,
    company: Company,
    provider: CreditHistoryProvider,
) -> tuple[CreditHistory, bool]:
    existing = await session.get(CreditHistory, company.id)
    if existing is not None:
        return existing, False
    try:
        data = await provider.get_by_inn(company.inn)
    except CreditHistoryProviderError as error:
        raise ApplicationDataProviderError(
            "Credit-history provider is unavailable"
        ) from error
    return (
        CreditHistory(
            company_id=company.id,
            active_credits=data.active_credits,
            closed_credits=data.closed_credits,
            overdue_count=data.overdue_count,
            overdue_amount=data.overdue_amount,
            source=data.source,
        ),
        True,
    )


def _build_snapshot_payload(
    application: Application,
    company: Company,
    product: CreditProduct,
    financials: Financials,
    credit_history: CreditHistory,
    risk_assessment: ApplicationRiskAssessment,
) -> dict[str, object]:
    return {
        "application": {
            "id": str(application.id),
            "requested_amount": str(application.requested_amount),
            "term_months": application.term_months,
            "purpose": application.purpose,
        },
        "company": {
            "id": str(company.id),
            "name": company.name,
            "inn": company.inn,
            "ogrn": company.ogrn,
            "registration_date": (
                company.registration_date.isoformat()
                if company.registration_date is not None
                else None
            ),
            "status": company.status,
            "director_name": company.director_name,
            "okved": company.okved,
            "data_source": company.data_source,
        },
        "financials": {
            "revenue_annual": str(financials.revenue_annual),
            "profit_annual": str(financials.profit_annual),
            "expenses_annual": str(financials.expenses_annual),
            "employees": financials.employees,
            "current_debt": str(financials.current_debt),
            "updated_at": financials.updated_at.isoformat(),
            "source": financials.source,
        },
        "credit_history": {
            "active_credits": credit_history.active_credits,
            "closed_credits": credit_history.closed_credits,
            "overdue_count": credit_history.overdue_count,
            "overdue_amount": str(credit_history.overdue_amount),
            "updated_at": credit_history.updated_at.isoformat(),
            "source": credit_history.source,
        },
        "credit_product": {
            "id": str(product.id),
            "name": product.name,
            "min_amount": str(product.min_amount),
            "max_amount": str(product.max_amount),
            "min_term_months": product.min_term_months,
            "max_term_months": product.max_term_months,
            "interest_rate": str(product.interest_rate),
            "data_source": product.data_source,
        },
        "risk_assessment": risk_assessment.model_dump(mode="json"),
    }


async def submit_application(
    session: AsyncSession,
    user_id: UUID,
    application_id: UUID,
    financial_provider: FinancialProvider,
    credit_history_provider: CreditHistoryProvider,
) -> Application:
    application = await session.scalar(
        select(Application)
        .where(
            Application.id == application_id,
            Application.user_id == user_id,
        )
        .with_for_update()
    )
    if application is None:
        raise ApplicationNotFoundError()

    if application.status == "SCORING":
        snapshot = await session.scalar(
            select(ApplicationSnapshot).where(
                ApplicationSnapshot.application_id == application.id
            )
        )
        if snapshot is not None:
            return application
        raise ApplicationSubmissionConflictError()
    if application.status != "DRAFT":
        raise ApplicationSubmissionConflictError()

    company = await session.get(Company, application.company_id)
    product = await session.get(CreditProduct, application.product_id)
    if company is None or product is None or not product.is_active:
        raise ApplicationDataMissingError()
    _validate_terms(product, application.requested_amount, application.term_months)

    financials, new_financials = await _get_or_fetch_financials(
        session, company, financial_provider
    )
    credit_history, new_credit_history = await _get_or_fetch_credit_history(
        session, company, credit_history_provider
    )
    if new_financials:
        session.add(financials)
    if new_credit_history:
        session.add(credit_history)
    await session.flush()

    risk_assessment = await _score_application(
        application, company, financials, credit_history
    )

    snapshot_id = uuid4()
    session.add(
        ApplicationSnapshot(
            id=snapshot_id,
            application_id=application.id,
            schema_version=2,
            payload=_build_snapshot_payload(
                application,
                company,
                product,
                financials,
                credit_history,
                risk_assessment,
            ),
        )
    )

    transitions = (
        ("DRAFT", "SUBMITTED", "APPLICATION_SUBMITTED", "USER"),
        ("SUBMITTED", "DATA_CHECK", "DATA_CHECK_PASSED", "SYSTEM"),
        (
            "DATA_CHECK",
            "DATA_ENRICHMENT",
            "DATA_ENRICHMENT_COMPLETED",
            "SYSTEM",
        ),
        (
            "DATA_ENRICHMENT",
            "SCORING",
            "RISK_ASSESSMENT_COMPLETED",
            "SYSTEM",
        ),
    )
    last_sequence = await session.scalar(
        select(func.coalesce(func.max(ApplicationEvent.sequence), 0)).where(
            ApplicationEvent.application_id == application.id
        )
    )
    for sequence, (from_status, to_status, event_type, actor_type) in enumerate(
        transitions, start=int(last_sequence or 0) + 1
    ):
        if application.status != from_status:
            raise ApplicationSubmissionConflictError()
        application.status = to_status
        session.add(
            ApplicationEvent(
                application_id=application.id,
                sequence=sequence,
                event_type=event_type,
                from_status=from_status,
                to_status=to_status,
                actor_type=actor_type,
                actor_user_id=user_id if actor_type == "USER" else None,
                details=(
                    {
                        "snapshot_id": str(snapshot_id),
                        "snapshot_schema_version": 2,
                        "risk_score": risk_assessment.risk_score,
                        "risk_level": risk_assessment.risk_level,
                        "top_factors": risk_assessment.top_factors,
                        "ai_advice_source": risk_assessment.ai_advice.source,
                    }
                    if event_type == "RISK_ASSESSMENT_COMPLETED"
                    else {}
                ),
            )
        )

    await session.commit()
    await session.refresh(application)
    return application


async def list_application_events(
    session: AsyncSession,
    user_id: UUID,
    application_id: UUID,
) -> list[ApplicationEvent]:
    await get_application(session, user_id, application_id)
    result = await session.scalars(
        select(ApplicationEvent)
        .where(ApplicationEvent.application_id == application_id)
        .order_by(ApplicationEvent.sequence)
    )
    return list(result)
