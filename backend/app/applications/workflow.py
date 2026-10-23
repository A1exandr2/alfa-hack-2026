from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from ml.facade import score_and_explain

from app.applications.schemas import ApplicationRiskAssessment
from app.applications.service import (
    ApplicationDecisionNotFoundError,
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
    ApplicationDecision,
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
    product: CreditProduct,
    financials: Financials,
    credit_history: CreditHistory,
) -> tuple[
    dict[str, float],
    dict[str, float],
    dict[str, float | int],
    float,
    str,
    int,
    dict[str, str | float | int],
]:
    registration_date = company.registration_date
    today = date.today()
    revenue = float(financials.revenue_annual)
    if registration_date is None or registration_date > today:
        raise ApplicationDataMissingError()
    if revenue <= 0:
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
    product_features: dict[str, str | float | int] = {
        "name": product.name,
        "interest_rate": float(product.interest_rate),
        "min_amount": float(product.min_amount),
        "max_amount": float(product.max_amount),
        "min_term_months": product.min_term_months,
        "max_term_months": product.max_term_months,
    }
    return (
        company_features,
        financial_features,
        credit_features,
        float(application.requested_amount),
        application.purpose,
        application.term_months,
        product_features,
    )


async def _score_application(
    application: Application,
    company: Company,
    product: CreditProduct,
    financials: Financials,
    credit_history: CreditHistory,
) -> ApplicationRiskAssessment:
    (
        company_features,
        financial_features,
        credit_features,
        loan_amount,
        user_query,
        loan_term_months,
        product_features,
    ) = _build_scoring_input(
        application, company, product, financials, credit_history
    )
    try:
        result = await run_in_threadpool(
            score_and_explain,
            company=company_features,
            financials=financial_features,
            credit=credit_features,
            loan_amount=loan_amount,
            user_query=user_query,
            loan_term_months=loan_term_months,
            product=product_features,
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
    risk_assessment: ApplicationRiskAssessment | None,
    required_fields: list[str],
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
        "risk_assessment": (
            risk_assessment.model_dump(mode="json")
            if risk_assessment is not None
            else None
        ),
        "required_fields": required_fields,
    }


def _apply_status_transitions(
    application: Application,
    user_id: UUID,
    transitions: tuple[tuple[str, str, str, str], ...],
    first_sequence: int,
    snapshot_id: UUID,
    snapshot_version: int,
    extra_details: dict[str, dict[str, object]] | None = None,
) -> list[ApplicationEvent]:
    events = []
    extra_details = extra_details or {}
    for sequence, (from_status, to_status, event_type, actor_type) in enumerate(
        transitions, start=first_sequence
    ):
        if application.status != from_status:
            raise ApplicationSubmissionConflictError()
        application.status = to_status
        details: dict[str, object] = {
            "snapshot_id": str(snapshot_id),
            "snapshot_version": snapshot_version,
            **extra_details.get(event_type, {}),
        }
        events.append(
            ApplicationEvent(
                application_id=application.id,
                sequence=sequence,
                event_type=event_type,
                from_status=from_status,
                to_status=to_status,
                actor_type=actor_type,
                actor_user_id=user_id if actor_type == "USER" else None,
                details=details,
            )
        )
    return events


async def submit_application(
    session: AsyncSession,
    user_id: UUID,
    application_id: UUID,
    financial_provider: FinancialProvider,
    credit_history_provider: CreditHistoryProvider,
) -> tuple[Application, ApplicationDecision | None, list[str]]:
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

    if application.status in {"DECISION", "MANUAL_REVIEW", "REJECTED"}:
        decision = await session.scalar(
            select(ApplicationDecision).where(
                ApplicationDecision.application_id == application.id
            )
        )
        if decision is not None:
            return application, decision, []
        raise ApplicationSubmissionConflictError()
    if application.status not in {"DRAFT", "NEED_MORE_DATA"}:
        raise ApplicationSubmissionConflictError()

    company = await session.get(Company, application.company_id)
    product = await session.get(CreditProduct, application.product_id)
    if company is None or product is None or not product.is_active:
        raise ApplicationDataMissingError()
    if company.registration_date is None or company.registration_date > date.today():
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

    required_fields = (
        ["financials.revenue_annual"]
        if financials.revenue_annual <= 0
        else []
    )
    incomplete_payload = _build_snapshot_payload(
        application,
        company,
        product,
        financials,
        credit_history,
        risk_assessment=None,
        required_fields=required_fields,
    )
    latest_snapshot = await session.scalar(
        select(ApplicationSnapshot)
        .where(ApplicationSnapshot.application_id == application.id)
        .order_by(ApplicationSnapshot.snapshot_version.desc())
        .limit(1)
    )
    if (
        application.status == "NEED_MORE_DATA"
        and latest_snapshot is not None
        and latest_snapshot.payload == incomplete_payload
    ):
        return application, None, required_fields

    snapshot_version = (
        latest_snapshot.snapshot_version + 1 if latest_snapshot is not None else 1
    )
    snapshot_id = uuid4()
    last_sequence = await session.scalar(
        select(func.coalesce(func.max(ApplicationEvent.sequence), 0)).where(
            ApplicationEvent.application_id == application.id
        )
    )
    first_sequence = int(last_sequence or 0) + 1
    previous_status = application.status

    if required_fields:
        session.add(
            ApplicationSnapshot(
                id=snapshot_id,
                application_id=application.id,
                snapshot_version=snapshot_version,
                schema_version=4,
                payload=incomplete_payload,
            )
        )
        transitions = (
            (
                previous_status,
                "SUBMITTED",
                "APPLICATION_RESUBMITTED"
                if previous_status == "NEED_MORE_DATA"
                else "APPLICATION_SUBMITTED",
                "USER",
            ),
            ("SUBMITTED", "DATA_CHECK", "DATA_CHECK_PASSED", "SYSTEM"),
            ("DATA_CHECK", "NEED_MORE_DATA", "APPLICATION_DATA_REQUIRED", "SYSTEM"),
        )
        events = _apply_status_transitions(
            application,
            user_id,
            transitions,
            first_sequence,
            snapshot_id,
            snapshot_version,
            extra_details={
                "APPLICATION_DATA_REQUIRED": {"required_fields": required_fields}
            },
        )
        session.add_all(events)
        await session.commit()
        await session.refresh(application)
        return application, None, required_fields

    risk_assessment = await _score_application(
        application, company, product, financials, credit_history
    )
    snapshot_payload = _build_snapshot_payload(
        application,
        company,
        product,
        financials,
        credit_history,
        risk_assessment=risk_assessment,
        required_fields=[],
    )
    session.add(
        ApplicationSnapshot(
            id=snapshot_id,
            application_id=application.id,
            snapshot_version=snapshot_version,
            schema_version=4,
            payload=snapshot_payload,
        )
    )
    await session.flush()

    decision_record = ApplicationDecision(
        application_id=application.id,
        snapshot_id=snapshot_id,
        outcome=risk_assessment.decision,
        source=risk_assessment.ai_advice.source,
        risk_score=Decimal(str(risk_assessment.risk_score)),
        risk_level=risk_assessment.risk_level,
        explanation=risk_assessment.ai_advice.data.explanation,
        recommended_product=risk_assessment.ai_advice.data.recommended_product,
        next_step=risk_assessment.ai_advice.data.next_step,
        top_factors=risk_assessment.ai_advice.data.top_risk_factors,
        conditions=risk_assessment.ai_advice.data.conditions,
    )
    session.add(decision_record)

    transitions = (
        (
            previous_status,
            "SUBMITTED",
            "APPLICATION_RESUBMITTED"
            if previous_status == "NEED_MORE_DATA"
            else "APPLICATION_SUBMITTED",
            "USER",
        ),
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
    events = _apply_status_transitions(
        application,
        user_id,
        transitions,
        first_sequence,
        snapshot_id,
        snapshot_version,
        extra_details={
            "RISK_ASSESSMENT_COMPLETED": {
                "risk_score": risk_assessment.risk_score,
                "risk_level": risk_assessment.risk_level,
                "top_factors": risk_assessment.top_factors,
                "ai_advice_source": risk_assessment.ai_advice.source,
            }
        },
    )
    session.add_all(events)

    decision_status = {
        "APPROVED": "DECISION",
        "CONDITIONAL_APPROVAL": "MANUAL_REVIEW",
        "REJECTED": "REJECTED",
    }[risk_assessment.decision]
    if application.status != "SCORING":
        raise ApplicationSubmissionConflictError()
    application.status = decision_status
    session.add(
        ApplicationEvent(
            application_id=application.id,
            sequence=first_sequence + len(transitions),
            event_type="APPLICATION_DECISION_RECORDED",
            from_status="SCORING",
            to_status=decision_status,
            actor_type="SYSTEM",
            actor_user_id=None,
            details={
                "decision_id": str(decision_record.id),
                "snapshot_id": str(snapshot_id),
                "snapshot_version": snapshot_version,
                "outcome": decision_record.outcome,
                "source": decision_record.source,
                "risk_score": risk_assessment.risk_score,
                "risk_level": risk_assessment.risk_level,
                "explanation": decision_record.explanation,
                "top_factors": decision_record.top_factors,
                "conditions": decision_record.conditions,
            },
        )
    )

    await session.commit()
    await session.refresh(application)
    await session.refresh(decision_record)
    return application, decision_record, []


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


async def get_application_decision(
    session: AsyncSession,
    user_id: UUID,
    application_id: UUID,
) -> ApplicationDecision:
    await get_application(session, user_id, application_id)
    decision = await session.scalar(
        select(ApplicationDecision).where(
            ApplicationDecision.application_id == application_id
        )
    )
    if decision is None:
        raise ApplicationDecisionNotFoundError()
    return decision
