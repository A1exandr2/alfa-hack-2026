from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.applications.schemas import (
    ApplicationCreateRequest,
    ApplicationUpdateRequest,
)
from app.applications.pricing import calculate_quote
from app.models import Application, ApplicationEvent, CreditProduct, User


class ApplicationError(Exception):
    status_code = 500


class CompanyNotLinkedError(ApplicationError):
    status_code = 409

    def __init__(self) -> None:
        super().__init__("Company must be linked before creating an application")


class CreditProductNotFoundError(ApplicationError):
    status_code = 404

    def __init__(self) -> None:
        super().__init__("Active credit product not found")


class InvalidApplicationTermsError(ApplicationError):
    status_code = 422

    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class ApplicationNotFoundError(ApplicationError):
    status_code = 404

    def __init__(self) -> None:
        super().__init__("Application not found")


class ApplicationNotEditableError(ApplicationError):
    status_code = 409

    def __init__(self) -> None:
        super().__init__("Only draft applications can be edited")


class ApplicationSubmissionConflictError(ApplicationError):
    status_code = 409

    def __init__(self) -> None:
        super().__init__("Application cannot be submitted in its current state")


class ApplicationReviewConflictError(ApplicationError):
    status_code = 409

    def __init__(self) -> None:
        super().__init__("Application is not awaiting a reviewer decision")


class ApplicationDataProviderError(ApplicationError):
    status_code = 502

    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class ApplicationDataMissingError(ApplicationError):
    status_code = 409

    def __init__(self) -> None:
        super().__init__("Application data is incomplete")


class ApplicationScoringError(ApplicationError):
    status_code = 502

    def __init__(self) -> None:
        super().__init__("Application risk scoring could not be completed")


class ApplicationDecisionNotFoundError(ApplicationError):
    status_code = 404

    def __init__(self) -> None:
        super().__init__("Application decision not found")


async def _get_active_product(
    session: AsyncSession, product_id: UUID
) -> CreditProduct:
    product = await session.scalar(
        select(CreditProduct).where(
            CreditProduct.id == product_id,
            CreditProduct.is_active.is_(True),
        )
    )
    if product is None:
        raise CreditProductNotFoundError()
    return product


def _validate_terms(
    product: CreditProduct, requested_amount: Decimal, term_months: int
) -> None:
    if not product.min_amount <= requested_amount <= product.max_amount:
        raise InvalidApplicationTermsError(
            "Requested amount is outside the credit product limits"
        )
    if not product.min_term_months <= term_months <= product.max_term_months:
        raise InvalidApplicationTermsError(
            "Requested term is outside the credit product limits"
        )


async def quote_application(session, amount, months, category, product_id=None):
    if product_id is not None:
        products = [await _get_active_product(session, product_id)]
        _validate_terms(products[0], amount, months)
    else:
        products = list(await session.scalars(select(CreditProduct).where(CreditProduct.is_active.is_(True))))
    result = calculate_quote(products, amount, months, category, automatic=product_id is None)
    if result is None:
        raise InvalidApplicationTermsError("No product matches requested amount and term")
    return result


async def create_application(
    session: AsyncSession,
    user: User,
    payload: ApplicationCreateRequest,
) -> Application:
    if user.company_id is None:
        raise CompanyNotLinkedError()

    product, pricing = await quote_application(session, payload.requested_amount, payload.term_months, payload.purpose_category, payload.product_id)

    application_id = uuid4()
    application = Application(
        id=application_id,
        user_id=user.id,
        company_id=user.company_id,
        product_id=product.id,
        pricing=pricing,
        purpose_category=payload.purpose_category,
        requested_amount=payload.requested_amount,
        term_months=payload.term_months,
        purpose=payload.purpose,
        additional_info=payload.additional_info.strip(),
    )
    session.add(application)
    session.add(
        ApplicationEvent(
            application_id=application_id,
            sequence=1,
            event_type="APPLICATION_DRAFT_CREATED",
            from_status=None,
            to_status="DRAFT",
            actor_type="USER",
            actor_user_id=user.id,
            details={},
        )
    )
    await session.commit()
    await session.refresh(application)
    return application


async def list_applications(
    session: AsyncSession, user_id: UUID
) -> list[Application]:
    result = await session.scalars(
        select(Application)
        .where(Application.user_id == user_id)
        .order_by(Application.created_at.desc(), Application.id)
    )
    return list(result)


async def get_application(
    session: AsyncSession, user_id: UUID, application_id: UUID
) -> Application:
    application = await session.scalar(
        select(Application).where(
            Application.id == application_id,
            Application.user_id == user_id,
        )
    )
    if application is None:
        raise ApplicationNotFoundError()
    return application


async def update_application(
    session: AsyncSession,
    user_id: UUID,
    application_id: UUID,
    payload: ApplicationUpdateRequest,
) -> Application:
    application = await get_application(session, user_id, application_id)
    if application.status != "DRAFT":
        raise ApplicationNotEditableError()

    changes = payload.model_dump(exclude_unset=True)
    product_id = changes.get("product_id", application.product_id)
    requested_amount = changes.get("requested_amount", application.requested_amount)
    term_months = changes.get("term_months", application.term_months)
    automatic = bool(application.pricing and application.pricing.get('selection_mode') == 'AUTO')
    category = changes.get('purpose_category', application.purpose_category)
    product, pricing = await quote_application(session, requested_amount, term_months, category,
        changes.get('product_id') if automatic else product_id)
    application.pricing = pricing
    application.product_id = product.id

    for field, value in changes.items():
        setattr(application, field, value)
    await session.commit()
    await session.refresh(application)
    return application
