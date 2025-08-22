"""
Add encrypted columns for response: analysis_json_enc, transcript_enc

Revision ID: 0011_add_encrypted_columns
Revises: 0010_response_audio_fields
Create Date: 2025-08-22
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0011_add_encrypted_columns"
down_revision = "0010_response_audio_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("response") as batch_op:
        batch_op.add_column(sa.Column("analysis_json_enc", sa.LargeBinary(), nullable=True))
        batch_op.add_column(sa.Column("transcript_enc", sa.LargeBinary(), nullable=True))
    try:
        op.create_index("ix_response_task_id", "response", ["task_id"], unique=False)
    except Exception:
        pass


def downgrade() -> None:
    with op.batch_alter_table("response") as batch_op:
        try:
            batch_op.drop_column("transcript_enc")
        except Exception:
            pass
        try:
            batch_op.drop_column("analysis_json_enc")
        except Exception:
            pass
    try:
        op.drop_index("ix_response_task_id", table_name="response")
    except Exception:
        pass
