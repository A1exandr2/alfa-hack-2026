import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from uuid import uuid4

from app.database import engine, session_factory
from app.main import app
from app.models import Company, User


@pytest.mark.asyncio
async def test_register_creates_user_in_postgres_and_returns_token() -> None:
    email = f"{uuid4()}@example.com"
    inn = str(uuid4().int)[:10]

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": email,
                    "password": "StrongPass123!",
                    "full_name": "Иван Иванов",
                    "inn": inn,
                },
            )

        assert response.status_code == 201
        body = response.json()
        assert body["user"]["email"] == email
        assert body["access_token"]
        assert body["token_type"] == "bearer"

        async with session_factory() as session:
            user = await session.scalar(select(User).where(User.email == email))
            assert user is not None
            assert user.password_hash != "StrongPass123!"
            company = await session.get(Company, user.company_id)
            assert company is not None
            assert company.inn == inn
            assert body["user"]["company_id"] == str(company.id)
    finally:
        async with session_factory() as session:
            user = await session.scalar(select(User).where(User.email == email))
            if user is not None:
                await session.delete(user)
            company = await session.scalar(select(Company).where(Company.inn == inn))
            if company is not None:
                await session.delete(company)
            await session.commit()
        await engine.dispose()
