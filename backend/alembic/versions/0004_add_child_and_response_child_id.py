"""add child table and response.child_id

Revision ID: 0004_add_child_and_response_child_id
Revises: 0003_add_users_table
Create Date: 2025-08-17
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0004_add_child_and_response_child_id"
down_revision: Union[str, None] = "0003_add_users_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "child",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("age", sa.Integer, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("parent_id", sa.Integer, sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_child_parent_id", "child", ["parent_id"], unique=False)
    with op.batch_alter_table("response") as batch:
        batch.add_column(sa.Column("child_id", sa.Integer, sa.ForeignKey("child.id"), nullable=True))
        batch.create_index("ix_response_child_id", ["child_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("response") as batch:
        batch.drop_index("ix_response_child_id")
        batch.drop_column("child_id")
    op.drop_index("ix_child_parent_id", table_name="child")
    op.drop_table("child")
