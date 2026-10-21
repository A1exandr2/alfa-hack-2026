from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.company.schemas import (
    CompanyResponse,
    FinancialsResponse,
    FinancialsUpdateRequest,
    LinkCompanyRequest,
)
from app.database import get_db_session
from app.integrations.company import (
    CompanyProvider,
    CompanyProviderError,
    get_company_provider,
)
from app.integrations.financials import (
    FinancialProvider,
    FinancialProviderError,
    get_financial_provider,
)
from app.models import Company, Financials, User


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
    for field in payload.model_fields_set:
        setattr(financials, field, getattr(payload, field))
    financials.source = "USER_VERIFIED"

    await session.commit()
    await session.refresh(financials)
    return FinancialsResponse.model_validate(financials)
