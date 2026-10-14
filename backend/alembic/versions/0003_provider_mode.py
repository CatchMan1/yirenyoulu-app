"""Persist result provenance independently from current configuration."""

from alembic import op
import sqlalchemy as sa

revision = "0003_provider_mode"
down_revision = "3d822eb29121"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("planning_jobs", "chat_messages"):
        op.add_column(
            table,
            sa.Column("provider_mode", sa.String(10), nullable=False, server_default="disabled"),
        )
        op.create_check_constraint(
            op.f("ck_" + table + "_provider_mode"),
            table,
            "provider_mode IN ('disabled','mock','real')",
        )


def downgrade():
    for table in ("chat_messages", "planning_jobs"):
        op.drop_constraint(op.f("ck_" + table + "_provider_mode"), table, type_="check")
        op.drop_column(table, "provider_mode")
