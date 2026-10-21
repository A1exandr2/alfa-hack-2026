"""Add normalized company credit-history summaries.

Revision ID: 0005_credit_history
Revises: 0004_fin_metrics
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0005_credit_history"
down_revision: Union[str, None] = "0004_fin_metrics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "credit_history",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("active_credits", sa.Integer(), nullable=False),
        sa.Column("closed_credits", sa.Integer(), nullable=False),
        sa.Column("overdue_count", sa.Integer(), nullable=False),
        sa.Column("overdue_amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "active_credits >= 0", name="ck_credit_history_active_nonnegative"
        ),
        sa.CheckConstraint(
            "closed_credits >= 0", name="ck_credit_history_closed_nonnegative"
        ),
        sa.CheckConstraint(
            "overdue_count >= 0", name="ck_credit_history_overdue_nonnegative"
        ),
        sa.CheckConstraint(
            "overdue_amount >= 0", name="ck_credit_history_amount_nonnegative"
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("company_id"),
    )


def downgrade() -> None:
    op.drop_table("credit_history")
