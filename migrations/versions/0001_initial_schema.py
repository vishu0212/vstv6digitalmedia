"""Initial schema. Revision ID: 0001_initial"""
from alembic import op
import sqlalchemy as sa
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None
def upgrade():
    op.create_table("users", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("email", sa.String(254), nullable=False), sa.Column("display_name", sa.String(120), nullable=False), sa.Column("password_hash", sa.String(255), nullable=False), sa.Column("role", sa.String(20), nullable=False, server_default="editor"), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("email"))
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table("categories", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name_en", sa.String(80), nullable=False), sa.Column("name_te", sa.String(80), nullable=False), sa.Column("slug", sa.String(100), nullable=False), sa.UniqueConstraint("name_en"), sa.UniqueConstraint("slug"))
    op.create_table("articles", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("title_en", sa.String(220), nullable=False), sa.Column("title_te", sa.String(220)), sa.Column("slug", sa.String(240), nullable=False), sa.Column("summary_en", sa.String(500), nullable=False), sa.Column("summary_te", sa.String(500)), sa.Column("body_en", sa.Text(), nullable=False), sa.Column("body_te", sa.Text()), sa.Column("language", sa.String(8), nullable=False, server_default="both"), sa.Column("category_id", sa.Integer(), nullable=False), sa.Column("author_id", sa.Integer(), nullable=False), sa.Column("source_name", sa.String(200)), sa.Column("source_url", sa.String(1000)), sa.Column("image_url", sa.String(1000)), sa.Column("status", sa.String(20), nullable=False, server_default="draft"), sa.Column("published_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.ForeignKeyConstraint(["author_id"], ["users.id"]), sa.ForeignKeyConstraint(["category_id"], ["categories.id"]), sa.UniqueConstraint("slug"))
    op.create_index("ix_articles_slug", "articles", ["slug"], unique=True)
    op.create_index("ix_articles_status", "articles", ["status"])
    op.create_index("ix_articles_published_at", "articles", ["published_at"])
def downgrade():
    op.drop_index("ix_articles_published_at", table_name="articles")
    op.drop_index("ix_articles_status", table_name="articles")
    op.drop_index("ix_articles_slug", table_name="articles")
    op.drop_table("articles")
    op.drop_table("categories")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
