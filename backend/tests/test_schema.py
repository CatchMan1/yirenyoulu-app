"""Fast constraint tests; PostgreSQL migration tests are a separate gate."""

import os
from datetime import date

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Base,
    City,
    DataSource,
    Favorite,
    Place,
    PlaceExternalId,
    PlanningJob,
    Trip,
    TripItem,
    User,
)


@pytest.fixture
def db():
    postgres = bool(os.getenv("RUN_POSTGRES_TESTS"))
    if postgres:
        from app.settings import Settings

        settings = Settings()
        assert settings.app_env == "test"
        engine = create_engine(settings.database_url)
    else:
        engine = create_engine("sqlite://")

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(engine)
    connection = engine.connect()
    transaction = connection.begin()
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        session.add_all(
            [
                User(
                    id="u1",
                    username="test_one",
                    email="one@example.invalid",
                    password_hash="fixture-hash",
                ),
                User(
                    id="u2",
                    username="test_two",
                    email="two@example.invalid",
                    password_hash="fixture-hash",
                ),
                DataSource(id="s1", name="FIXTURE ONLY", kind="fixture"),
                City(id="c1", name="测试城", code="fixture-city"),
            ]
        )
        session.commit()
        session.add(
            Place(
                id="p1",
                name="测试景点",
                kind="attraction",
                city_id="c1",
                source_id="s1",
                is_test=True,
            )
        )
        session.commit()
        yield session
    transaction.rollback()
    connection.close()
    engine.dispose()


def test_duplicate_favorite_is_rejected(db):
    db.add_all([Favorite(user_id="u1", place_id="p1"), Favorite(user_id="u1", place_id="p1")])
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    assert db.scalars(select(Favorite)).all() == []


@pytest.mark.parametrize(
    "changes",
    [
        dict(latitude=91, longitude=10, coordinate_system="GCJ-02"),
        dict(latitude=1),
        dict(latitude=1, longitude=2),
        dict(kind="made_up"),
        dict(price_minor=-1),
    ],
)
def test_invalid_place_data_is_rejected(db, changes):
    data = dict(
        id="p2", name="测试无效数据", kind="attraction", city_id="c1", source_id="s1", is_test=True
    )
    data.update(changes)
    db.add(Place(**data))
    with pytest.raises(IntegrityError):
        db.commit()


def test_missing_facts_stay_unknown(db):
    place = db.get(Place, "p1")
    assert place.price_minor is None
    assert place.latitude is None
    assert place.rating_value is None
    assert place.opening_hours is None


def test_duplicate_external_id_rejected(db):
    db.add_all(
        [
            PlaceExternalId(place_id="p1", source_id="s1", external_id="fixture-1"),
            PlaceExternalId(place_id="p1", source_id="s1", external_id="fixture-1"),
        ]
    )
    with pytest.raises(IntegrityError):
        db.commit()


def test_job_key_unique_per_user_and_rollback(db):
    db.add_all(
        [
            PlanningJob(
                user_id="u1", idempotency_key="fixture-key", request_hash="hash", request_payload={}
            ),
            PlanningJob(
                user_id="u1", idempotency_key="fixture-key", request_hash="hash", request_payload={}
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    assert db.scalars(select(PlanningJob)).all() == []


def test_snapshot_survives_catalog_update(db):
    db.add(
        Trip(
            id="t1",
            user_id="u1",
            title="测试行程",
            city_id="c1",
            start_date=date(2026, 10, 13),
            end_date=date(2026, 10, 13),
        )
    )
    db.commit()
    db.add(
        TripItem(
            trip_id="t1",
            place_id="p1",
            visit_date=date(2026, 10, 13),
            start_minute=600,
            end_minute=660,
            snapshot={"name": "测试景点", "price_minor": None, "is_test": True},
        )
    )
    db.commit()
    db.get(Place, "p1").name = "测试更新名称"
    db.commit()
    item = db.scalar(select(TripItem))
    assert item.snapshot["name"] == "测试景点"
    assert item.snapshot["price_minor"] is None


def test_foreign_key_rejects_missing_place(db):
    db.add(Favorite(user_id="u1", place_id="missing"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_postgres_constraint_names_are_distinct_within_each_table():
    # PostgreSQL backs UNIQUE with schema-visible indexes; SQLite permits the
    # accidental duplicate names and therefore cannot catch this migration bug.
    from sqlalchemy import PrimaryKeyConstraint, UniqueConstraint

    for table in Base.metadata.sorted_tables:
        names = [
            c.name
            for c in table.constraints
            if isinstance(c, (UniqueConstraint, PrimaryKeyConstraint))
        ]
        assert len(names) == len(set(names)), (
            f"duplicate PostgreSQL index-backed constraint in {table.name}"
        )
