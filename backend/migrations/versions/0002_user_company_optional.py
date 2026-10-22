"""Allow user registration before linking a company.

Revision ID: 0002_user_company_optional
Revises: 0001_initial_schema
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0002_user_company_optional"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "company_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "company_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
