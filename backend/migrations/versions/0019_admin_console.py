"""Admin role, account suspension and append-only administration audit."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0019_admin_console'
down_revision = '0018_document_imports'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('ck_users_role', 'users', type_='check')
    op.create_check_constraint('ck_users_role', 'users', "role IN ('USER', 'REVIEWER', 'ADMIN')")
    op.add_column('users', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table('admin_audit',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('actor_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('actor_email', sa.String(320), nullable=False),
        sa.Column('action', sa.String(64), nullable=False),
        sa.Column('target_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('details', postgresql.JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))

    op.create_index('ix_admin_audit_created_at', 'admin_audit', ['created_at'])

def downgrade():
    op.drop_table('admin_audit')
    op.drop_column('users', 'is_active')
    op.execute("UPDATE users SET role = 'REVIEWER' WHERE role = 'ADMIN'")
    op.drop_constraint('ck_users_role', 'users', type_='check')
    op.create_check_constraint('ck_users_role', 'users', "role IN ('USER', 'REVIEWER')")
