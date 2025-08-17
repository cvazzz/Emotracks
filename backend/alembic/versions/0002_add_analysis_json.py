from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002_add_analysis_json"
down_revision = "0001_init_responses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("response", sa.Column("analysis_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("response", "analysis_json")
