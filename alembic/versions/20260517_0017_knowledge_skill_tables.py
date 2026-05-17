"""Add knowledge_items, skill_manifests, and knowledge_audit_log tables."""

from __future__ import annotations

from alembic import op

revision = "20260517_0017"
down_revision = "20260517_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_items (
            id SERIAL PRIMARY KEY,
            knowledge_base_id VARCHAR NOT NULL
                REFERENCES knowledge_bases(knowledge_base_id) ON DELETE CASCADE,
            item_type VARCHAR(50) NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            embedding vector(1024),
            confidence DOUBLE PRECISION DEFAULT 0.5,
            source_run_id VARCHAR REFERENCES agent_runs(run_id) ON DELETE SET NULL,
            status VARCHAR(20) DEFAULT 'draft',
            dedup_hash VARCHAR(64),
            metadata JSONB,
            created_by VARCHAR,
            published_by VARCHAR,
            published_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ki_kb_type ON knowledge_items(knowledge_base_id, item_type)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_ki_status ON knowledge_items(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ki_dedup ON knowledge_items(dedup_hash)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS skill_manifests (
            id SERIAL PRIMARY KEY,
            skill_id VARCHAR NOT NULL UNIQUE,
            name VARCHAR(200) NOT NULL,
            description TEXT,
            trigger_conditions JSONB NOT NULL,
            diagnostic_steps JSONB NOT NULL,
            recommended_tools JSONB NOT NULL,
            evidence_requirements JSONB NOT NULL,
            risk_warnings JSONB NOT NULL,
            report_template TEXT,
            input_schema JSONB,
            output_schema JSONB,
            degradation_strategy JSONB,
            version VARCHAR(20) DEFAULT '1.0.0',
            status VARCHAR(20) DEFAULT 'active',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_audit_log (
            id SERIAL PRIMARY KEY,
            item_id INTEGER NOT NULL REFERENCES knowledge_items(id) ON DELETE CASCADE,
            action VARCHAR(50) NOT NULL,
            actor VARCHAR,
            details JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_kal_item ON knowledge_audit_log(item_id, created_at)"
    )

    op.execute(
        "ALTER TABLE agent_memory ADD COLUMN IF NOT EXISTS embedding vector(1024)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE agent_memory DROP COLUMN IF EXISTS embedding")
    op.execute("DROP INDEX IF EXISTS idx_kal_item")
    op.execute("DROP TABLE IF EXISTS knowledge_audit_log")
    op.execute("DROP TABLE IF EXISTS skill_manifests")
    op.execute("DROP INDEX IF EXISTS idx_ki_dedup")
    op.execute("DROP INDEX IF EXISTS idx_ki_status")
    op.execute("DROP INDEX IF EXISTS idx_ki_kb_type")
    op.execute("DROP TABLE IF EXISTS knowledge_items")
