import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.models import Base, Place, BehaviorEvent, User
from app.seed import seed_fixtures
from app.settings import Settings


def test_seed_is_idempotent_and_never_creates_real_behavior():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    settings = Settings(app_env='test', database_url='postgresql+psycopg://localhost/yirenyoulu_test')
    with Session(engine) as db:
        seed_fixtures(db, settings)
        seed_fixtures(db, settings)
        places = db.scalars(select(Place)).all()
        assert len(places) == 9
        assert all(p.is_test and p.name.startswith('【测试】') for p in places)
        assert {p.kind for p in places} == {'attraction','hotel','restaurant'}
        assert all(p.price_minor is None and p.latitude is None for p in places)
        assert db.scalars(select(BehaviorEvent)).all() == []
        assert db.scalars(select(User)).all() == []


def test_seed_refuses_production():
    settings = Settings(app_env='production', database_url='postgresql+psycopg://localhost/yirenyoulu_prod')
    with pytest.raises(ValueError, match='fixture'):
        seed_fixtures(None, settings)
