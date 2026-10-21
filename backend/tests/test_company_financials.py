from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.database import engine, session_factory
from app.main import app
from app.models import Company, Financials, User


@pytest.mark.asyncio
async def test_get_financials_loads_demo_data_and_persists_it() -> None:
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
            headers = {
                "Authorization": f"Bearer {register.json()['access_token']}"
            }
            link = await client.post(
                "/api/v1/company/link",
                headers=headers,
                json={"inn": inn},
            )
            assert link.status_code == 200

            first_response = await client.get(
                "/api/v1/company/financials", headers=headers
            )
            assert first_response.status_code == 200
            first = first_response.json()
            assert first["revenue_annual"] == 12_500_000.0
            assert first["profit_annual"] == 2_100_000.0
            assert first["expenses_annual"] == 10_400_000.0
            assert first["employees"] == 8
            assert first["current_debt"] == 800_000.0
            assert first["source"] == "DEMO"
            assert first["updated_at"]

            second_response = await client.get(
                "/api/v1/company/financials", headers=headers
            )
            assert second_response.json() == first

        company_id = link.json()["id"]
        async with session_factory() as session:
            saved = await session.get(Financials, company_id)
            assert saved is not None
            assert saved.revenue_annual == 12_500_000
            assert saved.expenses_annual == 10_400_000
            assert saved.employees == 8
            assert saved.source == "DEMO"
    finally:
        async with session_factory() as session:
            user = await session.scalar(select(User).where(User.email == email))
            company_id = user.company_id if user is not None else None
            if user is not None:
                await session.delete(user)
            if company_id is not None:
                financials = await session.get(Financials, company_id)
                if financials is not None:
                    await session.delete(financials)
                company = await session.get(Company, company_id)
                if company is not None:
                    await session.delete(company)
            await session.commit()
        await engine.dispose()
