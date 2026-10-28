"""Overture updates are explicit, versioned, idempotent and preserve saved facts."""

import json
import struct
from copy import deepcopy
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from test_data_tasks import approved_source

from app.ingestion import grant_permit
from app.models import ImportPermit, Place, PlaceExternalId, SourcePolicy
from support import auth, fixture_id, login, register


def raw_place(external_id="test-overture-1", status="open"):
    return {
        "id": external_id,
        "names": {"primary": "TEST Overture Restaurant"},
        "addresses": [{"country": "CN", "locality": "TEST City", "freeform": "TEST Address"}],
        "sources": [{"license": "CC0-1.0", "dataset": "TEST synthetic source"}],
        "operating_status": status,
        "confidence": 0.9,
        "taxonomy": {"hierarchy": ["restaurant"]},
        "bbox": {"xmin": 116.4, "xmax": 116.4, "ymin": 39.9, "ymax": 39.9},
        "geometry_hex": struct.pack("<BIdd", 1, 1, 116.4, 39.9).hex(),
        "version": 1,
    }


@pytest.fixture
def run_import(api, tmp_path, monkeypatch):
    import import_overture as cli

    client, factory = api
    engine = factory.kw["bind"]
    monkeypatch.setattr(cli, "make_engine", lambda settings: engine)
    monkeypatch.setattr(cli, "load_settings", lambda path: None)
    monkeypatch.setattr(cli, "check_readiness", lambda engine: None)
    monkeypatch.setattr(engine, "dispose", lambda: None)
    sid = approved_source(factory, cli.SOURCE)
    city = fixture_id("city")
    from app.models import CityAlias

    with factory.begin() as db:
        db.add(CityAlias(city_id=city, namespace="wikidata", external_id="Q100", name="TEST City"))
    grant_permit(factory, sid, [city], 100, "TEST operator approval")
    cfg = {"qid": "Q100", "names": ["TEST City"], "bounds": [116.3, 39.8, 116.5, 40.0]}

    def run(rows, release="2026-09-01.0", *, refresh=False, apply=True):
        snapshot = tmp_path / "snapshot.json"
        catalog = tmp_path / "cities.json"
        snapshot.write_text(json.dumps({"release": release, "city": cfg, "records": rows}))
        catalog.write_text(json.dumps({"release": release, "cities": {"Q100": cfg}}))
        argv = [
            "import_overture",
            "--snapshot",
            str(snapshot),
            "--catalog",
            str(catalog),
            "--env-file",
            str(tmp_path / ".env"),
        ]
        if refresh:
            argv.append("--refresh-existing")
        if apply:
            argv.append("--apply")
        monkeypatch.setattr("sys.argv", argv)
        cli.main()
        with factory() as db:
            return [
                (p.id, p.name, p.status, p.checked_at)
                for p in db.scalars(select(Place).where(Place.source_id == sid).order_by(Place.id))
            ]

    return run, sid


def test_refresh_updates_identity_keeps_snapshot_and_replay_budget(api, run_import):
    client, factory = api
    run, sid = run_import
    first = run([raw_place()])
    pid = first[0][0]
    register(client)
    tokens = login(client)
    trip = client.post(
        "/api/v1/trips",
        json={
            "title": "TEST Trip",
            "city_id": fixture_id("city"),
            "start_date": "2027-01-01",
            "end_date": "2027-01-01",
        },
        headers={**auth(tokens), "Idempotency-Key": "test-overture-snapshot"},
    )
    assert trip.status_code == 201, trip.text
    tid = trip.json()["data"]["id"]
    added = client.post(
        "/api/v1/trips/" + tid + "/items",
        json={
            "version": 1,
            "place_id": pid,
            "date": "2027-01-01",
            "start_minute": 600,
            "end_minute": 660,
        },
        headers=auth(tokens),
    )
    assert added.status_code == 201, added.text
    saved = deepcopy(added.json()["data"]["items"][0]["snapshot"])
    row = raw_place()
    row["names"]["primary"] = "TEST Renamed Restaurant"
    assert run([row], "2026-10-01.0")[0][1] == first[0][1]  # Opt-in required.
    assert run([row], "2026-10-01.0", refresh=True, apply=False)[0][1] == first[0][1]
    updated = run([row], "2026-10-01.0", refresh=True)
    assert updated[0][:3] == (pid, "TEST Renamed Restaurant", "active")
    with factory() as db:
        budget = db.scalar(select(ImportPermit.used_records).where(ImportPermit.source_id == sid))
    assert run([row], "2026-10-01.0", refresh=True) == updated
    assert run([raw_place()], refresh=True) == updated  # An old release copied today stays old.
    with factory() as db:
        assert (
            db.scalar(select(ImportPermit.used_records).where(ImportPermit.source_id == sid))
            == budget
        )
        assert (
            len(db.scalars(select(PlaceExternalId).where(PlaceExternalId.source_id == sid)).all())
            == 1
        )
    detail = client.get("/api/v1/trips/" + trip.json()["data"]["id"], headers=auth(tokens))
    assert detail.json()["data"]["items"][0]["snapshot"] == saved


def test_only_validated_known_permanent_closure_is_deactivated(api, run_import):
    _, factory = api
    run, sid = run_import
    initial = run([raw_place()])
    assert run([], "2026-10-01.0", refresh=True) == initial
    assert run([raw_place(status="temporarily_closed")], "2026-10-01.0", refresh=True) == initial
    closed = raw_place(status="permanently_closed")
    fresh_closed = raw_place("never-imported", "permanently_closed")
    result = run([closed, fresh_closed], "2026-10-01.0", refresh=True)
    assert len(result) == 1 and result[0][2] == "inactive"
    assert result[0][0] == initial[0][0]
    assert run([raw_place()], refresh=True) == result
    assert run([raw_place(status=None)], "2026-10-02.0", refresh=True)[0][2] == "inactive"
    assert run([raw_place()], "2026-10-03.0", refresh=True)[0][2] == "active"
    with factory() as db:
        assert db.get(Place, initial[0][0]).source_id == sid


@pytest.mark.parametrize("failure", ["policy", "permit", "budget", "field"])
def test_refresh_still_requires_current_source_policy(api, run_import, failure):
    _, factory = api
    run, sid = run_import
    initial = run([raw_place()])
    with factory.begin() as db:
        policy = db.get(SourcePolicy, sid)
        permit = db.scalar(select(ImportPermit).where(ImportPermit.source_id == sid))
        if failure == "policy":
            policy.expires_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        elif failure == "permit":
            permit.expires_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        elif failure == "budget":
            permit.max_records = permit.used_records
        else:
            policy.allowed_fields = [f for f in policy.allowed_fields if f != "status"]
    code = {
        "policy": "SOURCE_NOT_AUTHORIZED",
        "permit": "IMPORT_PERMIT_EXPIRED",
        "budget": "PERMIT_EXHAUSTED",
        "field": "UNLICENSED_FIELD",
    }[failure]
    with pytest.raises(ValueError, match=code):
        run([raw_place(status="permanently_closed")], "2026-10-01.0", refresh=True)
    with factory() as db:
        assert db.get(Place, initial[0][0]).status == "active"


def test_release_order_is_rechecked_inside_the_import_transaction(api, run_import):
    from app.http import utcnow
    from app.ingestion import apply_batch, approve_batch, create_batch
    from app.overture import adapt_record

    _, factory = api
    run, sid = run_import
    pid = run([raw_place()])[0][0]
    # Legacy imports used filesystem mtime, which may be later than the source release.
    with factory.begin() as db:
        db.scalar(
            select(PlaceExternalId).where(PlaceExternalId.source_id == sid)
        ).fetched_at = utcnow()
    batches = []
    for revision in (0, 1):
        row = raw_place()
        row["names"]["primary"] = f"TEST revision {revision}"
        record = adapt_record(
            row,
            city_names=["TEST City"],
            bounds=[116, 39, 117, 40],
            release=f"2026-10-01.{revision}",
            observed_at="2026-10-01T00:00:00+00:00",
        )
        batch = create_batch(
            factory, sid, fixture_id("city"), "restaurant", [record], f"test-race-{revision}"
        )
        approve_batch(factory, batch, "TEST review")
        batches.append(batch)
    apply_batch(factory, batches[1])
    result = apply_batch(factory, batches[0])
    assert result["skipped"] == 1
    with factory() as db:
        assert db.get(Place, pid).name == "TEST revision 1"
