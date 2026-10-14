from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.settings import Settings


def make_engine(settings: Settings):
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_timeout=5,
        connect_args={
            "connect_timeout": 5,
            "options": "-c statement_timeout=10000 -c lock_timeout=5000",
        },
        hide_parameters=True,
    )


def session_factory(settings: Settings):
    return sessionmaker(bind=make_engine(settings), expire_on_commit=False)
