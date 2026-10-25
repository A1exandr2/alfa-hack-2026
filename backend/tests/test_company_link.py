from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.database import engine, session_factory
from app.main import app
from app.models import Company, User


@pytest.mark.asyncio
async def test_user_can_link_company_and_read_it() -> None:
    email = f"{uuid4()}@example.com"
    inn = str(uuid4().int)[:10]

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            register = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": email,
                    "password": "StrongPass123!",
                    "full_name": "Иван Иванов",
                },
            )
            assert register.status_code == 201
            token = register.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            missing_company = await client.get("/api/v1/company", headers=headers)
            assert missing_company.status_code == 404

            link = await client.post(
                "/api/v1/company/link",
                headers=headers,
                json={"inn": inn},
            )
            assert link.status_code == 200
            linked_company = link.json()
            assert linked_company["inn"] == inn
            assert linked_company["name"] == f"Демо-компания {inn}"
            assert linked_company["data_source"] == "DEMO"

            company = await client.get("/api/v1/company", headers=headers)
            assert company.status_code == 200
            assert company.json() == linked_company

            current_user = await client.get("/api/v1/auth/me", headers=headers)
            assert current_user.json()["company_id"] == linked_company["id"]
    finally:
        async with session_factory() as session:
            user = await session.scalar(select(User).where(User.email == email))
            company_id = user.company_id if user is not None else None
            if user is not None:
                await session.delete(user)
            if company_id is not None:
                company = await session.get(Company, company_id)
                if company is not None:
                    await session.delete(company)
            await session.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_unlink_removes_only_user_link_and_allows_another_company() -> None:
    email = f"unlink-{uuid4()}@example.com"
    ids = []
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            auth = await client.post('/api/v1/auth/register', json={'email':email,'password':'StrongPass123!','full_name':'Test'})
            headers={'Authorization':f"Bearer {auth.json()['access_token']}"}
            assert (await client.delete('/api/v1/company')).status_code == 401
            for _ in range(2):
                linked = await client.post('/api/v1/company/link', headers=headers,json={'inn':str(uuid4().int)[:10]})
                assert linked.status_code == 200
                ids.append(linked.json()['id'])
                assert (await client.delete('/api/v1/company',headers=headers)).status_code == 204
                assert (await client.get('/api/v1/company',headers=headers)).status_code == 404
                assert (await client.get('/api/v1/auth/me',headers=headers)).json()['company_id'] is None
            async with session_factory() as session:
                from uuid import UUID
                for company_id in ids:
                    assert await session.get(Company,UUID(company_id)) is not None
    finally:
        async with session_factory() as session:
            user=await session.scalar(select(User).where(User.email==email))
            if user is not None:
                await session.delete(user)
                await session.flush()
            from uuid import UUID
            for company_id in ids:
                record=await session.get(Company,UUID(company_id))
                if record is not None:
                    await session.delete(record)
            await session.commit()
        await engine.dispose()
