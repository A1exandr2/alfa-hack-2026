from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.applications.schemas import (
    ApplicationCreateRequest,
    ApplicationQuoteRequest,
    ApplicationDecisionResponse,
    ApplicationEventResponse,
    ApplicationReviewRequest,
    ApplicationReviewRecordResponse,
    ApplicationReviewResponse,
    ApplicationResponse,
    ApplicationSubmissionResponse,
    ApplicationUpdateRequest,
)
from app.applications.service import (
    ApplicationError,
    create_application,
    quote_application,
    get_application,
    list_applications,
    update_application,
)
from app.applications.workflow import (
    get_application_decision,
    list_application_events,
    submit_application,
)
from app.applications.review import review_application as record_application_review
from app.auth.dependencies import get_current_reviewer, get_current_user
from app.database import get_db_session
from app.integrations.credit_history import (
    CreditHistoryProvider,
    get_credit_history_provider,
)
from app.integrations.financials import (
    FinancialProvider,
    get_financial_provider,
)
from app.models import User


router = APIRouter(prefix="/api/v1/applications", tags=["applications"])


def _raise_http_error(error: ApplicationError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=str(error)) from error


@router.post("/quote")
async def preview_application_quote(
    payload: ApplicationQuoteRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    try:
        _, pricing = await quote_application(session, payload.requested_amount, payload.term_months, payload.purpose_category)
    except ApplicationError as error:
        _raise_http_error(error)
    return pricing


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


@router.post(
    "/{application_id}/submit", response_model=ApplicationSubmissionResponse
)
async def submit_application_for_scoring(
    application_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    financial_provider: FinancialProvider = Depends(get_financial_provider),
    credit_history_provider: CreditHistoryProvider = Depends(
        get_credit_history_provider
    ),
) -> ApplicationSubmissionResponse:
    try:
        application, decision, required_fields = await submit_application(
            session,
            user.id,
            application_id,
            financial_provider,
            credit_history_provider,
        )
    except ApplicationError as error:
        _raise_http_error(error)
    return ApplicationSubmissionResponse(
        **ApplicationResponse.model_validate(application).model_dump(),
        decision=(
            ApplicationDecisionResponse.model_validate(decision)
            if decision is not None
            else None
        ),
        required_fields=required_fields,
    )


@router.post(
    "/{application_id}/review",
    response_model=ApplicationReviewResponse,
)
async def review_application_decision(
    application_id: UUID,
    payload: ApplicationReviewRequest,
    user: User = Depends(get_current_reviewer),
    session: AsyncSession = Depends(get_db_session),
) -> ApplicationReviewResponse:
    try:
        application, decision, review = await record_application_review(
            session, user.id, application_id, payload
        )
    except ApplicationError as error:
        _raise_http_error(error)
    return ApplicationReviewResponse(
        application_id=application.id,
        status=application.status,
        review=ApplicationReviewRecordResponse.model_validate(review),
        original_decision=ApplicationDecisionResponse.model_validate(decision),
    )


@router.get(
    "/{application_id}/history",
    response_model=list[ApplicationEventResponse],
)
async def get_application_history(
    application_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[ApplicationEventResponse]:
    try:
        events = await list_application_events(session, user.id, application_id)
    except ApplicationError as error:
        _raise_http_error(error)
    return [ApplicationEventResponse.model_validate(event) for event in events]


@router.get(
    "/{application_id}/decision",
    response_model=ApplicationDecisionResponse,
)
async def get_application_decision_details(
    application_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ApplicationDecisionResponse:
    try:
        decision = await get_application_decision(session, user.id, application_id)
    except ApplicationError as error:
        _raise_http_error(error)
    return ApplicationDecisionResponse.model_validate(decision)


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
