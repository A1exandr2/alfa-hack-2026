from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.company.schemas import CompanyResponse, LinkCompanyRequest
from app.database import get_db_session
from app.integrations.company import (
    CompanyProvider,
    CompanyProviderError,
    get_company_provider,
)
from app.models import Company, User


router = APIRouter(prefix="/api/v1/company", tags=["company"])


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
