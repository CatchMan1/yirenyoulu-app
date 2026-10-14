from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Base, City, DataSource, Place, PlanningJob, Trip, TripItem, User


def test_lodging_can_use_null_minutes_but_partial_minutes_are_rejected():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all(
            [
                User(
                    id="u",
                    username="fixture",
                    email="fixture@example.com",
                    password_hash="not-a-login",
                ),
                City(id="c", code="fixture", name="【测试】"),
                DataSource(id="s", name="fixture", kind="fixture"),
            ]
        )
        db.flush()
        db.add(
            Place(
                id="p", name="【测试】酒店", kind="hotel", city_id="c", source_id="s", is_test=True
            )
        )
        db.flush()
        db.add(
            Trip(
                id="t",
                user_id="u",
                title="【测试】",
                city_id="c",
                start_date=date(2027, 1, 1),
                end_date=date(2027, 1, 2),
            )
        )
        db.commit()
        db.add(
            TripItem(
                trip_id="t",
                place_id="p",
                visit_date=date(2027, 1, 1),
                start_minute=None,
                end_minute=None,
                snapshot={"kind": "hotel"},
            )
        )
        try:
            db.commit()
        except IntegrityError:
            pytest.fail("Lodging must persist null minute fields")
        assert db.scalar(select(TripItem)).start_minute is None
        db.add(
            TripItem(
                trip_id="t",
                place_id="p",
                visit_date=date(2027, 1, 2),
                start_minute=None,
                end_minute=600,
                snapshot={"kind": "hotel"},
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
    engine.dispose()


def test_task_result_has_durable_deleted_marker():
    job = PlanningJob(
        user_id="fixture", idempotency_key="fixture", request_hash="x", request_payload={}
    )
    assert hasattr(job, "result_deleted"), "Deletion must not lose task idempotency outcome"
