from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.applications.schemas import ApplicationReviewRequest
from app.applications.service import (
    ApplicationDecisionNotFoundError,
    ApplicationNotFoundError,
    ApplicationReviewConflictError,
)
from app.models import (
    AdminAudit,
    User,
    Application,
    ApplicationDecision,
    ApplicationEvent,
    ApplicationReview,
)


async def review_application(
    session: AsyncSession,
    reviewer_user_id: UUID,
    application_id: UUID,
    payload: ApplicationReviewRequest,
) -> tuple[Application, ApplicationDecision, ApplicationReview]:
    application = await session.scalar(
        select(Application)
        .where(Application.id == application_id)
        .with_for_update()
    )
    if application is None:
        raise ApplicationNotFoundError()

    existing_review = await session.scalar(
        select(ApplicationReview).where(
            ApplicationReview.application_id == application_id
        )
    )
    if existing_review is not None:
        decision = await session.scalar(
            select(ApplicationDecision).where(
                ApplicationDecision.application_id == application_id
            )
        )
        expected_status = {
            "APPROVED": "DECISION",
            "REJECTED": "REJECTED",
        }[existing_review.outcome]
        if (
            decision is not None
            and application.status == expected_status
            and existing_review.outcome == payload.outcome
            and existing_review.comment == payload.comment
        ):
            return application, decision, existing_review
        raise ApplicationReviewConflictError()

    if application.status != "MANUAL_REVIEW":
        raise ApplicationReviewConflictError()

    decision = await session.scalar(
        select(ApplicationDecision)
        .where(ApplicationDecision.application_id == application_id)
        .with_for_update()
    )
    if decision is None:
        raise ApplicationDecisionNotFoundError()
    if decision.outcome != "CONDITIONAL_APPROVAL":
        raise ApplicationReviewConflictError()

    review = ApplicationReview(
        id=uuid4(),
        application_id=application.id,
        decision_id=decision.id,
        reviewer_user_id=reviewer_user_id,
        outcome=payload.outcome,
        comment=payload.comment,
    )
    session.add(review)
    reviewer = await session.get(User, reviewer_user_id)
    session.add(AdminAudit(actor_user_id=reviewer_user_id, actor_email=reviewer.email,
                          action="APPLICATION_REVIEWED", target_id=application.id,
                          details={"outcome": payload.outcome, "comment": payload.comment}))
    await session.flush()

    last_sequence = await session.scalar(
        select(func.coalesce(func.max(ApplicationEvent.sequence), 0)).where(
            ApplicationEvent.application_id == application_id
        )
    )
    final_status = {
        "APPROVED": "DECISION",
        "REJECTED": "REJECTED",
    }[review.outcome]
    application.status = final_status
    session.add(
        ApplicationEvent(
            application_id=application.id,
            sequence=int(last_sequence or 0) + 1,
            event_type="APPLICATION_REVIEW_RECORDED",
            from_status="MANUAL_REVIEW",
            to_status=final_status,
            actor_type="USER",
            actor_user_id=reviewer_user_id,
            details={
                "review_id": str(review.id),
                "decision_id": str(decision.id),
                "ai_outcome": decision.outcome,
                "ai_source": decision.source,
                "review_outcome": review.outcome,
            },
        )
    )

    await session.commit()
    await session.refresh(application)
    await session.refresh(decision)
    await session.refresh(review)
    return application, decision, review
