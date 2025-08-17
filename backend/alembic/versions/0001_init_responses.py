import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_init_responses"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "response",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("child_name", sa.String(length=255), nullable=False),
        sa.Column("emotion", sa.String(length=255), nullable=False, server_default="Unknown"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="QUEUED"),
    )


def downgrade() -> None:
    op.drop_table("response")
