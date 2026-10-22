"""Add the synthetic MVP credit-product catalog.

Revision ID: 0006_credit_products
Revises: 0005_credit_history
"""
from decimal import Decimal
from typing import Sequence, Union
from uuid import UUID

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0006_credit_products"
down_revision: Union[str, None] = "0005_credit_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "credit_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("min_amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("max_amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("min_term_months", sa.Integer(), nullable=False),
        sa.Column("max_term_months", sa.Integer(), nullable=False),
        sa.Column("interest_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("data_source", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "min_amount >= 0", name="ck_credit_products_min_amount_nonnegative"
        ),
        sa.CheckConstraint(
            "max_amount >= min_amount", name="ck_credit_products_amount_range"
        ),
        sa.CheckConstraint(
            "min_term_months > 0", name="ck_credit_products_min_term_positive"
        ),
        sa.CheckConstraint(
            "max_term_months >= min_term_months", name="ck_credit_products_term_range"
        ),
        sa.CheckConstraint(
            "interest_rate >= 0", name="ck_credit_products_rate_nonnegative"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    products = sa.table(
        "credit_products",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String(length=160)),
        sa.column("description", sa.Text()),
        sa.column("min_amount", sa.Numeric(precision=15, scale=2)),
        sa.column("max_amount", sa.Numeric(precision=15, scale=2)),
        sa.column("min_term_months", sa.Integer()),
        sa.column("max_term_months", sa.Integer()),
        sa.column("interest_rate", sa.Numeric(precision=5, scale=2)),
        sa.column("is_active", sa.Boolean()),
        sa.column("data_source", sa.String(length=32)),
    )
    op.bulk_insert(
        products,
        [
            {
                "id": UUID("00000000-0000-0000-0000-000000000101"),
                "name": "Оборотный кредит",
                "description": "Синтетический demo-продукт для пополнения оборотных средств.",
                "min_amount": Decimal("100000.00"),
                "max_amount": Decimal("5000000.00"),
                "min_term_months": 6,
                "max_term_months": 36,
                "interest_rate": Decimal("18.90"),
                "is_active": True,
                "data_source": "DEMO",
            },
            {
                "id": UUID("00000000-0000-0000-0000-000000000102"),
                "name": "Кредит на развитие бизнеса",
                "description": "Синтетический demo-продукт для инвестиций в развитие компании.",
                "min_amount": Decimal("500000.00"),
                "max_amount": Decimal("20000000.00"),
                "min_term_months": 12,
                "max_term_months": 60,
                "interest_rate": Decimal("16.50"),
                "is_active": True,
                "data_source": "DEMO",
            },
            {
                "id": UUID("00000000-0000-0000-0000-000000000103"),
                "name": "Экспресс-кредит",
                "description": "Синтетический demo-продукт для небольших краткосрочных расходов.",
                "min_amount": Decimal("50000.00"),
                "max_amount": Decimal("1000000.00"),
                "min_term_months": 3,
                "max_term_months": 12,
                "interest_rate": Decimal("21.50"),
                "is_active": True,
                "data_source": "DEMO",
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("credit_products")
