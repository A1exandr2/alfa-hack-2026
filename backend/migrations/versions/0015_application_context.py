"""Persist customer-provided application context."""
from alembic import op
import sqlalchemy as sa
revision = "0015_application_context"
down_revision = "0014_company_registry"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("applications", sa.Column("additional_info", sa.String(1000), nullable=False, server_default=""))

def downgrade():
    op.drop_column("applications", "additional_info")
