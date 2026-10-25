import pytest
from httpx import ASGITransport, AsyncClient

from app.database import engine
from app.main import app


@pytest.mark.asyncio
async def test_list_credit_products_returns_demo_catalog() -> None:
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/credit-products")

        assert response.status_code == 200
        products = response.json()
        assert len(products) == 3
        assert {product["name"] for product in products} == {
            "Оборотный кредит",
            "Кредит на развитие бизнеса",
            "Экспресс-кредит",
        }
        assert all(product["data_source"] == "DEMO" for product in products)
        for product in products:
            assert product["min_amount"] <= product["max_amount"]
            assert product["min_term_months"] <= product["max_term_months"]
            assert product["interest_rate"] > 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_credit_product_returns_details_or_404() -> None:
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            listing = await client.get("/api/v1/credit-products")
            assert listing.status_code == 200
            product = listing.json()[0]

            detail = await client.get(f"/api/v1/credit-products/{product['id']}")
            missing = await client.get(
                "/api/v1/credit-products/ffffffff-ffff-ffff-ffff-ffffffffffff"
            )

        assert detail.status_code == 200
        assert detail.json() == product
        assert missing.status_code == 404
    finally:
        await engine.dispose()
