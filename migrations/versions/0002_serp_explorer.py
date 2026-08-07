"""SERP Explorer v1 normalized result tables."""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

def upgrade():
    # 0001 in the original foundation package used Base.metadata.create_all().
    # On a fresh install it therefore sees current models and may already create
    # these tables; an existing 0001 database does not have them yet.
    inspector = sa.inspect(op.get_bind())
    if "serp_organic_results" in inspector.get_table_names():
        return
    op.create_table("serp_organic_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organic_position", sa.Integer(), nullable=False),
        sa.Column("serp_position", sa.Integer(), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("url", sa.Text(), nullable=False), sa.Column("title", sa.Text(), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=False), sa.Column("breadcrumb", sa.Text(), nullable=False),
        sa.Column("is_own_domain", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_serp_organic_results_run_id", "serp_organic_results", ["run_id"])
    op.create_table("serp_features",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("feature", sa.String(80), nullable=False),
    )
    op.create_index("ix_serp_features_run_id", "serp_features", ["run_id"])

def downgrade():
    op.drop_table("serp_features")
    op.drop_table("serp_organic_results")
