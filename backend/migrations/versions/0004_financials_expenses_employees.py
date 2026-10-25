"""Add expenses and employee count to financial data.

Revision ID: 0004_fin_metrics
Revises: 0003_company_data_source
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_fin_metrics"
down_revision: Union[str, None] = "0003_company_data_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "financials",
        sa.Column(
            "expenses_annual",
            sa.Numeric(precision=15, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "financials",
        sa.Column("employees", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.create_check_constraint(
        "ck_financials_expenses_nonnegative",
        "financials",
        "expenses_annual >= 0",
    )
    op.create_check_constraint(
        "ck_financials_employees_nonnegative",
        "financials",
        "employees >= 0",
    )
    op.alter_column("financials", "expenses_annual", server_default=None)
    op.alter_column("financials", "employees", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "ck_financials_employees_nonnegative", "financials", type_="check"
    )
    op.drop_constraint(
        "ck_financials_expenses_nonnegative", "financials", type_="check"
    )
    op.drop_column("financials", "employees")
    op.drop_column("financials", "expenses_annual")
