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
