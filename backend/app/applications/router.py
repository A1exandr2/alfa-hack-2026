from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.applications.schemas import (
    ApplicationCreateRequest,
    ApplicationResponse,
    ApplicationUpdateRequest,
)
from app.applications.service import (
    ApplicationError,
    create_application,
    get_application,
    list_applications,
    update_application,
)
from app.auth.dependencies import get_current_user
from app.database import get_db_session
from app.models import User


router = APIRouter(prefix="/api/v1/applications", tags=["applications"])


def _raise_http_error(error: ApplicationError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=str(error)) from error


@router.post(
    "",
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_application_draft(
    payload: ApplicationCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ApplicationResponse:
    try:
        application = await create_application(session, user, payload)
    except ApplicationError as error:
        _raise_http_error(error)
    return ApplicationResponse.model_validate(application)


@router.get("", response_model=list[ApplicationResponse])
async def get_applications(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[ApplicationResponse]:
    applications = await list_applications(session, user.id)
    return [ApplicationResponse.model_validate(item) for item in applications]


@router.get("/{application_id}", response_model=ApplicationResponse)
async def get_application_details(
    application_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ApplicationResponse:
    try:
        application = await get_application(session, user.id, application_id)
    except ApplicationError as error:
        _raise_http_error(error)
    return ApplicationResponse.model_validate(application)


@router.patch("/{application_id}", response_model=ApplicationResponse)
async def update_application_draft(
    application_id: UUID,
    payload: ApplicationUpdateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ApplicationResponse:
    try:
        application = await update_application(
            session, user.id, application_id, payload
        )
    except ApplicationError as error:
        _raise_http_error(error)
    return ApplicationResponse.model_validate(application)
