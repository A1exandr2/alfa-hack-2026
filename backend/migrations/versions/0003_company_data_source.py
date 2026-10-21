"""Record the company data provider.

Revision ID: 0003_company_data_source
Revises: 0002_user_company_optional
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_company_data_source"
down_revision: Union[str, None] = "0002_user_company_optional"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column(
            "data_source",
            sa.String(length=32),
            server_default="DEMO",
            nullable=False,
        ),
    )
    op.alter_column("companies", "data_source", server_default=None)


def downgrade() -> None:
    op.drop_column("companies", "data_source")
