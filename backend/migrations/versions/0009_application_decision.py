"""Persist structured application decisions linked to their snapshot.

Revision ID: 0009_application_decision
Revises: 0008_application_snapshot_audit
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0009_application_decision"
down_revision: Union[str, None] = "0008_application_snapshot_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "application_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("risk_score", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("top_factors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "outcome IN ('APPROVED', 'CONDITIONAL_APPROVAL', 'REJECTED')",
            name="ck_application_decisions_outcome",
        ),
        sa.CheckConstraint(
            "source IN ('AI', 'Fallback_Rules')",
            name="ck_application_decisions_source",
        ),
        sa.CheckConstraint(
            "risk_score >= 0 AND risk_score <= 100",
            name="ck_application_decisions_score_range",
        ),
        sa.CheckConstraint(
            "risk_level IN ('Low', 'Medium', 'High')",
            name="ck_application_decisions_risk_level",
        ),

        sa.ForeignKeyConstraint(
            ["application_id"], ["applications.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["application_snapshots.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "application_id", name="uq_application_decisions_application_id"
        ),
        sa.UniqueConstraint("snapshot_id", name="uq_application_decisions_snapshot_id"),
    )


def downgrade() -> None:
    op.drop_table("application_decisions")
