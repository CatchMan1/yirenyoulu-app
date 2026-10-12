from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.settings import Settings


def make_engine(settings: Settings):
    return create_engine(settings.database_url, pool_pre_ping=True, hide_parameters=True)


def session_factory(settings: Settings):
    return sessionmaker(bind=make_engine(settings), expire_on_commit=False)
