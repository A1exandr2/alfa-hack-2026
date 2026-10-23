from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import inspect, select, text

from app.database import engine, session_factory
from app.main import app
import app.applications.workflow as application_workflow
from app.integrations.credit_history import (
    CreditHistoryData,
    CreditHistoryProviderError,
    get_credit_history_provider,
)
from ml.facade import score_and_explain as ml_score_and_explain
from ml.llm_assistant.schemas import CreditAdvice

from app.models import (
    Application,
    ApplicationDecision,
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
async def test_submit_application_persists_fallback_decision(monkeypatch) -> None:
    email = ""
    scoring_inputs: list[dict[str, Any]] = []

    def unavailable_ollama(self, **kwargs: Any) -> None:
        raise ConnectionError("Ollama is offline for this test")

    def fake_score_and_explain(**kwargs: Any) -> dict[str, Any]:
        scoring_inputs.append(kwargs)
        result = ml_score_and_explain(**kwargs)
        return result

    monkeypatch.setattr("ollama.Client.chat", unavailable_ollama)
    monkeypatch.setattr(
        application_workflow, "score_and_explain", fake_score_and_explain,
        raising=False,
    )
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
            decision_response = await client.get(
                f"/api/v1/applications/{created.json()['id']}/decision",
                headers=headers,
            )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "DECISION"
        assert response.json()["decision"]["outcome"] == "APPROVED"
        assert response.json()["decision"]["source"] == "Fallback_Rules"
        assert repeated.status_code == 200
        assert repeated.json() == response.json()
        assert decision_response.status_code == 200
        assert decision_response.json()["outcome"] == "APPROVED"
        assert decision_response.json()["source"] == "Fallback_Rules"
        assert financial_update.status_code == 200
        assert financial_update.json()["revenue_annual"] == 99_000_000.0
        assert edit_after_submit.status_code == 409
        assert history.status_code == 200
        assert [event["sequence"] for event in history.json()] == [1, 2, 3, 4, 5, 6]
        assert [event["to_status"] for event in history.json()] == [
            "DRAFT",
            "SUBMITTED",
            "DATA_CHECK",
            "DATA_ENRICHMENT",
            "SCORING",
            "DECISION",
        ]
        assert history.json()[0]["event_type"] == "APPLICATION_DRAFT_CREATED"
        assert history.json()[-1]["event_type"] == "APPLICATION_DECISION_RECORDED"
        assert history.json()[-1]["details"]["outcome"] == "APPROVED"
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
        assert saved_application.status == "DECISION"
        assert snapshot is not None
        assert snapshot.schema_version == 4
        assert snapshot.payload["financials"]["revenue_annual"] == "12500000.00"
        assert snapshot.payload["financials"]["source"] == "DEMO"
        assert snapshot.payload["credit_history"]["source"] == "DEMO"
        assert snapshot.payload["application"]["purpose"] == "Пополнение оборотных средств"
        assert saved_financials is not None
        assert saved_financials.revenue_annual == Decimal("99000000")
        assert saved_history is not None
        assert saved_history.source == "DEMO"
        assert len(events) == 6
        assert len(scoring_inputs) == 1
        scoring_input = scoring_inputs[0]
        assert scoring_input["company"]["company_age"] > 0
        assert scoring_input["financials"] == {
            "revenue": 12_500_000.0,
            "profit_margin": 2_100_000.0 / 12_500_000.0,
        }
        assert scoring_input["credit"] == {
            "has_overdue": 0,
            "debt_load": 800_000.0 / 12_500_000.0,
        }
        assert scoring_input["loan_amount"] == float(
            Decimal(created.json()["requested_amount"])
        )
        assert scoring_input["user_query"] == "Пополнение оборотных средств"
        assert scoring_input["loan_term_months"] == created.json()["term_months"]
        assert scoring_input["product"]["name"] == products.json()[0]["name"]
        risk_assessment = snapshot.payload["risk_assessment"]
        assert risk_assessment["risk_score"] == 25.0
        assert risk_assessment["risk_level"] == "Low"
        assert risk_assessment["decision"] == "APPROVED"
        assert risk_assessment["ai_advice"]["source"] == "Fallback_Rules"
        assert events[-1].event_type == "APPLICATION_DECISION_RECORDED"
        assert events[-1].details["risk_score"] == 25.0
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


@pytest.mark.asyncio
async def test_scoring_failure_rolls_back_submission(monkeypatch) -> None:
    email = ""

    def failing_score(**kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("scoring unavailable")

    monkeypatch.setattr(
        application_workflow,
        "score_and_explain",
        failing_score,
        raising=False,
    )
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            email, headers = await _register_company_user(client)
            products = await client.get("/api/v1/credit-products")
            created = await _create_draft(client, headers, products.json()[0])
            application_id = created.json()["id"]
            company_id = created.json()["company_id"]

            response = await client.post(
                f"/api/v1/applications/{application_id}/submit",
                headers=headers,
            )

        assert response.status_code == 502
        async with session_factory() as session:
            saved_application = await session.get(Application, application_id)
            snapshot = await session.scalar(
                select(ApplicationSnapshot).where(
                    ApplicationSnapshot.application_id == application_id
                )
            )
            events = list(
                await session.scalars(
                    select(ApplicationEvent).where(
                        ApplicationEvent.application_id == application_id
                    )
                )
            )
            saved_financials = await session.get(Financials, company_id)
            saved_history = await session.get(CreditHistory, company_id)

        assert saved_application is not None
        assert saved_application.status == "DRAFT"
        assert snapshot is None
        assert len(events) == 1
        assert saved_financials is None
        assert saved_history is None
    finally:
        if email:
            await _cleanup_user(email)
        await engine.dispose()


@pytest.mark.parametrize(
    ("outcome", "expected_status", "conditions"),
    [
        (
            "CONDITIONAL_APPROVAL",
            "MANUAL_REVIEW",
            ["Требуется ручная проверка финансовых данных."],
        ),
        ("REJECTED", "REJECTED", []),
    ],
)
@pytest.mark.asyncio
async def test_submission_persists_structured_llm_decision(
    monkeypatch, outcome: str, expected_status: str, conditions: list[str]
) -> None:
    email = ""
    selected_product: dict[str, Any] = {}

    def llm_decision(self, **kwargs: Any) -> dict[str, Any]:
        context = kwargs["messages"][1]["content"]
        assert selected_product["name"] in context
        assert f"{selected_product['min_term_months']} мес." in context
        payload = CreditAdvice(
            decision=outcome,
            conditions=conditions,
            recommended_product="Оборотный",
            explanation="Показатели требуют дополнительной проверки.",
            top_risk_factors=["Умеренная долговая нагрузка"],
            next_step="Дождитесь ручной проверки.",
        )
        return {"message": {"content": payload.model_dump_json()}}

    monkeypatch.setattr("ollama.Client.chat", llm_decision)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            email, headers = await _register_company_user(client)
            products = await client.get("/api/v1/credit-products")
            selected_product = products.json()[0]
            created = await _create_draft(client, headers, selected_product)
            response = await client.post(
                f"/api/v1/applications/{created.json()['id']}/submit",
                headers=headers,
            )
            history = await client.get(
                f"/api/v1/applications/{created.json()['id']}/history",
                headers=headers,
            )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == expected_status
        assert response.json()["decision"]["outcome"] == outcome
        assert response.json()["decision"]["source"] == "AI"
        assert response.json()["decision"]["conditions"] == conditions
        assert response.json()["decision"]["top_factors"] == ["Умеренная долговая нагрузка"]
        assert response.json()["decision"]["recommended_product"] == "Оборотный"
        assert response.json()["decision"]["next_step"] == "Дождитесь ручной проверки."
        assert history.status_code == 200
        assert history.json()[-1]["event_type"] == "APPLICATION_DECISION_RECORDED"
        assert history.json()[-1]["to_status"] == expected_status
        assert history.json()[-1]["details"]["outcome"] == outcome
    finally:
        if email:
            await _cleanup_user(email)
        await engine.dispose()


@pytest.mark.asyncio
async def test_need_more_data_can_be_corrected_and_resubmitted(monkeypatch) -> None:
    email = ""
    scoring_calls: list[dict[str, Any]] = []

    def scoring_fallback(**kwargs: Any) -> dict[str, Any]:
        scoring_calls.append(kwargs)
        advice = CreditAdvice(
            decision="APPROVED",
            conditions=[],
            recommended_product="Оборотный",
            explanation="Подходит для оборотного капитала.",
            top_risk_factors=["Низкая долговая нагрузка"],
            next_step="Ознакомьтесь с предложением.",
        )
        return {
            "decision": "APPROVED",
            "risk_score": 25.0,
            "risk_level": "Low",
            "top_factors": ["Низкая долговая нагрузка"],
            "ai_advice": {
                "source": "Fallback_Rules",
                "data": advice.model_dump(mode="json"),
            },
        }

    monkeypatch.setattr(
        application_workflow,
        "score_and_explain",
        scoring_fallback,
    )
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            email, headers = await _register_company_user(client)
            products = await client.get("/api/v1/credit-products")
            product = products.json()[0]
            created = await _create_draft(client, headers, product)
            application_id = created.json()["id"]
            company_id = created.json()["company_id"]

            initial_financials = await client.get(
                "/api/v1/company/financials", headers=headers
            )
            assert initial_financials.status_code == 200
            invalid_financials = await client.patch(
                "/api/v1/company/financials",
                headers=headers,
                json={"revenue_annual": 0},
            )
            assert invalid_financials.status_code == 200

            needs_data = await client.post(
                f"/api/v1/applications/{application_id}/submit",
                headers=headers,
            )
            repeated_needs_data = await client.post(
                f"/api/v1/applications/{application_id}/submit",
                headers=headers,
            )

        assert needs_data.status_code == 200, needs_data.text
        assert needs_data.json()["status"] == "NEED_MORE_DATA"
        assert needs_data.json()["decision"] is None
        assert needs_data.json()["required_fields"] == ["financials.revenue_annual"]
        assert repeated_needs_data.json() == needs_data.json()
        assert scoring_calls == []

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            repaired = await client.patch(
                "/api/v1/company/financials",
                headers=headers,
                json={"revenue_annual": 13_000_000},
            )
            assert repaired.status_code == 200
            resubmitted = await client.post(
                f"/api/v1/applications/{application_id}/submit",
                headers=headers,
            )
            history = await client.get(
                f"/api/v1/applications/{application_id}/history",
                headers=headers,
            )

        assert resubmitted.status_code == 200, resubmitted.text
        assert resubmitted.json()["status"] == "DECISION"
        assert resubmitted.json()["required_fields"] == []
        assert resubmitted.json()["decision"]["outcome"] == "APPROVED"
        assert len(scoring_calls) == 1
        assert history.status_code == 200
        assert "NEED_MORE_DATA" in [event["to_status"] for event in history.json()]
        assert history.json()[-1]["to_status"] == "DECISION"

        async with session_factory() as session:
            snapshots = list(
                await session.scalars(
                    select(ApplicationSnapshot)
                    .where(ApplicationSnapshot.application_id == application_id)
                    .order_by(ApplicationSnapshot.snapshot_version)
                )
            )
            saved_application = await session.get(Application, application_id)
            saved_financials = await session.get(Financials, company_id)

        assert [snapshot.snapshot_version for snapshot in snapshots] == [1, 2]
        assert all(snapshot.schema_version == 4 for snapshot in snapshots)
        assert snapshots[0].payload["required_fields"] == [
            "financials.revenue_annual"
        ]
        assert snapshots[0].payload["risk_assessment"] is None
        assert snapshots[1].payload["required_fields"] == []
        assert snapshots[1].payload["risk_assessment"]["ai_advice"]["source"] == (
            "Fallback_Rules"
        )
        assert saved_application is not None
        assert saved_application.status == "DECISION"
        assert saved_financials is not None
        assert saved_financials.revenue_annual == Decimal("13000000")
    finally:
        if email:
            await _cleanup_user(email)
        await engine.dispose()


@pytest.mark.asyncio
async def test_missing_official_registration_date_stays_draft(monkeypatch) -> None:
    email = ""
    scoring_calls: list[dict[str, Any]] = []

    def scoring(**kwargs: Any) -> dict[str, Any]:
        scoring_calls.append(kwargs)
        raise AssertionError("scoring must not run without official registration date")

    monkeypatch.setattr(application_workflow, "score_and_explain", scoring)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            email, headers = await _register_company_user(client)
            products = await client.get("/api/v1/credit-products")
            created = await _create_draft(client, headers, products.json()[0])
            application_id = created.json()["id"]
            company_id = created.json()["company_id"]

            async with session_factory() as session:
                company = await session.get(Company, company_id)
                assert company is not None
                company.registration_date = None
                await session.commit()

            response = await client.post(
                f"/api/v1/applications/{application_id}/submit",
                headers=headers,
            )
            detail = await client.get(
                f"/api/v1/applications/{application_id}", headers=headers
            )

        assert response.status_code == 409
        assert detail.status_code == 200
        assert detail.json()["status"] == "DRAFT"
        assert scoring_calls == []
        async with session_factory() as session:
            snapshot = await session.scalar(
                select(ApplicationSnapshot).where(
                    ApplicationSnapshot.application_id == application_id
                )
            )
            events = list(
                await session.scalars(
                    select(ApplicationEvent).where(
                        ApplicationEvent.application_id == application_id
                    )
                )
            )
        assert snapshot is None
        assert len(events) == 1
        assert events[0].event_type == "APPLICATION_DRAFT_CREATED"
    finally:
        if email:
            await _cleanup_user(email)
        await engine.dispose()
