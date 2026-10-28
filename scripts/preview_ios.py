"""Loopback-only UI preview API with labelled fixtures in a disposable in-memory DB."""

import sys
from pathlib import Path
from secrets import token_urlsafe

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend/tests"))


def main():
    import uvicorn
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.api import create_app
    from app.models import Base
    from app.settings import Settings
    from support import seed_fixtures

    settings = Settings(
        app_env="test",
        database_url="postgresql+psycopg://fixture@localhost/yirenyoulu_test",
        jwt_secret=token_urlsafe(48),
        cors_origins=["http://127.0.0.1:8081", "http://localhost:8081"],
    )
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)  # Only this isolated preview; production uses Alembic.
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        seed_fixtures(db, settings)
    print("TEST PREVIEW: synthetic places and newly registered accounts exist only in memory.")
    try:
        uvicorn.run(create_app(settings, factory), host="127.0.0.1", port=18000, access_log=False)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
