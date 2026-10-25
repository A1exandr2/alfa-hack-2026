"""Create initial credit domain schema.

Revision ID: 0001_initial_schema
Revises:
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("inn", sa.String(length=12), nullable=False),
        sa.Column("ogrn", sa.String(length=15), nullable=True),
        sa.Column("registration_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("director_name", sa.String(length=255), nullable=True),
        sa.Column("okved", sa.String(length=16), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("inn"),
        sa.UniqueConstraint("ogrn"),
    )
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "financials",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revenue_annual", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("profit_annual", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("current_debt", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.CheckConstraint("revenue_annual >= 0", name="ck_financials_revenue_nonnegative"),
        sa.CheckConstraint("current_debt >= 0", name="ck_financials_debt_nonnegative"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("company_id"),
    )


def downgrade() -> None:
    op.drop_table("financials")
    op.drop_table("users")
    op.drop_table("companies")
