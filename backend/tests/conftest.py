"""All destructive fixture setup is restricted to the dedicated test database."""

import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.settings import Settings
from support import seed_fixtures

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


@pytest.fixture
def api():
    settings = Settings(
        app_env="test",
        database_url="postgresql+psycopg://fixture@localhost/yirenyoulu_test",
        jwt_secret=uuid4().hex * 2,
    )
    pg_url = os.getenv("ITERATION_HTTP_DATABASE_URL")
    if pg_url:
        Settings(app_env="test", database_url=pg_url)
        engine = create_engine(pg_url, hide_parameters=True)
        with engine.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())
    else:
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        seed_fixtures(db, settings)
    from app.api import create_app

    app = create_app(settings, factory)
    with TestClient(app, raise_server_exceptions=False) as client:
        from wire_contract import check_response

        client.event_hooks["response"].append(lambda response: check_response(app, response))
        yield client, factory
    if pg_url:
        with engine.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())
    engine.dispose()
