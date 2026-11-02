"""Make English article fields optional for Telugu-only articles."""

from alembic import op
import sqlalchemy as sa


revision = "c2e8b3f941ad"
down_revision = "a7c91d4e62b0"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("articles") as batch_op:
        batch_op.alter_column(
            "title_en",
            existing_type=sa.String(length=220),
            existing_nullable=False,
            nullable=True,
        )
        batch_op.alter_column(
            "summary_en",
            existing_type=sa.String(length=500),
            existing_nullable=False,
            nullable=True,
        )
        batch_op.alter_column(
            "body_en",
            existing_type=sa.Text(),
            existing_nullable=False,
            nullable=True,
        )


def downgrade():
    op.execute("UPDATE articles SET title_en = '' WHERE title_en IS NULL")
    op.execute("UPDATE articles SET summary_en = '' WHERE summary_en IS NULL")
    op.execute("UPDATE articles SET body_en = '' WHERE body_en IS NULL")

    with op.batch_alter_table("articles") as batch_op:
        batch_op.alter_column(
            "title_en",
            existing_type=sa.String(length=220),
            existing_nullable=True,
            nullable=False,
        )
        batch_op.alter_column(
            "summary_en",
            existing_type=sa.String(length=500),
            existing_nullable=True,
            nullable=False,
        )
        batch_op.alter_column(
            "body_en",
            existing_type=sa.Text(),
            existing_nullable=True,
            nullable=False,
        )
