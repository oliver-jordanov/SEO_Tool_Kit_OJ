"""Backlink Explorer v1 normalized data tables."""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

def upgrade():
    inspector = sa.inspect(op.get_bind())
    tables = inspector.get_table_names()
    if "backlink_summaries" not in tables:
        op.create_table("backlink_summaries", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("run_id", sa.Integer(), sa.ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("data_json", sa.Text(), nullable=False))
        op.create_index("ix_backlink_summaries_run_id", "backlink_summaries", ["run_id"], unique=True)
    if "backlink_referring_domains" not in tables:
        op.create_table("backlink_referring_domains", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("run_id", sa.Integer(), sa.ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("position", sa.Integer(), nullable=False), sa.Column("data_json", sa.Text(), nullable=False))
        op.create_index("ix_backlink_referring_domains_run_id", "backlink_referring_domains", ["run_id"])
    if "backlink_items" not in tables:
        op.create_table("backlink_items", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("run_id", sa.Integer(), sa.ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("position", sa.Integer(), nullable=False), sa.Column("data_json", sa.Text(), nullable=False))
        op.create_index("ix_backlink_items_run_id", "backlink_items", ["run_id"])

def downgrade():
    op.drop_table("backlink_items"); op.drop_table("backlink_referring_domains"); op.drop_table("backlink_summaries")
