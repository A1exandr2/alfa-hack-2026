"""Add customer-facing advice fields to application decisions.

Revision ID: 0010_decision_advice
Revises: 0009_application_decision
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010_decision_advice"
down_revision: Union[str, None] = "0009_application_decision"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "application_decisions",
        sa.Column("recommended_product", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "application_decisions",
        sa.Column("next_step", sa.Text(), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE application_decisions AS decision
            SET recommended_product = snapshot.payload
                    -> 'risk_assessment' -> 'ai_advice' -> 'data'
                    ->> 'recommended_product',
                next_step = snapshot.payload
                    -> 'risk_assessment' -> 'ai_advice' -> 'data'
                    ->> 'next_step'
            FROM application_snapshots AS snapshot
            WHERE snapshot.id = decision.snapshot_id
            """
        )
    )
    op.alter_column(
        "application_decisions", "recommended_product", nullable=False
    )
    op.alter_column("application_decisions", "next_step", nullable=False)
    op.create_check_constraint(
        "ck_application_decisions_recommended_product",
        "application_decisions",
        "recommended_product IN ('Оборотный', 'Инвестиционный', 'Рефинансирование')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_application_decisions_recommended_product",
        "application_decisions",
        type_="check",
    )
    op.drop_column("application_decisions", "next_step")
    op.drop_column("application_decisions", "recommended_product")
