"""Run only against the dedicated integration database, never a supplied legacy DB."""

import os
from hashlib import sha256
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from app.db import make_engine
from app.settings import Settings


@pytest.mark.skipif(
    not os.getenv("RUN_POSTGRES_TESTS"), reason="PostgreSQL integration environment not configured"
)
def test_postgres_migration_round_trip(monkeypatch):
    # Settings rejects any database name other than yirenyoulu_test in test mode.
    settings = Settings()
    assert settings.app_env == "test", "destructive migration round-trip requires APP_ENV=test"
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    engine = make_engine(settings)
    with engine.connect() as conn:
        assert inspect(conn).get_table_names() == [], (
            "integration test must start with an empty dedicated database"
        )
    command.upgrade(config, "a5552c8a1d17")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO cities (id,code,name,timezone) VALUES ('migration-city','migration-city','TEST city','Asia/Shanghai')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO data_sources (id,name,kind,commercial_display_allowed,storage_allowed) VALUES ('migration-source','TEST existing provider','provider',false,false)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO places (id,kind,name,city_id,source_id,currency,status,is_test) VALUES ('migration-place','attraction','ＴＥＳＴ  Museum','migration-city','migration-source','CNY','active',true)"
            )
        )
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO places (id,kind,name,city_id,source_id,currency,status,is_test) VALUES ('migration-expansion','attraction',:name,'migration-city','migration-source','CNY','active',true)"
            ),
            {"name": "ß" * 200},
        )
    command.upgrade(config, "head")
    with engine.connect() as conn:
        assert (
            len(
                conn.execute(
                    text("SELECT normalized_name FROM places WHERE id='migration-expansion'")
                ).scalar_one()
            )
            <= 64
        )

        assert (
            conn.execute(
                text("SELECT normalized_name FROM places WHERE id='migration-place'")
            ).scalar_one()
            == sha256(b"testmuseum").hexdigest()
        )
        names = set(inspect(conn).get_table_names())
        assert {
            "users",
            "places",
            "planning_jobs",
            "trips",
            "trip_items",
            "chat_sessions",
            "behavior_events",
        } <= names
        assert (
            conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == ScriptDirectory.from_config(config).get_current_head()
        )
    command.check(config)  # Detect drift between checked-in migration and ORM.
    command.downgrade(config, "base")
    with engine.connect() as conn:
        assert set(inspect(conn).get_table_names()) <= {"alembic_version"}
    command.upgrade(config, "head")
    command.check(config)
    engine.dispose()
