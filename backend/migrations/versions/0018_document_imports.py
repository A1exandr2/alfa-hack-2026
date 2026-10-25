"""Store editable document extraction previews and confirmed import provenance."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0018_document_imports"
down_revision = "0017_financial_sources"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("document_imports",
        sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),
        sa.Column("user_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("company_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("companies.id"),nullable=False),
        sa.Column("filename",sa.String(255),nullable=False),
        sa.Column("sha256",sa.String(64),nullable=False),
        sa.Column("extracted",postgresql.JSONB(),nullable=False),
        sa.Column("accepted_values",postgresql.JSONB(),nullable=True),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column("confirmed_at",sa.DateTime(timezone=True),nullable=True))


def downgrade():
    op.drop_table("document_imports")
