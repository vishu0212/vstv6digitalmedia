"""Add RSS collection run history."""

from alembic import op
import sqlalchemy as sa

revision = "a7c91d4e62b0"
down_revision = "ff45264864bb"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rss_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("feeds_checked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicates", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_rss_runs_started_at", "rss_runs", ["started_at"])
    op.create_index("ix_rss_runs_status", "rss_runs", ["status"])


def downgrade():
    op.drop_index("ix_rss_runs_status", table_name="rss_runs")
    op.drop_index("ix_rss_runs_started_at", table_name="rss_runs")
    op.drop_table("rss_runs")
