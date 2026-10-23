"""Synthetic open-place records; never real customer or merchant data."""

import struct
from copy import deepcopy

import pytest


def sample():
    return {
        "id": "test-place-1",
        "names": {"primary": "TEST 酒店"},
        "addresses": [{"country": "CN", "locality": "Beijing", "freeform": "TEST address"}],
        "sources": [{"dataset": "meta", "license": "CDLA-Permissive-2.0"}],
        "operating_status": "open",
        "taxonomy": {"primary": "hotel", "hierarchy": ["lodging", "hotel"]},
        "bbox": {"xmin": 116.4, "xmax": 116.4, "ymin": 39.9, "ymax": 39.9},
        "version": 1,
        "confidence": 0.9,
        "geometry_hex": struct.pack("<BIdd", 1, 1, 116.4, 39.9).hex(),
    }


def adapt(value):
    from app.overture import adapt_record

    return adapt_record(
        value,
        city_names=["Beijing", "北京市"],
        bounds=[116.35, 39.87, 116.45, 39.97],
        release="2026-10-21.0",
        observed_at="2026-10-23T00:00:00Z",
    )


def test_adapter_preserves_facts_without_inventing_prices():
    r = adapt(sample())
    assert r["kind"] == "hotel"
    assert r["coordinates"] == {"longitude": 116.4, "latitude": 39.9, "crs": "WGS84"}
    assert "price_minor" not in r and "rating_value" not in r
    assert r["evidence"]["release"] == "2026-10-21.0"


@pytest.mark.parametrize(
    "field,value",
    [
        ("addresses", [{"country": "US", "locality": "Beijing"}]),
        ("addresses", [{"country": "CN", "locality": "Shanghai"}]),
        ("sources", [{"dataset": "unknown", "license": "proprietary"}]),
        ("sources", []),
        ("operating_status", "permanently_closed"),
        ("bbox", {"xmin": 0, "xmax": 0, "ymin": 0, "ymax": 0}),
        ("taxonomy", {"primary": "school", "hierarchy": ["education", "school"]}),
        ("confidence", 0.1),
    ],
)
def test_unsupported_or_unverified_records_cannot_enter_catalog(field, value):
    row = deepcopy(sample())
    row[field] = value
    with pytest.raises(ValueError):
        adapt(row)


def test_restaurant_subtypes_are_classified_from_hierarchy():
    row = sample()
    row["taxonomy"] = {
        "primary": "chinese_restaurant",
        "hierarchy": ["food_and_drink", "restaurant", "chinese_restaurant"],
    }
    assert adapt(row)["kind"] == "restaurant"


def test_snapshot_import_replay_does_not_duplicate_places(api):
    from sqlalchemy import func, select
    from test_ingestion import approved_source

    from app.ingestion import grant_permit
    from app.models import Place
    from app.overture import import_snapshot
    from app.seed import fixture_id

    _, sessions = api
    source = approved_source(sessions)
    city = fixture_id("city")
    grant_permit(sessions, source, [city], 100, "TEST permit")
    records = [adapt(sample())]
    first = import_snapshot(sessions, source, city, records, "TEST snapshot")
    again = import_snapshot(sessions, source, city, records, "TEST snapshot")
    assert first == again
    with sessions() as db:
        assert (
            db.scalar(select(func.count()).select_from(Place).where(Place.source_id == source)) == 1
        )


def test_unknown_operating_status_stays_unknown_in_evidence():
    row = sample()
    row["operating_status"] = None
    result = adapt(row)
    assert result["evidence"]["operating_status"] is None


def test_coordinates_come_from_geometry_not_float32_index_box():
    row = sample()
    row["bbox"] = {"xmin": 116.39999, "xmax": 116.40001, "ymin": 39.89999, "ymax": 39.90001}
    assert adapt(row)["coordinates"]["longitude"] == 116.4


def test_nearby_translated_names_are_held_for_review():
    from app.overture import separate_duplicates

    a = adapt(sample())
    b = dict(a, external_id="test-place-2", name="TEST English hotel")
    accepted, review = separate_duplicates([a, b], [])
    assert len(accepted) == 1 and len(review) == 1
    accepted, review = separate_duplicates([b], [a])
    assert not accepted and len(review) == 1
