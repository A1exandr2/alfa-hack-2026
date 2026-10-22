import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from uuid import uuid4

from app.database import engine, session_factory
from app.main import app
from app.models import User


@pytest.mark.asyncio
async def test_register_creates_user_without_linking_company() -> None:
    email = f"{uuid4()}@example.com"

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": email,
                    "password": "StrongPass123!",
                    "full_name": "Иван Иванов",
                },
            )

        assert response.status_code == 201
        body = response.json()
        assert body["user"]["email"] == email
        assert body["user"]["company_id"] is None
        assert body["access_token"]
        assert body["token_type"] == "bearer"

        async with session_factory() as session:
            user = await session.scalar(select(User).where(User.email == email))
            assert user is not None
            assert user.password_hash != "StrongPass123!"
            assert user.company_id is None
    finally:
        async with session_factory() as session:
            user = await session.scalar(select(User).where(User.email == email))
            if user is not None:
                await session.delete(user)
            await session.commit()
        await engine.dispose()
