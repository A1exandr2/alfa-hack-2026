from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.schemas import StaffReviewRequest, UserAccessUpdate
from app.applications.review import review_application
from app.applications.schemas import (ApplicationResponse, ApplicationDecisionResponse,
    ApplicationEventResponse, ApplicationReviewRecordResponse, ApplicationReviewRequest)
from app.applications.service import ApplicationError
from app.auth.dependencies import get_current_admin, get_current_reviewer
from app.database import get_db_session
from app.models import (AdminAudit, Application, ApplicationDecision, ApplicationEvent,
    ApplicationReview, ApplicationSnapshot, Company, User)

router = APIRouter(prefix='/api/v1/admin', tags=['administration'])


def user_data(user, company_name=None):
    return dict(id=user.id, email=user.email, full_name=user.full_name, role=user.role,
                is_active=user.is_active, company_id=user.company_id, company_name=company_name)


@router.get('/overview')
async def overview(user: User = Depends(get_current_admin), session: AsyncSession = Depends(get_db_session)):
    statuses = dict((await session.execute(select(Application.status, func.count()).group_by(Application.status))).all())
    return dict(users=await session.scalar(select(func.count()).select_from(User)),
                companies=await session.scalar(select(func.count()).select_from(Company)),
                applications=sum(statuses.values()), statuses=statuses,
                blocked_users=await session.scalar(select(func.count()).select_from(User).where(User.is_active.is_(False))))


@router.get('/users')
async def users(q: str = Query('', max_length=100), offset: int = Query(0, ge=0),
                limit: int = Query(25, ge=1, le=100), user: User = Depends(get_current_admin),
                session: AsyncSession = Depends(get_db_session)):
    filters = [or_(User.email.icontains(q, autoescape=True), User.full_name.icontains(q, autoescape=True))] if q else []
    rows = (await session.execute(select(User, Company.name).outerjoin(Company, User.company_id == Company.id)
             .where(*filters).order_by(User.email, User.id).offset(offset).limit(limit))).all()
    total = await session.scalar(select(func.count()).select_from(User).where(*filters))
    return dict(items=[user_data(u, name) for u, name in rows], total=total, offset=offset, limit=limit)


@router.patch('/users/{target_id}')
async def update_user(target_id: UUID, payload: UserAccessUpdate,
                      actor: User = Depends(get_current_admin), session: AsyncSession = Depends(get_db_session)):
    target = await session.scalar(select(User).where(User.id == target_id).with_for_update())
    if target is None:
        raise HTTPException(404, 'Пользователь не найден')
    if target.id == actor.id or target.role == 'ADMIN':
        raise HTTPException(409, 'Доступ администратора изменяется только серверной командой')
    reason = payload.reason.strip()
    if len(reason) < 3:
        raise HTTPException(422, 'Укажите причину изменения доступа')
    before = dict(role=target.role, is_active=target.is_active)
    after = dict(role=payload.role, is_active=payload.is_active)
    if before != after:
        target.role, target.is_active = payload.role, payload.is_active
        session.add(AdminAudit(actor_user_id=actor.id, actor_email=actor.email, action='USER_ACCESS_CHANGED', target_id=target.id,
                               details=dict(before=before, after=after, reason=reason)))
        await session.commit()
    return user_data(target)


@router.get('/applications')
async def applications(q: str = Query('', max_length=100), status: str = Query('', max_length=32),
                       offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
                       user: User = Depends(get_current_reviewer), session: AsyncSession = Depends(get_db_session)):
    filters = []
    if status:
        filters.append(Application.status == status)
    if q:
        filters.append(or_(Company.inn.icontains(q, autoescape=True), Company.name.icontains(q, autoescape=True),
                           cast(Application.id, String).icontains(q, autoescape=True)))
    query = select(Application, Company.name, Company.inn, User.email).join(Company, Application.company_id == Company.id).join(User, Application.user_id == User.id).where(*filters)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = (await session.execute(query.order_by(Application.created_at.desc(), Application.id).offset(offset).limit(limit))).all()
    return dict(items=[dict(**ApplicationResponse.model_validate(a).model_dump(), company_name=name,
                           inn=inn, owner_email=email) for a, name, inn, email in rows], total=total, offset=offset, limit=limit)


@router.get('/applications/{application_id}')
async def application_details(application_id: UUID, user: User = Depends(get_current_reviewer),
                              session: AsyncSession = Depends(get_db_session)):
    a = await session.get(Application, application_id)
    if a is None:
        raise HTTPException(404, 'Заявка не найдена')
    company = await session.get(Company, a.company_id)
    owner = await session.get(User, a.user_id)
    decision = await session.scalar(select(ApplicationDecision).where(ApplicationDecision.application_id == a.id))
    review = await session.scalar(select(ApplicationReview).where(ApplicationReview.application_id == a.id))
    events = (await session.scalars(select(ApplicationEvent).where(ApplicationEvent.application_id == a.id).order_by(ApplicationEvent.sequence))).all()
    snapshots = (await session.scalars(select(ApplicationSnapshot).where(ApplicationSnapshot.application_id == a.id).order_by(ApplicationSnapshot.snapshot_version.desc()).limit(20))).all()
    return dict(application=ApplicationResponse.model_validate(a), company=dict(name=company.name, inn=company.inn),
                owner=dict(full_name=owner.full_name, email=owner.email),
                decision=ApplicationDecisionResponse.model_validate(decision) if decision else None,
                review=ApplicationReviewRecordResponse.model_validate(review) if review else None,
                events=[ApplicationEventResponse.model_validate(e) for e in events],
                snapshots=[dict(version=s.snapshot_version, captured_at=s.captured_at, data=s.payload) for s in snapshots])


@router.post('/applications/{application_id}/review')
async def review(application_id: UUID, payload: StaffReviewRequest,
                 user: User = Depends(get_current_reviewer), session: AsyncSession = Depends(get_db_session)):
    comment = payload.comment.strip()
    if len(comment) < 3:
        raise HTTPException(422, 'Добавьте обоснование решения')
    try:
        a, decision, record = await review_application(session, user.id, application_id,
                    ApplicationReviewRequest(outcome=payload.outcome, comment=comment))
    except ApplicationError as error:
        await session.rollback()
        raise HTTPException(error.status_code, str(error)) from error
    return dict(status=a.status, review=ApplicationReviewRecordResponse.model_validate(record))


@router.get('/audit')
async def audit(offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
                user: User = Depends(get_current_admin), session: AsyncSession = Depends(get_db_session)):
    rows = (await session.execute(select(AdminAudit, AdminAudit.actor_email)
            .order_by(AdminAudit.created_at.desc(), AdminAudit.id).offset(offset).limit(limit))).all()
    return dict(items=[dict(id=e.id, actor_email=email, action=e.action, target_id=e.target_id,
                           details=e.details, created_at=e.created_at) for e,email in rows],
                total=await session.scalar(select(func.count()).select_from(AdminAudit)), offset=offset, limit=limit)
