"""response extra indexes & ensure tz columns

Revision ID: 0007_response_indexes_and_tz
Revises: 0006_add_alert_table
Create Date: 2025-08-17
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0007_response_indexes_and_tz"
down_revision: Union[str, None] = "0006_add_alert_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add indexes (if they already exist this may fail in some DBs; acceptable for first application)
    with op.batch_alter_table("response") as batch:
        batch.create_index("ix_response_emotion", ["emotion"], unique=False)
        batch.create_index("ix_response_created_at", ["created_at"], unique=False)
        batch.create_index("ix_response_child_created", ["child_id", "created_at"], unique=False)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        try:
            op.execute(
                "ALTER TABLE response ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE"
            )
        except Exception:
            pass


def downgrade() -> None:
    with op.batch_alter_table("response") as batch:
        batch.drop_index("ix_response_child_created")
        batch.drop_index("ix_response_created_at")
        batch.drop_index("ix_response_emotion")
