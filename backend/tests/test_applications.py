from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import inspect, select, text

from app.database import engine, session_factory
from app.main import app
from app.integrations.credit_history import (
    CreditHistoryData,
    CreditHistoryProviderError,
    get_credit_history_provider,
)

from app.models import (
    Application,
    ApplicationEvent,
    ApplicationSnapshot,
    Company,
    CreditHistory,
    Financials,
    User,
)


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
            if company_id is not None:
                financials = await session.get(Financials, company_id)
                if financials is not None:
                    await session.delete(financials)
                credit_history = await session.get(CreditHistory, company_id)
                if credit_history is not None:
                    await session.delete(credit_history)
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
            other_submit = await client.post(
                f"/api/v1/applications/{second_created.json()['id']}/submit",
                headers=first_headers,
            )

        assert first_list.status_code == 200, first_list.text
        assert [item["id"] for item in first_list.json()] == [
            first_created.json()["id"]
        ]
        assert first_detail.status_code == 200
        assert first_detail.json() == first_created.json()
        assert other_detail.status_code == 404
        assert other_submit.status_code == 404
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


@pytest.mark.asyncio
async def test_submit_application_prepares_data_and_moves_to_scoring() -> None:
    email = ""
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            email, headers = await _register_company_user(client)
            products = await client.get("/api/v1/credit-products")
            created = await _create_draft(client, headers, products.json()[0])
            assert created.status_code == 201

            response = await client.post(
                f"/api/v1/applications/{created.json()['id']}/submit",
                headers=headers,
            )
            repeated = await client.post(
                f"/api/v1/applications/{created.json()['id']}/submit",
                headers=headers,
            )
            history = await client.get(
                f"/api/v1/applications/{created.json()['id']}/history",
                headers=headers,
            )
            financial_update = await client.patch(
                "/api/v1/company/financials",
                headers=headers,
                json={"revenue_annual": 99_000_000},
            )
            edit_after_submit = await client.patch(
                f"/api/v1/applications/{created.json()['id']}",
                headers=headers,
                json={"purpose": "Изменение после отправки"},
            )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "SCORING"
        assert repeated.status_code == 200
        assert repeated.json() == response.json()
        assert financial_update.status_code == 200
        assert financial_update.json()["revenue_annual"] == 99_000_000.0
        assert edit_after_submit.status_code == 409
        assert history.status_code == 200
        assert [event["sequence"] for event in history.json()] == [1, 2, 3, 4, 5]
        assert [event["to_status"] for event in history.json()] == [
            "DRAFT",
            "SUBMITTED",
            "DATA_CHECK",
            "DATA_ENRICHMENT",
            "SCORING",
        ]
        assert history.json()[0]["event_type"] == "APPLICATION_DRAFT_CREATED"
        assert history.json()[0]["actor_type"] == "USER"
        assert history.json()[1]["actor_type"] == "USER"
        assert all(event["actor_type"] == "SYSTEM" for event in history.json()[2:])

        application_id = created.json()["id"]
        company_id = created.json()["company_id"]
        async with session_factory() as session:
            snapshot = await session.scalar(
                select(ApplicationSnapshot).where(
                    ApplicationSnapshot.application_id == application_id
                )
            )
            events = list(await session.scalars(
                select(ApplicationEvent)
                .where(ApplicationEvent.application_id == application_id)
                .order_by(ApplicationEvent.sequence)
            ))
            saved_application = await session.get(Application, application_id)
            saved_financials = await session.get(Financials, company_id)
            saved_history = await session.get(CreditHistory, company_id)

        assert saved_application is not None
        assert saved_application.status == "SCORING"
        assert snapshot is not None
        assert snapshot.schema_version == 1
        assert snapshot.payload["financials"]["revenue_annual"] == "12500000.00"
        assert snapshot.payload["financials"]["source"] == "DEMO"
        assert snapshot.payload["credit_history"]["source"] == "DEMO"
        assert snapshot.payload["application"]["purpose"] == "Пополнение оборотных средств"
        assert saved_financials is not None
        assert saved_financials.revenue_annual == Decimal("99000000")
        assert saved_history is not None
        assert saved_history.source == "DEMO"
        assert len(events) == 5
    finally:
        if email:
            await _cleanup_user(email)
        await engine.dispose()


class _FailingCreditHistoryProvider:
    async def get_by_inn(self, inn: str) -> CreditHistoryData:
        raise CreditHistoryProviderError("provider offline")


@pytest.mark.asyncio
async def test_submission_provider_failure_leaves_application_unchanged() -> None:
    email = ""
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            email, headers = await _register_company_user(client)
            products = await client.get("/api/v1/credit-products")
            created = await _create_draft(client, headers, products.json()[0])
            application_id = created.json()["id"]
            company_id = created.json()["company_id"]
            app.dependency_overrides[get_credit_history_provider] = (
                _FailingCreditHistoryProvider
            )

            response = await client.post(
                f"/api/v1/applications/{application_id}/submit",
                headers=headers,
            )

        assert response.status_code == 502
        async with session_factory() as session:
            saved_application = await session.get(Application, application_id)
            financials = await session.get(Financials, company_id)
            credit_history = await session.get(CreditHistory, company_id)
            snapshot = await session.scalar(
                select(ApplicationSnapshot).where(
                    ApplicationSnapshot.application_id == application_id
                )
            )
            events = list(await session.scalars(
                select(ApplicationEvent).where(
                    ApplicationEvent.application_id == application_id
                )
            ))

        assert saved_application is not None
        assert saved_application.status == "DRAFT"
        assert financials is None
        assert credit_history is None
        assert snapshot is None
        assert len(events) == 1
        assert events[0].event_type == "APPLICATION_DRAFT_CREATED"
        assert events[0].to_status == "DRAFT"
    finally:
        app.dependency_overrides.pop(get_credit_history_provider, None)
        if email:
            await _cleanup_user(email)
        await engine.dispose()
