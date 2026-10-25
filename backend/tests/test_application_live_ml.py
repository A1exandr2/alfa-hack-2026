import os
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from app.database import engine, session_factory
from app.main import app
from app.models import (
    ApplicationSnapshot,
    Company,
    CreditHistory,
    Financials,
    User,
)


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_QWEN_APPLICATION") != "1",
    reason="set RUN_LIVE_QWEN_APPLICATION=1 to call the live Ollama model",
)
async def test_live_application_submit_uses_qwen() -> None:
    email = f"live-qwen-{uuid4().hex}@example.com"
    company_id = None
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            timeout=180.0,
        ) as client:
            register = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": email,
                    "password": f"{uuid4().hex}!Aa1",
                    "full_name": "Live Qwen Smoke",
                },
            )
            assert register.status_code == 201, register.text
            headers = {
                "Authorization": f"Bearer {register.json()['access_token']}"
            }
            company = await client.post(
                "/api/v1/company/link",
                headers=headers,
                json={"inn": str(uuid4().int)[:10]},
            )
            assert company.status_code == 200, company.text
            company_id = company.json()["id"]

            products_response = await client.get("/api/v1/credit-products")
            assert products_response.status_code == 200
            product = products_response.json()[0]
            created = await client.post(
                "/api/v1/applications",
                headers=headers,
                json={
                    "product_id": product["id"],
                    "requested_amount": str(product["min_amount"]),
                    "term_months": product["min_term_months"],
                    "purpose": "Пополнение оборотных средств для закупки оборудования",
                },
            )
            assert created.status_code == 201, created.text
            application_id = created.json()["id"]

            response = await client.post(
                f"/api/v1/applications/{application_id}/submit",
                headers=headers,
            )
            decision_response = await client.get(
                f"/api/v1/applications/{application_id}/decision",
                headers=headers,
            )

        assert response.status_code == 200, response.text
        body = response.json()
        decision = body["decision"]
        assert decision["source"] == "AI", decision
        assert decision["outcome"] in {
            "APPROVED",
            "CONDITIONAL_APPROVAL",
            "REJECTED",
        }
        assert 0 <= decision["risk_score"] <= 100
        assert decision["risk_level"] in {"Low", "Medium", "High"}
        assert decision["explanation"].strip()
        assert decision["top_factors"]
        assert decision["next_step"].strip()
        assert decision["recommended_product"] in {
            "Оборотный",
            "Инвестиционный",
            "Рефинансирование",
        }
        if decision["outcome"] == "CONDITIONAL_APPROVAL":
            assert body["status"] == "MANUAL_REVIEW"
            assert decision["conditions"]
        elif decision["outcome"] == "APPROVED":
            assert body["status"] == "DECISION"
            assert decision["conditions"] == []
        else:
            assert body["status"] == "REJECTED"
            assert decision["conditions"] == []

        assert decision_response.status_code == 200, decision_response.text
        assert decision_response.json()["source"] == "AI"
        assert decision_response.json()["outcome"] == decision["outcome"]
        async with session_factory() as session:
            snapshot = await session.scalar(
                select(ApplicationSnapshot).where(
                    ApplicationSnapshot.application_id == application_id
                )
            )
        assert snapshot is not None
        assert snapshot.schema_version == 4
        assert snapshot.payload["application"]["term_months"] == body["term_months"]
        assert snapshot.payload["credit_product"]["id"] == product["id"]
        assert snapshot.payload["risk_assessment"]["ai_advice"]["source"] == "AI"
    finally:
        async with session_factory() as session:
            user = await session.scalar(select(User).where(User.email == email))
            if user is not None:
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
                    saved_company = await session.get(Company, company_id)
                    if saved_company is not None:
                        await session.delete(saved_company)
                await session.commit()
        await engine.dispose()
