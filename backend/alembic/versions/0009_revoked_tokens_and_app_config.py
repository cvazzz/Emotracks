"""revoked tokens and app config tables

Revision ID: 0009_revoked_tokens_and_app_config
Revises: 0008_alert_rule_version_and_dedup_index
Create Date: 2025-08-19
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0009_revoked_tokens_and_app_config'
down_revision = '0008_alert_rule_version_and_dedup_index'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'revokedtoken',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('jti_hash', sa.String(), nullable=False, unique=True, index=True),
        sa.Column('token_type', sa.String(), nullable=False, server_default='refresh'),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True, index=True),
    )
    op.create_table(
        'appconfig',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('key', sa.String(), nullable=False, unique=True, index=True),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )


def downgrade():
    op.drop_table('appconfig')
    op.drop_table('revokedtoken')
