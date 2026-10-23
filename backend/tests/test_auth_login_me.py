from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.auth.security import hash_password
from app.database import engine, session_factory
from app.main import app
from app.models import Company, User


@pytest.mark.asyncio
async def test_login_returns_jwt_and_me_returns_current_user() -> None:
    company_id = uuid4()
    user_id = uuid4()
    email = f"{uuid4()}@example.com"
    password = "StrongPass123!"

    async with session_factory() as session:
        session.add(
            Company(
                id=company_id,
                name="ООО «Тест login»",
                inn=str(uuid4().int)[:10],
            )
        )
        session.add(
            User(
                id=user_id,
                email=email,
                password_hash=hash_password(password),
                full_name="Иван Иванов",
                company_id=company_id,
            )
        )
        await session.commit()

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            login_response = await client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": password},
            )

            assert login_response.status_code == 200
            login_body = login_response.json()
            assert login_body["user"]["id"] == str(user_id)
            assert login_body["user"]["role"] == "USER"
            assert login_body["token_type"] == "bearer"
            assert login_body["access_token"]

            me_response = await client.get(
                "/api/v1/auth/me",
                headers={
                    "Authorization": f"Bearer {login_body['access_token']}"
                },
            )

            assert me_response.status_code == 200
            assert me_response.json() == {
                "id": str(user_id),
                "email": email,
                "full_name": "Иван Иванов",
                "role": "USER",
                "company_id": str(company_id),
            }
    finally:
        async with session_factory() as session:
            user = await session.scalar(select(User).where(User.id == user_id))
            if user is not None:
                await session.delete(user)
            company = await session.get(Company, company_id)
            if company is not None:
                await session.delete(company)
            await session.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_login_rejects_invalid_password() -> None:
    company_id = uuid4()
    user_id = uuid4()
    email = f"{uuid4()}@example.com"

    async with session_factory() as session:
        session.add(
            Company(
                id=company_id,
                name="ООО «Тест invalid»",
                inn=str(uuid4().int)[:10],
            )
        )
        session.add(
            User(
                id=user_id,
                email=email,
                password_hash=hash_password("StrongPass123!"),
                full_name="Пётр Петров",
                company_id=company_id,
            )
        )
        await session.commit()

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "WrongPass123!"},
            )

        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid email or password"}
    finally:
        async with session_factory() as session:
            user = await session.scalar(select(User).where(User.id == user_id))
            if user is not None:
                await session.delete(user)
            company = await session.get(Company, company_id)
            if company is not None:
                await session.delete(company)
            await session.commit()
        await engine.dispose()
