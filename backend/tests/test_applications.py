from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import inspect, select, text

from app.database import engine, session_factory
from app.main import app
from app.models import Company, User


@pytest.mark.asyncio
async def test_user_can_create_application_draft() -> None:
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

            company = await client.post(
                "/api/v1/company/link", headers=headers, json={"inn": inn}
            )
            assert company.status_code == 200
            products = await client.get("/api/v1/credit-products")
            assert products.status_code == 200
            product = products.json()[0]
            product_id = product["id"]
            requested_amount = str(product["min_amount"])

            response = await client.post(
                "/api/v1/applications",
                headers=headers,
                json={
                    "product_id": product_id,
                    "requested_amount": requested_amount,
                    "term_months": 12,
                    "purpose": "Пополнение оборотных средств",
                },
            )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["company_id"] == company.json()["id"]
        assert body["product_id"] == product_id
        assert Decimal(body["requested_amount"]) == Decimal(requested_amount)
        assert body["term_months"] == 12
        assert body["purpose"] == "Пополнение оборотных средств"
        assert body["status"] == "DRAFT"
        assert body["created_at"]
        assert body["updated_at"]
    finally:
        async with session_factory() as session:
            user = await session.scalar(select(User).where(User.email == email))
            if user is not None:
                company_id = user.company_id
                connection = await session.connection()
                has_applications = await connection.run_sync(
                    lambda sync_connection: inspect(sync_connection).has_table(
                        "applications"
                    )
                )
                if has_applications:
                    await session.execute(
                        text("DELETE FROM applications WHERE user_id = :user_id"),
                        {"user_id": user.id},
                    )
                await session.delete(user)
                await session.flush()
                if company_id is not None:
                    company = await session.get(Company, company_id)
                    if company is not None:
                        await session.delete(company)
                await session.commit()
        await engine.dispose()


async def _register_company_user(client: AsyncClient) -> tuple[str, dict]:
    email = f"{uuid4()}@example.com"
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
    company = await client.post(
        "/api/v1/company/link",
        headers=headers,
        json={"inn": str(uuid4().int)[:10]},
    )
    assert company.status_code == 200
    return email, headers


async def _create_draft(client: AsyncClient, headers: dict, product: dict):
    return await client.post(
        "/api/v1/applications",
        headers=headers,
        json={
            "product_id": product["id"],
            "requested_amount": str(product["min_amount"]),
            "term_months": product["min_term_months"],
            "purpose": "Пополнение оборотных средств",
        },
    )


async def _cleanup_user(email: str) -> None:
    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.email == email))
        if user is not None:
            company_id = user.company_id
            await session.execute(
                text("DELETE FROM applications WHERE user_id = :user_id"),
                {"user_id": user.id},
            )
            await session.delete(user)
            await session.flush()
            if company_id is not None:
                company = await session.get(Company, company_id)
                if company is not None:
                    await session.delete(company)
            await session.commit()


@pytest.mark.asyncio
async def test_user_can_list_and_read_only_their_applications() -> None:
    first_email = second_email = ""
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            first_email, first_headers = await _register_company_user(client)
            second_email, second_headers = await _register_company_user(client)
            products = await client.get("/api/v1/credit-products")
            product = products.json()[0]
            first_created = await _create_draft(client, first_headers, product)
            second_created = await _create_draft(client, second_headers, product)
            assert first_created.status_code == 201
            assert second_created.status_code == 201

            first_list = await client.get(
                "/api/v1/applications", headers=first_headers
            )
            first_detail = await client.get(
                f"/api/v1/applications/{first_created.json()['id']}",
                headers=first_headers,
            )
            other_detail = await client.get(
                f"/api/v1/applications/{second_created.json()['id']}",
                headers=first_headers,
            )

        assert first_list.status_code == 200, first_list.text
        assert [item["id"] for item in first_list.json()] == [
            first_created.json()["id"]
        ]
        assert first_detail.status_code == 200
        assert first_detail.json() == first_created.json()
        assert other_detail.status_code == 404
    finally:
        if first_email:
            await _cleanup_user(first_email)
        if second_email:
            await _cleanup_user(second_email)
        await engine.dispose()


@pytest.mark.asyncio
async def test_user_can_update_draft_and_invalid_updates_are_rejected() -> None:
    email = ""
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            email, headers = await _register_company_user(client)
            products = await client.get("/api/v1/credit-products")
            product = products.json()[0]
            created = await _create_draft(client, headers, product)
            assert created.status_code == 201
            application_id = created.json()["id"]

            updated = await client.patch(
                f"/api/v1/applications/{application_id}",
                headers=headers,
                json={"purpose": "Закупка оборудования"},
            )
            invalid_amount = await client.patch(
                f"/api/v1/applications/{application_id}",
                headers=headers,
                json={"requested_amount": str(product["max_amount"] + 1)},
            )
            empty_update = await client.patch(
                f"/api/v1/applications/{application_id}",
                headers=headers,
                json={},
            )
            unchanged = await client.get(
                f"/api/v1/applications/{application_id}", headers=headers
            )

        assert updated.status_code == 200, updated.text
        assert updated.json()["purpose"] == "Закупка оборудования"
        assert invalid_amount.status_code == 422
        assert empty_update.status_code == 422
        assert unchanged.json()["purpose"] == "Закупка оборудования"
    finally:
        if email:
            await _cleanup_user(email)
        await engine.dispose()


@pytest.mark.asyncio
async def test_application_requires_linked_company_and_product_limits() -> None:
    email = f"{uuid4()}@example.com"
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
            headers = {
                "Authorization": f"Bearer {register.json()['access_token']}"
            }
            products = await client.get("/api/v1/credit-products")
            product = products.json()[0]
            valid_payload = {
                "product_id": product["id"],
                "requested_amount": str(product["min_amount"]),
                "term_months": product["min_term_months"],
                "purpose": "Пополнение оборотных средств",
            }
            without_company = await client.post(
                "/api/v1/applications", headers=headers, json=valid_payload
            )
            link = await client.post(
                "/api/v1/company/link",
                headers=headers,
                json={"inn": str(uuid4().int)[:10]},
            )
            below_minimum = await client.post(
                "/api/v1/applications",
                headers=headers,
                json={
                    **valid_payload,
                    "requested_amount": str(
                        Decimal(str(product["min_amount"])) - Decimal("1")
                    ),
                },
            )
            outside_term = await client.post(
                "/api/v1/applications",
                headers=headers,
                json={
                    **valid_payload,
                    "term_months": product["min_term_months"] - 1,
                },
            )
            unknown_product = await client.post(
                "/api/v1/applications",
                headers=headers,
                json={
                    **valid_payload,
                    "product_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
                },
            )

        assert link.status_code == 200
        assert without_company.status_code == 409
        assert below_minimum.status_code == 422
        assert outside_term.status_code == 422
        assert unknown_product.status_code == 404
    finally:
        await _cleanup_user(email)
        await engine.dispose()
