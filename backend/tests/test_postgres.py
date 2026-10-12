"""Run only against the dedicated integration database, never a supplied legacy DB."""
import os
from pathlib import Path
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from app.db import make_engine
from app.settings import Settings


@pytest.mark.skipif(not os.getenv('RUN_POSTGRES_TESTS'), reason='PostgreSQL integration environment not configured')
def test_postgres_migration_round_trip(monkeypatch):
    # Settings rejects any database name other than yirenyoulu_test in test mode.
    settings = Settings()
    assert settings.app_env == 'test', 'destructive migration round-trip requires APP_ENV=test'
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    engine = make_engine(settings)
    with engine.connect() as conn:
        assert inspect(conn).get_table_names() == [], 'integration test must start with an empty dedicated database'
    command.upgrade(config, 'head')
    with engine.connect() as conn:
        names = set(inspect(conn).get_table_names())
        assert {'users','places','planning_jobs','trips','trip_items','chat_sessions','behavior_events'} <= names
        assert conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '0001_initial'
    command.check(config)  # Detect drift between checked-in migration and ORM.
    command.downgrade(config, 'base')
    with engine.connect() as conn:
        assert set(inspect(conn).get_table_names()) <= {'alembic_version'}
    command.upgrade(config, 'head')
    command.check(config)
    engine.dispose()
