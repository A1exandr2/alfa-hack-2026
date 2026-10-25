from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.credit_products.schemas import CreditProductResponse
from app.database import get_db_session
from app.models import CreditProduct


router = APIRouter(prefix="/api/v1/credit-products", tags=["credit-products"])


@router.get("", response_model=list[CreditProductResponse])
async def list_credit_products(
    session: AsyncSession = Depends(get_db_session),
) -> list[CreditProductResponse]:
    products = await session.scalars(
        select(CreditProduct)
        .where(CreditProduct.is_active.is_(True))
        .order_by(CreditProduct.name)
    )
    return [CreditProductResponse.model_validate(product) for product in products]


@router.get("/{product_id}", response_model=CreditProductResponse)
async def get_credit_product(
    product_id: UUID,
    session: AsyncSession = Depends(get_db_session),
) -> CreditProductResponse:
    product = await session.scalar(
        select(CreditProduct).where(
            CreditProduct.id == product_id,
            CreditProduct.is_active.is_(True),
        )
    )
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credit product not found",
        )
    return CreditProductResponse.model_validate(product)
