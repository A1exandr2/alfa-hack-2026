"""Persist reviewer outcomes separately from AI decisions.

Revision ID: 0013_application_reviews
Revises: 0012_reviewer_role
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0013_application_reviews"
down_revision: Union[str, None] = "0012_reviewer_role"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "application_reviews",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("decision_id", sa.UUID(), nullable=False),
        sa.Column("reviewer_user_id", sa.UUID(), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "outcome IN ('APPROVED', 'REJECTED')",
            name="ck_application_reviews_outcome",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"], ["applications.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["decision_id"], ["application_decisions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "application_id", name="uq_application_reviews_application_id"
        ),
        sa.UniqueConstraint("decision_id", name="uq_application_reviews_decision_id"),
    )


def downgrade() -> None:
    op.drop_table("application_reviews")
