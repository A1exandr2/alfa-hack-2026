"""Store expanded company registry details."""
from alembic import op
import sqlalchemy as sa
revision = "0014_company_registry"
down_revision = "0013_application_reviews"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("companies", sa.Column("full_name", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("kpp", sa.String(9), nullable=True))
    op.add_column("companies", sa.Column("address", sa.Text(), nullable=True))

def downgrade():
    op.drop_column("companies", "address")
    op.drop_column("companies", "kpp")
    op.drop_column("companies", "full_name")
