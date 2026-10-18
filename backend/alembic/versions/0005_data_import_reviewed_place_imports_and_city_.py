"""reviewed place imports and city recommendation scope
Revision: 0005_data_import
"""

import unicodedata
from hashlib import sha256

import sqlalchemy as sa
from alembic import op

revision = "0005_data_import"
down_revision = "a5552c8a1d17"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "city_aliases",
        sa.Column("city_id", sa.String(length=36), nullable=False),
        sa.Column("namespace", sa.String(length=100), nullable=False),
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("parent_code", sa.String(length=100), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["city_id"], ["cities.id"], name=op.f("fk_city_aliases_city_id_cities")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_city_aliases")),
        sa.UniqueConstraint("namespace", "external_id", name=op.f("uq_city_aliases_namespace")),
    )
    op.create_index(op.f("ix_city_aliases_city_id"), "city_aliases", ["city_id"], unique=False)
    op.create_table(
        "import_batches",
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("city_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("cursor", sa.Integer(), nullable=False),
        sa.Column("review_reference", sa.Text(), nullable=True),
        sa.Column("last_error", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
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
            "kind IN ('attraction','hotel','restaurant')", name=op.f("ck_import_batches_valid_kind")
        ),
        sa.CheckConstraint(
            "status IN ('staged','approved','completed','failed')",
            name=op.f("ck_import_batches_valid_status"),
        ),
        sa.CheckConstraint(
            "total >= 0 AND cursor >= 0 AND cursor <= total",
            name=op.f("ck_import_batches_bounded_cursor"),
        ),
        sa.ForeignKeyConstraint(
            ["city_id"], ["cities.id"], name=op.f("fk_import_batches_city_id_cities")
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["data_sources.id"],
            name=op.f("fk_import_batches_source_id_data_sources"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_batches")),
        sa.UniqueConstraint("source_id", "key", name=op.f("uq_import_batches_source_id")),
    )
    op.create_index(
        op.f("ix_import_batches_source_id"), "import_batches", ["source_id"], unique=False
    )
    op.create_table(
        "import_permits",
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("city_ids", sa.JSON(), nullable=False),
        sa.Column("max_records", sa.Integer(), nullable=False),
        sa.Column("used_records", sa.Integer(), nullable=False),
        sa.Column("max_requests", sa.Integer(), nullable=False),
        sa.Column("used_requests", sa.Integer(), nullable=False),
        sa.Column("reference", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
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
            "max_records > 0 AND used_records >= 0 AND used_records <= max_records",
            name=op.f("ck_import_permits_bounded_budget"),
        ),
        sa.CheckConstraint(
            "max_requests > 0 AND used_requests >= 0 AND used_requests <= max_requests",
            name=op.f("ck_import_permits_bounded_requests"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["data_sources.id"],
            name=op.f("fk_import_permits_source_id_data_sources"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_permits")),
        sa.UniqueConstraint("source_id", name=op.f("uq_import_permits_source_id")),
    )
    op.create_table(
        "source_policies",
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("license_url", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("allowed_fields", sa.JSON(), nullable=False),
        sa.Column("computation_allowed", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("version >= 1", name=op.f("ck_source_policies_positive_version")),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["data_sources.id"],
            name=op.f("fk_source_policies_source_id_data_sources"),
        ),
        sa.PrimaryKeyConstraint("source_id", name=op.f("pk_source_policies")),
    )
    op.create_index(
        op.f("ix_source_policies_expires_at"), "source_policies", ["expires_at"], unique=False
    )
    op.create_table(
        "import_rows",
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("review_reference", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("place_id", sa.String(length=36), nullable=True),
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
            "status IN ('validated','rejected','duplicate','applied','skipped')",
            name=op.f("ck_import_rows_valid_status"),
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["import_batches.id"],
            name=op.f("fk_import_rows_batch_id_import_batches"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["place_id"], ["places.id"], name=op.f("fk_import_rows_place_id_places")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_rows")),
        sa.UniqueConstraint("batch_id", "sequence", name=op.f("uq_import_rows_batch_id")),
    )
    op.create_index(op.f("ix_import_rows_batch_id"), "import_rows", ["batch_id"], unique=False)
    op.create_table(
        "place_field_provenance",
        sa.Column("place_id", sa.String(length=36), nullable=False),
        sa.Column("field", sa.String(length=100), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("missing_reason", sa.String(length=100), nullable=True),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["place_id"],
            ["places.id"],
            name=op.f("fk_place_field_provenance_place_id_places"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["data_sources.id"],
            name=op.f("fk_place_field_provenance_source_id_data_sources"),
        ),
        sa.PrimaryKeyConstraint("place_id", "field", name=op.f("pk_place_field_provenance")),
    )
    op.add_column("places", sa.Column("normalized_name", sa.String(length=200), nullable=True))
    # Keep existing UUIDs and facts; backfill only the derived, indexed duplicate key.
    connection = op.get_bind()
    last_id = ""
    while True:
        rows = connection.execute(
            sa.text("SELECT id, name FROM places WHERE id > :last ORDER BY id LIMIT 500"),
            {"last": last_id},
        ).all()
        if not rows:
            break
        connection.execute(
            sa.text("UPDATE places SET normalized_name=:normalized WHERE id=:id"),
            [
                {
                    "id": row.id,
                    "normalized": sha256(
                        "".join(unicodedata.normalize("NFKC", row.name).casefold().split()).encode(
                            "utf-8"
                        )
                    ).hexdigest(),
                }
                for row in rows
            ],
        )
        last_id = rows[-1].id
    op.add_column("places", sa.Column("price_conditions", sa.String(length=1000), nullable=True))
    op.create_index(
        "ix_places_city_kind_normalized_name",
        "places",
        ["city_id", "kind", "normalized_name"],
        unique=False,
    )
    op.add_column(
        "recommendation_runs",
        sa.Column("scope_key", sa.String(length=100), server_default="global", nullable=False),
    )
    op.create_index(
        op.f("ix_recommendation_runs_scope_key"), "recommendation_runs", ["scope_key"], unique=False
    )


def downgrade():
    op.drop_index(op.f("ix_recommendation_runs_scope_key"), table_name="recommendation_runs")
    op.drop_column("recommendation_runs", "scope_key")
    op.drop_index("ix_places_city_kind_normalized_name", table_name="places")
    op.drop_column("places", "price_conditions")
    op.drop_column("places", "normalized_name")
    op.drop_table("place_field_provenance")
    op.drop_index(op.f("ix_import_rows_batch_id"), table_name="import_rows")
    op.drop_table("import_rows")
    op.drop_index(op.f("ix_source_policies_expires_at"), table_name="source_policies")
    op.drop_table("source_policies")
    op.drop_table("import_permits")
    op.drop_index(op.f("ix_import_batches_source_id"), table_name="import_batches")
    op.drop_table("import_batches")
    op.drop_index(op.f("ix_city_aliases_city_id"), table_name="city_aliases")
    op.drop_table("city_aliases")
