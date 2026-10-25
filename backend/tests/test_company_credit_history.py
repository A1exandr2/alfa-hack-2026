from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.database import engine, session_factory
from app.main import app
from app.models import Company, CreditHistory, User


@pytest.mark.asyncio
async def test_get_credit_history_loads_and_reuses_demo_snapshot() -> None:
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
            headers = {"Authorization": f"Bearer {register.json()['access_token']}"}

            link = await client.post(
                "/api/v1/company/link",
                headers=headers,
                json={"inn": inn},
            )
            assert link.status_code == 200

            first_response = await client.get(
                "/api/v1/company/credit-history", headers=headers
            )
            assert first_response.status_code == 200
            first = first_response.json()
            assert first["active_credits"] == 2
            assert first["closed_credits"] == 5
            assert first["overdue_count"] == 0
            assert first["overdue_amount"] == 0.0
            assert first["source"] == "DEMO"
            assert first["updated_at"]

            company_id = UUID(link.json()["id"])
            async with session_factory() as session:
                saved = await session.get(CreditHistory, company_id)
                assert saved is not None
                assert saved.active_credits == 2
                assert saved.closed_credits == 5
                assert saved.overdue_count == 0
                assert saved.overdue_amount == 0
                assert saved.source == "DEMO"

            second_response = await client.get(
                "/api/v1/company/credit-history", headers=headers
            )
            assert second_response.status_code == 200
            assert second_response.json() == first
    finally:
        async with session_factory() as session:
            user = await session.scalar(select(User).where(User.email == email))
            company_id = user.company_id if user is not None else None
            if user is not None:
                await session.delete(user)
            if company_id is not None:
                credit_history = await session.get(CreditHistory, company_id)
                if credit_history is not None:
                    await session.delete(credit_history)
                company = await session.get(Company, company_id)
                if company is not None:
                    await session.delete(company)
            await session.commit()
        await engine.dispose()
