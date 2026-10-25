from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.company.schemas import (
    CompanyResponse,
    CreditHistoryResponse,
    CreditHistoryUpdateRequest,
    CreditHistoryConsentRequest,
    FinancialsResponse,
    FinancialsUpdateRequest,
    LinkCompanyRequest,
)
from app.database import get_db_session
from app.integrations.company import (
    CompanyProvider,
    CompanyProviderError,
    CompanyNotFoundError,
    DemoCompanyProvider,
    get_company_provider,
)
from app.integrations.credit_history import (
    CreditHistoryProvider,
    CreditHistoryProviderError,
    get_credit_history_provider,
)
from app.integrations.financials import (
    FinancialProvider,
    FinancialProviderError,
    get_financial_provider,
)
from app.models import Company, CreditHistory, CreditHistoryConsent, Financials, User
from app.company.credit_access import active_consent, authorized_provider, unknown_history


from app.company.data_quality import FINANCIAL_FIELDS, CREDIT_FIELDS, MANUAL_SOURCES, provenance
from datetime import datetime, timezone


router = APIRouter(prefix="/api/v1/company", tags=["company"])


async def _get_or_create_financials(
    user: User,
    session: AsyncSession,
    provider: FinancialProvider,
) -> Financials:
    if user.company_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company is not linked",
        )

    financials = await session.get(Financials, user.company_id)
    if financials is not None:
        return financials

    company = await session.get(Company, user.company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found",
        )

    try:
        data = await provider.get_by_inn(company.inn)
    except FinancialProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Financial provider is unavailable",
        ) from error

    financials = Financials(
        company_id=company.id,
        revenue_annual=data.revenue_annual,
        profit_annual=data.profit_annual,
        expenses_annual=data.expenses_annual,
        employees=data.employees,
        current_debt=data.current_debt,
        source=data.source,
        report_year=getattr(data, "report_year", None),
        field_sources=provenance(data, FINANCIAL_FIELDS),
    )
    session.add(financials)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        financials = await session.get(Financials, company.id)
        if financials is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Financial data could not be saved",
            ) from error
    return financials


async def _get_or_create_credit_history(
    user: User,
    session: AsyncSession,
    provider: CreditHistoryProvider,
) -> CreditHistory:
    if user.company_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company is not linked",
        )

    provider = await authorized_provider(session, user.id, user.company_id, provider)
    if provider is None:
        return unknown_history(user.company_id)
    credit_history = await session.get(CreditHistory, user.company_id)
    if credit_history is not None:
        return credit_history

    company = await session.get(Company, user.company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found",
        )

    try:
        data = await provider.get_by_inn(company.inn)
    except CreditHistoryProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Credit-history provider is unavailable",
        ) from error

    credit_history = CreditHistory(
        company_id=company.id,
        active_credits=data.active_credits,
        closed_credits=data.closed_credits,
        overdue_count=data.overdue_count,
        overdue_amount=data.overdue_amount,
        source=data.source,
        field_sources=provenance(data, CREDIT_FIELDS),
        as_of=data.as_of,
    )
    session.add(credit_history)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        credit_history = await session.get(CreditHistory, company.id)
        if credit_history is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Credit history could not be saved",
            ) from error
    return credit_history


@router.get("/registry-status")
async def company_registry_status(
    user: User = Depends(get_current_user),
    provider: CompanyProvider = Depends(get_company_provider),
) -> dict:
    configured = not isinstance(provider, DemoCompanyProvider)
    return {"configured": configured, "provider": "DaData" if configured else None,
            "description": "Реквизиты ЕГРЮЛ/ЕГРИП через внешний источник. Финансы и БКИ не обновляются этим запросом."}


@router.get("", response_model=CompanyResponse)
async def get_company(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CompanyResponse:
    if user.company_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company is not linked",
        )

    company = await session.get(Company, user.company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found",
        )
    return CompanyResponse.model_validate(company)


@router.post("/link", response_model=CompanyResponse)
async def link_company(
    payload: LinkCompanyRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    provider: CompanyProvider = Depends(get_company_provider),
) -> CompanyResponse:
    if user.company_id is not None:
        linked_company = await session.get(Company, user.company_id)
        if linked_company is not None and linked_company.inn == payload.inn:
            return CompanyResponse.model_validate(linked_company)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already linked to another company",
        )

    company = await session.scalar(select(Company).where(Company.inn == payload.inn))
    if company is None:
        try:
            company_data = await provider.get_by_inn(payload.inn)
        except CompanyNotFoundError as error:
            raise HTTPException(status_code=404, detail="Company not found") from error
        except CompanyProviderError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Company provider is unavailable",
            ) from error

        if company_data.inn != payload.inn:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Company provider returned mismatched INN",
            )

        company = Company(
            name=company_data.name,
            inn=company_data.inn,
            ogrn=company_data.ogrn,
            registration_date=company_data.registration_date,
            status=company_data.status,
            director_name=company_data.director_name,
            okved=company_data.okved,
            data_source=company_data.data_source,
            full_name=company_data.full_name, kpp=company_data.kpp, address=company_data.address,
        )
        session.add(company)

    user.company = company
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Company could not be linked",
        ) from error

    return CompanyResponse.model_validate(company)


@router.post("/refresh", response_model=CompanyResponse)
async def refresh_company(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    provider: CompanyProvider = Depends(get_company_provider),
) -> CompanyResponse:
    if user.company_id is None:
        raise HTTPException(status_code=404, detail="Company is not linked")
    if isinstance(provider, DemoCompanyProvider):
        raise HTTPException(status_code=503, detail="Company registry is not configured")
    company = await session.get(Company, user.company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        data = await provider.get_by_inn(company.inn)
    except CompanyNotFoundError as error:
        raise HTTPException(status_code=404, detail="Company not found") from error
    except CompanyProviderError as error:
        raise HTTPException(status_code=502, detail="Company provider is unavailable") from error
    for field in ("name", "ogrn", "registration_date", "status", "director_name", "okved", "data_source", "full_name", "kpp", "address"):
        setattr(company, field, getattr(data, field))
    await session.commit()
    await session.refresh(company)
    return CompanyResponse.model_validate(company)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_company(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    # Remove only this user's link. Company records and application snapshots
    # remain available to their owners and are not deleted for other users.
    user.company_id = None
    await session.commit()


@router.get("/financials", response_model=FinancialsResponse)
async def get_company_financials(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    provider: FinancialProvider = Depends(get_financial_provider),
) -> FinancialsResponse:
    financials = await _get_or_create_financials(user, session, provider)
    return FinancialsResponse.model_validate(financials)


@router.patch("/financials", response_model=FinancialsResponse)
async def update_company_financials(
    payload: FinancialsUpdateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    provider: FinancialProvider = Depends(get_financial_provider),
) -> FinancialsResponse:
    financials = await _get_or_create_financials(user, session, provider)
    old_values = {f: getattr(financials, f) for f in FINANCIAL_FIELDS}
    for field in payload.model_fields_set:
        setattr(financials, field, getattr(payload, field))
    sources = dict(financials.field_sources or {})
    for field in payload.model_fields_set - {"report_year"}:
        original = sources.get(field, {})
        registry = original.get("registry") if isinstance(original, dict) else None
        if isinstance(original, dict) and original.get("source") not in MANUAL_SOURCES and old_values[field] is not None:
            registry = {**original, "value": str(old_values[field])}
        sources[field] = {"source": "USER_INPUT", "report_year": financials.report_year,
                          "entered_by": str(user.id), "registry": registry,
                          "fetched_at": datetime.now(timezone.utc).isoformat()}
    financials.field_sources = sources
    financials.source = "USER_INPUT" if all(sources.get(f, {}).get("source") == "USER_INPUT" for f in FINANCIAL_FIELDS if getattr(financials, f) is not None) else "MIXED"

    await session.commit()
    await session.refresh(financials)
    return FinancialsResponse.model_validate(financials)


@router.get("/credit-history", response_model=CreditHistoryResponse)
async def get_company_credit_history(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    provider: CreditHistoryProvider = Depends(get_credit_history_provider),
) -> CreditHistoryResponse:
    credit_history = await _get_or_create_credit_history(user, session, provider)
    return CreditHistoryResponse.model_validate(credit_history)


@router.post("/financials/refresh", response_model=FinancialsResponse)
async def refresh_financials(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    provider: FinancialProvider = Depends(get_financial_provider),
) -> FinancialsResponse:
    if user.company_id is None:
        raise HTTPException(status_code=404, detail="Company is not linked")
    company = await session.get(Company, user.company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        data = await provider.get_by_inn(company.inn)
    except FinancialProviderError as error:
        raise HTTPException(status_code=502, detail="Financial provider is unavailable") from error
    record = await session.get(Financials, company.id, with_for_update=True)
    if record is None:
        record = Financials(company_id=company.id, source=data.source)
        session.add(record)
    sources = dict(record.field_sources or {})
    new_sources = provenance(data, FINANCIAL_FIELDS)
    for field in FINANCIAL_FIELDS:
        old = sources.get(field, {})
        old_source = old.get("source", record.source) if isinstance(old, dict) else old
        if old_source in MANUAL_SOURCES:
            if field in new_sources:
                sources[field] = {**old, "registry": {**new_sources[field], "value": str(getattr(data,field))}}
            continue
        setattr(record, field, getattr(data, field))
        sources.pop(field, None)
        if field in new_sources:
            sources[field] = new_sources[field]
    record.field_sources = sources
    record.report_year = data.report_year
    record.source = "MIXED" if any((v.get("source") if isinstance(v, dict) else v) in MANUAL_SOURCES for v in sources.values()) else data.source
    record.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(record)
    return FinancialsResponse.model_validate(record)


@router.patch("/credit-history", response_model=CreditHistoryResponse)
async def update_credit_history(
    payload: CreditHistoryUpdateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    provider: CreditHistoryProvider = Depends(get_credit_history_provider),
) -> CreditHistoryResponse:
    if user.company_id is None:
        raise HTTPException(status_code=404, detail="Company is not linked")
    record = await session.get(CreditHistory, user.company_id, with_for_update=True)
    if record is None:
        record = CreditHistory(company_id=user.company_id, source="USER_INPUT", field_sources={})
        session.add(record)
    sources = dict(record.field_sources or {})
    for field in payload.model_fields_set:
        setattr(record, field, getattr(payload, field))
        sources[field] = {"source": "USER_INPUT", "entered_by": str(user.id), "fetched_at": datetime.now(timezone.utc).isoformat()}
    record.field_sources = sources
    record.source = "USER_INPUT"
    record.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(record)
    return CreditHistoryResponse.model_validate(record)


@router.get("/credit-history/connection")
async def credit_history_connection(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db_session), provider: CreditHistoryProvider = Depends(get_credit_history_provider)):
    consent = await active_consent(session, user.id, user.company_id) if user.company_id else None
    return {"configured": bool(getattr(provider,"requires_consent",False)),
            "consent_active": consent is not None, "text_version": "credit-report-v1",
            "description": "Запрос кредитного отчёта компании для рассмотрения кредитной заявки. Доступен только после подключения отдельного источника БКИ."}


@router.post("/credit-history/consent")
async def grant_credit_consent(payload: CreditHistoryConsentRequest, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db_session), provider: CreditHistoryProvider = Depends(get_credit_history_provider)):
    from datetime import timedelta
    if not user.company_id:
        raise HTTPException(status_code=404, detail="Company is not linked")
    if not getattr(provider,"requires_consent",False):
        raise HTTPException(status_code=503, detail="Credit history source is not configured")
    if not payload.accepted or payload.text_version != "credit-report-v1":
        raise HTTPException(status_code=422, detail="Explicit credit report consent is required")
    consent = await active_consent(session,user.id,user.company_id)
    if consent is None:
        consent=CreditHistoryConsent(user_id=user.id,company_id=user.company_id,
            expires_at=datetime.now(timezone.utc)+timedelta(days=180),text_version=payload.text_version)
        session.add(consent)
        await session.commit()
    return {"consent_active":True,"expires_at":consent.expires_at}


@router.delete("/credit-history/consent", status_code=204)
async def revoke_credit_consent(user: User = Depends(get_current_user),session: AsyncSession = Depends(get_db_session)):
    rows=await session.scalars(select(CreditHistoryConsent).where(CreditHistoryConsent.user_id==user.id,
        CreditHistoryConsent.company_id==user.company_id,CreditHistoryConsent.revoked_at.is_(None)))
    for row in rows:
        row.revoked_at=datetime.now(timezone.utc)
    await session.commit()


@router.post("/credit-history/refresh", response_model=CreditHistoryResponse)
async def refresh_credit_history(user: User = Depends(get_current_user),session: AsyncSession = Depends(get_db_session),provider: CreditHistoryProvider = Depends(get_credit_history_provider)):
    if not user.company_id:
        raise HTTPException(status_code=404,detail="Company is not linked")
    if not getattr(provider,"requires_consent",False):
        raise HTTPException(status_code=503,detail="Credit history source is not configured")
    provider=await authorized_provider(session,user.id,user.company_id,provider)
    if provider is None:
        raise HTTPException(status_code=403,detail="Credit history consent is required")
    company=await session.get(Company,user.company_id)
    try:
        data=await provider.get_by_inn(company.inn)
    except CreditHistoryProviderError as error:
        raise HTTPException(status_code=502,detail="Credit-history provider is unavailable") from error
    record=await session.get(CreditHistory,user.company_id,with_for_update=True)
    if record is None:
        record=CreditHistory(company_id=user.company_id,source=data.source)
        session.add(record)
    # Keep manually entered originals separately when the verified report becomes current.
    sources=provenance(data,CREDIT_FIELDS)
    previous_sources=record.field_sources or {}
    for field in CREDIT_FIELDS:
        old=previous_sources.get(field,{})
        manual=old.get("user_input") if isinstance(old,dict) else None
        if isinstance(old,dict) and old.get("source") in MANUAL_SOURCES and getattr(record,field) is not None:
            manual={**old,"value":str(getattr(record,field))}
        if manual:
            sources.setdefault(field,{"source":data.source})["user_input"]=manual
        setattr(record,field,getattr(data,field))
    record.source=data.source
    record.field_sources=sources
    record.as_of=data.as_of
    record.updated_at=datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(record)
    return CreditHistoryResponse.model_validate(record)
