"""Store versioned demonstration tariff selection per application."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = "0016_smart_pricing"
down_revision = "0015_application_context"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("applications", sa.Column("purpose_category", sa.String(32), nullable=False, server_default="other"))
    op.add_column("applications", sa.Column("pricing", postgresql.JSONB(), nullable=True))

def downgrade():
    op.drop_column("applications", "pricing")
    op.drop_column("applications", "purpose_category")
