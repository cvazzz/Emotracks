"""add alert table

Revision ID: 0006_add_alert_table
Revises: 0005_child_unique_parent_name
Create Date: 2025-08-17
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_add_alert_table"
down_revision = "0005_child_unique_parent_name"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "alert",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("child_id", sa.Integer, sa.ForeignKey("child.id"), nullable=False),
        sa.Column("type", sa.String(length=100), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="info"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_alert_child_id", "alert", ["child_id"])


def downgrade() -> None:
    op.drop_index("ix_alert_child_id", table_name="alert")
    op.drop_table("alert")
