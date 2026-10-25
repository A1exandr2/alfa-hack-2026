"""Add reviewer roles to users.

Revision ID: 0012_reviewer_role
Revises: 0011_snapshot_attempts
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012_reviewer_role"
down_revision: Union[str, None] = "0011_snapshot_attempts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(length=16),
            server_default=sa.text("'USER'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('USER', 'REVIEWER')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.drop_column("users", "role")
