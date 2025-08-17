"""add unique constraint child(parent_id,name)

Revision ID: 0005_child_unique_parent_name
Revises: 0004_add_child_and_response_child_id
Create Date: 2025-08-17
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0005_child_unique_parent_name"
down_revision: Union[str, None] = "0004_add_child_and_response_child_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint("uq_child_parent_name", "child", ["parent_id", "name"])


def downgrade() -> None:
    op.drop_constraint("uq_child_parent_name", "child", type_="unique")
