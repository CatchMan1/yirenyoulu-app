"""resumable city collection
Revision: 0006_city_collection
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_city_collection"
down_revision = "0005_data_import"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "collection_runs",
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("run_key", sa.String(length=100), nullable=False),
        sa.Column("config_hash", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("progress", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("lease_token", sa.String(length=36), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=100), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','staged','completed','failed','paused')",
            name=op.f("ck_collection_runs_valid_status"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["data_sources.id"],
            name=op.f("fk_collection_runs_source_id_data_sources"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collection_runs")),
        sa.UniqueConstraint("source_id", "run_key", name=op.f("uq_collection_runs_source_id")),
    )
    op.create_index(
        op.f("ix_collection_runs_source_id"), "collection_runs", ["source_id"], unique=False
    )
    op.create_table(
        "collection_pages",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("city_qid", sa.String(length=20), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("cursor", sa.String(length=20), nullable=False),
        sa.Column("next_cursor", sa.String(length=20), nullable=True),
        sa.Column("ids", sa.JSON(), nullable=False),
        sa.Column("records", sa.JSON(), nullable=True),
        sa.Column("rejected", sa.JSON(), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=True),
        sa.Column("done", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('attraction','hotel','restaurant')",
            name=op.f("ck_collection_pages_valid_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["import_batches.id"],
            name=op.f("fk_collection_pages_batch_id_import_batches"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["collection_runs.id"],
            name=op.f("fk_collection_pages_run_id_collection_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collection_pages")),
        sa.UniqueConstraint("batch_id", name=op.f("uq_collection_pages_batch_id")),
        sa.UniqueConstraint(
            "run_id", "city_qid", "kind", "cursor", name="uq_collection_pages_position"
        ),
    )
    op.create_index(
        op.f("ix_collection_pages_run_id"), "collection_pages", ["run_id"], unique=False
    )
    op.add_column("import_rows", sa.Column("result_action", sa.String(length=20), nullable=True))


def downgrade():
    op.drop_column("import_rows", "result_action")
    op.drop_index(op.f("ix_collection_pages_run_id"), table_name="collection_pages")
    op.drop_table("collection_pages")
    op.drop_index(op.f("ix_collection_runs_source_id"), table_name="collection_runs")
    op.drop_table("collection_runs")
