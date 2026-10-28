"""Quality counts must separate inventory from usable, non-test facts."""

from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.http import utcnow
from app.models import City, DataSource, ImportBatch, ImportRow, Place, PlaceImage, SourcePolicy
from support import fixture_id


def test_quality_groups_inventory_permissions_missing_facts_and_pending_review(api):
    from app.data_operator import execute

    _, factory = api
    city_id = str(uuid4())
    source_id = str(uuid4())
    expired_id = str(uuid4())
    with factory.begin() as db:
        db.add(City(id=city_id, code="TEST quality", name="TEST quality city"))
        for sid, name in [(source_id, "TEST usable"), (expired_id, "TEST expired")]:
            db.add(
                DataSource(
                    id=sid,
                    name=name,
                    kind="provider",
                    storage_allowed=True,
                    commercial_display_allowed=True,
                    reviewed_at=utcnow(),
                )
            )
        db.flush()
        for sid, days in [(source_id, 1), (expired_id, -1)]:
            db.add(
                SourcePolicy(
                    source_id=sid,
                    version=1,
                    license_url="https://example.invalid",
                    evidence="TEST",
                    allowed_fields=[],
                    computation_allowed=False,
                    expires_at=utcnow() + timedelta(days=days),
                )
            )
        ids = [str(uuid4()) for _ in range(5)]
        for i, pid in enumerate(ids):
            db.add(
                Place(
                    id=pid,
                    name=f"TEST {i}",
                    kind="hotel",
                    city_id=city_id,
                    source_id=expired_id if i == 3 else source_id,
                    status="inactive" if i == 4 else "active",
                    is_test=i == 2,
                    checked_at=utcnow() - timedelta(days=31) if i == 1 else None,
                )
            )
        db.flush()
        place = db.get(Place, ids[0])
        place.checked_at = utcnow()
        place.address = "TEST address"
        place.longitude, place.latitude, place.coordinate_system = 116.4, 39.9, "WGS84"
        place.price_minor, place.price_unit = 0, "night"
        place.rating_value, place.rating_scale = 0, 5
        place.opening_hours = {"note": "TEST hours"}
        db.add(
            PlaceImage(
                place_id=ids[0],
                source_id=source_id,
                url="https://example.invalid/test.png",
                display_allowed=True,
            )
        )
        db.add(
            PlaceImage(
                place_id=ids[1],
                source_id=expired_id,
                url="https://example.invalid/expired.png",
                display_allowed=True,
            )
        )
        batch = ImportBatch(
            source_id=source_id,
            city_id=city_id,
            kind="hotel",
            key="TEST",
            input_hash="0" * 64,
            policy_version=1,
            total=1,
        )
        db.add(batch)
        db.flush()
        db.add(ImportRow(batch_id=batch.id, sequence=0, status="duplicate"))
    result = execute(SimpleNamespace(action="quality", city=city_id, stale_days=30), factory)
    assert len(result["cities"]) == 1
    hotel = result["cities"][0]["groups"]["hotel"]
    assert hotel["total"] == 5 and hotel["active"] == 4 and hotel["inactive"] == 1
    assert hotel["test_places"] == 1
    assert hotel["display_eligible"] == 2 and hotel["computation_eligible"] == 0
    assert set(hotel["missing"].values()) == {1}
    assert hotel["freshness"] == {"recent": 1, "stale": 1, "unknown": 0, "future": 0}
    assert hotel["pending_duplicate_rows"] == 1
    assert result["cities"][0]["groups"]["restaurant"]["total"] == 0
    with factory() as db:
        assert db.get(Place, ids[1]).checked_at is not None


def test_quality_fixture_facts_are_never_counted_as_real_completeness(api):
    from app.data_quality import quality_report

    _, factory = api
    report = quality_report(factory, city_id=fixture_id("city"))
    for group in report["cities"][0]["groups"].values():
        assert group["total"] == group["test_places"] == 3
        assert group["display_eligible"] == group["computation_eligible"] == 0
        assert sum(group["missing"].values()) == sum(group["freshness"].values()) == 0
    with pytest.raises(ValueError, match="STALE_DAYS"):
        quality_report(factory, stale_days=0)
    with pytest.raises(ValueError, match="CITY_NOT_FOUND"):
        quality_report(factory, city_id=str(uuid4()))
    from app.data_operator import parser

    assert parser().parse_args(["quality", "--city", fixture_id("city")]).stale_days == 30
    with pytest.raises(SystemExit):
        parser().parse_args(["quality", "--city", "invalid"])
