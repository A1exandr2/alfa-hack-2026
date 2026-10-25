"""Allow unknown financial fields and preserve per-field provenance."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="0017_financial_sources"
down_revision="0016_smart_pricing"
branch_labels=None
depends_on=None

def upgrade():
    for name in ("revenue_annual","profit_annual","expenses_annual","employees","current_debt"):
        op.alter_column("financials", name, nullable=True)
    for name in ("active_credits","closed_credits","overdue_count","overdue_amount"):
        op.alter_column("credit_history", name, nullable=True)
    op.add_column("financials",sa.Column("report_year",sa.Integer(),nullable=True))
    op.add_column("financials",sa.Column("field_sources",postgresql.JSONB(),nullable=False,server_default="{}"))
    op.add_column("credit_history",sa.Column("report_year",sa.Integer(),nullable=True))
    op.add_column("credit_history",sa.Column("field_sources",postgresql.JSONB(),nullable=False,server_default="{}"))
    op.add_column("credit_history",sa.Column("as_of",sa.DateTime(timezone=True),nullable=True))
    op.create_table("credit_history_consents",
        sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),
        sa.Column("user_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("users.id"),nullable=False),
        sa.Column("company_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("companies.id"),nullable=False),
        sa.Column("granted_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("revoked_at",sa.DateTime(timezone=True),nullable=True),
        sa.Column("text_version",sa.String(32),nullable=False))
    # Remove only synthetic current data. Historical application snapshots are immutable.
    op.execute("UPDATE financials f SET revenue_annual=NULL, profit_annual=NULL, expenses_annual=NULL, employees=NULL, current_debt=NULL, source='UNAVAILABLE' FROM companies c WHERE f.company_id=c.id AND f.source='DEMO'")
    op.execute("UPDATE credit_history h SET active_credits=NULL, closed_credits=NULL, overdue_count=NULL, overdue_amount=NULL, source='UNAVAILABLE' FROM companies c WHERE h.company_id=c.id AND h.source='DEMO'")

def downgrade():
    # Refuse a lossy rollback instead of fabricating zeroes for unknown data.
    connection = op.get_bind()
    for table, fields in [("financials", ("revenue_annual","profit_annual","expenses_annual","employees","current_debt")), ("credit_history", ("active_credits","closed_credits","overdue_count","overdue_amount"))]:
        condition = " OR ".join(f"{field} IS NULL" for field in fields)
        if connection.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table} WHERE {condition})")).scalar():
            raise RuntimeError("Cannot downgrade while unknown financial values exist; restore a backup instead")
        for field in fields:
            op.alter_column(table,field,nullable=False)
    op.drop_table("credit_history_consents")
    op.drop_column("credit_history","as_of")
    for table in ("financials", "credit_history"):
        op.drop_column(table,"field_sources")
        op.drop_column(table,"report_year")
