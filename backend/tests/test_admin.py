from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select
from app.auth.security import create_access_token, hash_password
from app.database import engine, session_factory
from app.main import app
from app.models import (AdminAudit, Application, ApplicationDecision, ApplicationSnapshot,
                        Company, CreditProduct, User)


@pytest.mark.asyncio
async def test_admin_access_roles_blocking_and_audit():
    ids = [uuid4() for _ in range(4)]
    password = 'A-long-test-password_847!'
    async with session_factory() as session:
        for id,role in zip(ids,['ADMIN','USER','REVIEWER','ADMIN']):
            session.add(User(id=id,email=f'{id}@example.com',full_name='Access test',
                             password_hash=hash_password(password),role=role))
        await session.commit()
    headers=lambda i: {'Authorization':'Bearer '+create_access_token(ids[i])}
    try:
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            assert (await client.get('/api/v1/admin/users')).status_code == 401
            for i in [1,2]:
                for url in ['overview','users','audit']:
                    assert (await client.get('/api/v1/admin/'+url,headers=headers(i))).status_code==403
            assert (await client.get('/api/v1/admin/applications',headers=headers(2))).status_code==200
            assert (await client.get('/api/v1/admin/applications',headers=headers(1))).status_code==403
            listed=await client.get('/api/v1/admin/users',headers=headers(0),params={'q':str(ids[1])})
            assert listed.status_code==200
            assert listed.json()['total']==1
            assert 'password_hash' not in listed.text
            assert (await client.get('/api/v1/admin/users?limit=101',headers=headers(0))).status_code==422
            payload=dict(role='REVIEWER',is_active=True,reason='Назначение проверяющего')
            for target in [ids[0],ids[3]]:
                assert (await client.patch(f'/api/v1/admin/users/{target}',headers=headers(0),json=payload)).status_code==409
            assert (await client.patch(f'/api/v1/admin/users/{ids[1]}',headers=headers(0),json={**payload,'role':'ADMIN'})).status_code==422
            assert (await client.patch(f'/api/v1/admin/users/{ids[1]}',headers=headers(0),json=payload)).status_code==200
            # Previously issued token gets its rights from the current database row.
            assert (await client.get('/api/v1/admin/applications',headers=headers(1))).status_code==200
            assert (await client.patch(f'/api/v1/admin/users/{ids[1]}',headers=headers(0),json={**payload,'is_active':False})).status_code==200
            assert (await client.get('/api/v1/auth/me',headers=headers(1))).status_code==401
            assert (await client.post('/api/v1/auth/login',json={'email':f'{ids[1]}@example.com','password':password})).status_code==401
            logs=await client.get('/api/v1/admin/audit',headers=headers(0))
            changes=[e for e in logs.json()['items'] if e['target_id']==str(ids[1])]
            assert len(changes)==2
            assert changes[0]['details']['before']=={'role':'REVIEWER','is_active':True}
            assert changes[0]['details']['after']=={'role':'REVIEWER','is_active':False}
            assert changes[0]['actor_email']==f'{ids[0]}@example.com'
            assert (await client.post('/api/v1/auth/register',json={'email':f'{uuid4()}@example.com','password':password,'full_name':'Escalation','role':'ADMIN'})).status_code==422
    finally:
        async with session_factory() as session:
            await session.execute(delete(AdminAudit).where(AdminAudit.actor_user_id.in_(ids)))
            await session.execute(delete(User).where(User.id.in_(ids)))
            await session.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_staff_reviews_cross_company_preserving_snapshot_and_decision():
    admin_id, owner_id, company_id, app_id, snapshot_id = [uuid4() for _ in range(5)]
    async with session_factory() as session:
        product=await session.scalar(select(CreditProduct).limit(1))
        session.add(Company(id=company_id,name='Очередь проверки',inn=str(uuid4().int)[:10]))
        await session.flush()
        session.add_all([User(id=admin_id,email=f'{admin_id}@example.com',full_name='Admin',password_hash='unused',role='ADMIN'),
                         User(id=owner_id,email=f'{owner_id}@example.com',full_name='Owner',password_hash='unused',company_id=company_id)])
        await session.flush()
        session.add(Application(id=app_id,user_id=owner_id,company_id=company_id,product_id=product.id,
                                requested_amount=100000,term_months=12,purpose='Тест ручной проверки',status='MANUAL_REVIEW'))
        await session.flush()
        session.add(ApplicationSnapshot(id=snapshot_id,application_id=app_id,snapshot_version=1,schema_version=1,payload={'marker':'immutable','financials':{'source':'USER_INPUT'}}))
        await session.flush()
        session.add(ApplicationDecision(application_id=app_id,snapshot_id=snapshot_id,outcome='CONDITIONAL_APPROVAL',source='AI',
            risk_score=Decimal('45'),risk_level='Medium',explanation='Проверить документы',recommended_product='Оборотный',
            next_step='Ручная проверка',top_factors=['Проверить источник'],conditions=['Проверить отчётность']))
        await session.commit()
    headers={'Authorization':'Bearer '+create_access_token(admin_id)}
    owner_headers={'Authorization':'Bearer '+create_access_token(owner_id)}
    try:
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            base=f'/api/v1/admin/applications/{app_id}'
            assert (await client.get(base,headers=owner_headers)).status_code==403
            listing=await client.get('/api/v1/admin/applications',headers=headers,params={'q':str(app_id),'status':'MANUAL_REVIEW'})
            assert listing.json()['total']==1
            assert listing.json()['items'][0]['company_name']=='Очередь проверки'
            before=(await client.get(base,headers=headers)).json()
            assert before['snapshots'][0]['data']['marker']=='immutable'
            assert (await client.post(base+'/review',headers=headers,json={'outcome':'APPROVED','comment':' '})).status_code==422
            payload={'outcome':'REJECTED','comment':'Проверены документы: сведения не подтверждены'}
            for _ in range(2):
                result=await client.post(base+'/review',headers=headers,json=payload)
                assert result.status_code==200,result.text
                assert result.json()['status']=='REJECTED'
            after=(await client.get(base,headers=headers)).json()
            assert after['snapshots']==before['snapshots']
            assert after['decision']==before['decision']
            assert after['review']['comment']==payload['comment']
            assert after['events'][-1]['event_type']=='APPLICATION_REVIEW_RECORDED'
            assert (await client.post(base+'/review',headers=headers,json={**payload,'outcome':'APPROVED'})).status_code==409
            async with session_factory() as session:
                assert await session.scalar(select(func.count()).select_from(AdminAudit).where(AdminAudit.target_id==app_id))==1
    finally:
        async with session_factory() as session:
            await session.execute(delete(AdminAudit).where(AdminAudit.actor_user_id==admin_id))
            await session.execute(delete(Application).where(Application.id==app_id))
            await session.execute(delete(User).where(User.id.in_([admin_id,owner_id])))
            await session.execute(delete(Company).where(Company.id==company_id))
            await session.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_configured_admin_alias_requires_admin_role_and_rotated_password(monkeypatch):
    from app.config import get_settings
    from app.admin.bootstrap import provision
    from app.auth.security import verify_password
    admin_id, other_id=uuid4(),uuid4()
    old_email=f'{admin_id}@example.com'
    new_email=f'admin-{admin_id}@example.com'
    old_password='Old-random-password-only-in-test!'
    new_password='New-random-password-only-in-test!'
    async with session_factory() as session:
        session.add(User(id=admin_id,email=old_email,full_name='Admin',role='ADMIN',password_hash=hash_password(old_password)))
        session.add(User(id=other_id,email=f'{other_id}@example.com',full_name='User',role='USER',password_hash=hash_password(old_password)))
        await session.commit()
    monkeypatch.setenv('ADMIN_EMAIL',new_email)
    monkeypatch.setenv('ADMIN_LOGIN','Admin')
    get_settings.cache_clear()
    try:
        # Console rotation preserves the administrator identity and its audit history.
        await provision({'email':new_email,'password':new_password,'full_name':'Admin'},admin_id)
        await provision({'email':new_email,'password':'Ignored-on-existing-admin-password!','full_name':'Admin'},if_missing=True)
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            response=await client.post('/api/v1/auth/login',json={'email':'Admin','password':new_password})
            assert response.status_code==200
            assert response.json()['user']['id']==str(admin_id)
            assert (await client.post('/api/v1/auth/login',json={'email':new_email,'password':old_password})).status_code==401
            assert (await client.post('/api/v1/auth/login',json={'email':old_email,'password':old_password})).status_code==401
            async with session_factory() as session:
                user=await session.get(User,admin_id)
                assert verify_password(new_password,user.password_hash)
                assert not verify_password(old_password,user.password_hash)
                user.role='USER';await session.commit()
            # An email match alone never gives a regular user the Admin alias.
            assert (await client.post('/api/v1/auth/login',json={'email':'Admin','password':new_password})).status_code==401
        with pytest.raises(ValueError):
            await provision({'email':new_email,'password':new_password},other_id)
    finally:
        get_settings.cache_clear()
        async with session_factory() as session:
            await session.execute(delete(AdminAudit).where(AdminAudit.actor_user_id==admin_id))
            await session.execute(delete(User).where(User.id.in_([admin_id,other_id])))
            await session.commit()
        await engine.dispose()
