"""Version application snapshots across NEED_MORE_DATA retries.

Revision ID: 0011_application_snapshot_attempts
Revises: 0010_decision_advice
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011_snapshot_attempts"
down_revision: Union[str, None] = "0010_decision_advice"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "application_snapshots",
        sa.Column(
            "snapshot_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
    )
    op.drop_constraint(
        "application_snapshots_application_id_key",
        "application_snapshots",
        type_="unique",
    )
    op.create_check_constraint(
        "ck_application_snapshot_attempt_positive",
        "application_snapshots",
        "snapshot_version > 0",
    )
    op.create_unique_constraint(
        "uq_application_snapshots_version",
        "application_snapshots",
        ["application_id", "snapshot_version"],
    )
    op.alter_column("application_snapshots", "snapshot_version", server_default=None)


def downgrade() -> None:
    # A downgrade keeps only the decision snapshot (or latest attempt if no decision).
    op.execute(
        sa.text(
            """
            DELETE FROM application_snapshots AS snapshot
            WHERE snapshot.id <> COALESCE(
                (
                    SELECT decision.snapshot_id
                    FROM application_decisions AS decision
                    WHERE decision.application_id = snapshot.application_id
                ),
                (
                    SELECT latest.id
                    FROM application_snapshots AS latest
                    WHERE latest.application_id = snapshot.application_id
                    ORDER BY latest.snapshot_version DESC
                    LIMIT 1
                )
            )
            """
        )
    )
    op.drop_constraint(
        "uq_application_snapshots_version",
        "application_snapshots",
        type_="unique",
    )
    op.drop_constraint(
        "ck_application_snapshot_attempt_positive",
        "application_snapshots",
        type_="check",
    )
    op.create_unique_constraint(
        "application_snapshots_application_id_key",
        "application_snapshots",
        ["application_id"],
    )
    op.drop_column("application_snapshots", "snapshot_version")
