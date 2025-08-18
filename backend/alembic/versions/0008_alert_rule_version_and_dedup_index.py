"""add rule_version to alert and dedup index

Revision ID: 0008_alert_rule_version_and_dedup_index
Revises: 0007_response_indexes_and_tz
Create Date: 2025-08-17
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0008_alert_rule_version_and_dedup_index"
down_revision: Union[str, None] = "0007_response_indexes_and_tz"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("alert") as batch:
        batch.add_column(sa.Column("rule_version", sa.String(length=50), nullable=True))
        batch.create_index(
            "ix_alert_child_type_rule_version",
            ["child_id", "type", "rule_version"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("alert") as batch:
        batch.drop_index("ix_alert_child_type_rule_version")
        batch.drop_column("rule_version")
