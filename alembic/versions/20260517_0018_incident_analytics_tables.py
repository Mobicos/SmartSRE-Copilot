"""Add incidents, incident_links, and analytics_findings tables.

Revision ID: 20260518_0018
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa

revision = "20260518_0018"
down_revision = "20260517_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("incident_id", sa.Text(), primary_key=True),
        sa.Column("workspace_id", sa.Text(), sa.ForeignKey("workspaces.workspace_id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False, server_default="P2"),
        sa.Column("service_name", sa.Text(), nullable=True),
        sa.Column("owner", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("source", sa.Text(), nullable=False, server_default="manual"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("idx_incidents_workspace", "incidents", ["workspace_id"])
    op.create_index("idx_incidents_status", "incidents", ["status"])
    op.create_index("idx_incidents_severity", "incidents", ["severity"])

    op.create_table(
        "incident_links",
        sa.Column("link_id", sa.Text(), primary_key=True),
        sa.Column("incident_id", sa.Text(), sa.ForeignKey("incidents.incident_id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Text(), nullable=False),
        sa.Column("relationship", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_incident_links_incident", "incident_links", ["incident_id"])
    op.create_index("idx_incident_links_target", "incident_links", ["target_type", "target_id"])

    op.create_table(
        "analytics_findings",
        sa.Column("finding_id", sa.Text(), primary_key=True),
        sa.Column("workspace_id", sa.Text(), sa.ForeignKey("workspaces.workspace_id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_analytics_findings_workspace", "analytics_findings", ["workspace_id"])
    op.create_index("idx_analytics_findings_category", "analytics_findings", ["category"])


def downgrade() -> None:
    op.drop_table("analytics_findings")
    op.drop_table("incident_links")
    op.drop_table("incidents")
