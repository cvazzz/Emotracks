"""response audio fields

Revision ID: 0010_response_audio_fields
Revises: 0009_revoked_tokens_and_app_config
Create Date: 2025-08-19
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0010_response_audio_fields'
down_revision = '0009_revoked_tokens_and_app_config'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('response') as batch:
        batch.add_column(sa.Column('audio_path', sa.String(), nullable=True))
        batch.add_column(sa.Column('audio_format', sa.String(), nullable=True))
        batch.add_column(sa.Column('audio_duration_sec', sa.Float(), nullable=True))
        batch.add_column(sa.Column('transcript', sa.Text(), nullable=True))
        batch.create_index('ix_response_audio_path', ['audio_path'])


def downgrade() -> None:
    with op.batch_alter_table('response') as batch:
        batch.drop_index('ix_response_audio_path')
        batch.drop_column('transcript')
        batch.drop_column('audio_duration_sec')
        batch.drop_column('audio_format')
        batch.drop_column('audio_path')
