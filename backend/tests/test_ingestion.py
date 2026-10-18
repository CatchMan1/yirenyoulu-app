"""Import safety and externally visible source rights; only synthetic fixtures."""

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select

from app.http import utcnow
from app.models import DataSource, Place
from app.seed import fixture_id


def test_unreviewed_provider_is_hidden_from_public_reads(api):
    client, factory = api
    pid = str(uuid4())
    with factory.begin() as db:
        source = DataSource(name="TEST unreviewed provider", kind="provider")
        db.add(source)
        db.flush()
        db.add(
            Place(
                id=pid,
                name="TEST not approved for display",
                kind="hotel",
                city_id=fixture_id("city"),
                source_id=source.id,
            )
        )
    assert client.get("/api/v1/places/" + pid).status_code == 404
    rows = client.get("/api/v1/places").json()["data"]
    assert pid not in {r["id"] for r in rows}
    assert pid not in {
        r["id"] for r in client.get("/api/v1/recommendations").json()["data"]["items"]
    }


def approved_source(factory, name="TEST licensed source"):
    from app.ingestion import RECORD_FIELDS
    from app.models import SourcePolicy

    with factory.begin() as db:
        source = DataSource(
            name=name,
            kind="provider",
            source_url="https://example.invalid/source",
            storage_allowed=True,
            commercial_display_allowed=True,
            reviewed_at=utcnow(),
        )
        db.add(source)
        db.flush()
        db.add(
            SourcePolicy(
                source_id=source.id,
                version=1,
                license_url="https://example.invalid/license",
                evidence="TEST synthetic authorization",
                computation_allowed=True,
                allowed_fields=sorted(RECORD_FIELDS),
                expires_at=utcnow() + timedelta(days=30),
            )
        )
        return source.id


def payload(external_id="test-place", name="TEST imported place"):
    return dict(
        external_id=external_id,
        kind="attraction",
        name=name,
        source_url="https://example.invalid/place",
        observed_at=utcnow().isoformat(),
        coordinates={"longitude": 116.4, "latitude": 39.9, "crs": "WGS84"},
    )


def test_import_needs_permit_review_and_is_idempotent(api):
    from app.ingestion import apply_batch, approve_batch, create_batch, grant_permit

    client, factory = api
    sid = approved_source(factory)
    city = fixture_id("city")
    import pytest

    with pytest.raises(ValueError, match="PERMIT"):
        create_batch(factory, sid, city, "attraction", [payload()], "batch1")
    grant_permit(factory, sid, [city], 10, "TEST scope approval")
    record = payload()
    batch = create_batch(factory, sid, city, "attraction", [record], "batch1")
    assert client.get("/api/v1/places").json()["meta"]["total"] == 9
    with pytest.raises(ValueError, match="REVIEW"):
        apply_batch(factory, batch)
    approve_batch(factory, batch, "TEST reviewed record")
    assert apply_batch(factory, batch)["applied"] == 1
    assert apply_batch(factory, batch)["applied"] == 1
    assert create_batch(factory, sid, city, "attraction", [record], "batch1") == batch
    rows = client.get("/api/v1/places").json()["data"]
    imported = next(r for r in rows if r["name"] == "TEST imported place")
    assert imported["price"] is None and imported["is_test"] is False


def test_invalid_row_is_quarantined_without_partial_place(api):
    from app.ingestion import apply_batch, approve_batch, create_batch, grant_permit, report

    client, factory = api
    sid = approved_source(factory)
    city = fixture_id("city")
    grant_permit(factory, sid, [city], 10, "TEST scope")
    bad = payload()
    bad["coordinates"]["latitude"] = 99
    batch = create_batch(factory, sid, city, "attraction", [bad], "invalid")
    assert report(factory, batch)["rejected"] == 1
    approve_batch(factory, batch, "TEST review")
    assert apply_batch(factory, batch)["applied"] == 0
    assert client.get("/api/v1/places").json()["meta"]["total"] == 9


def test_resume_checkpoint_updates_existing_id_and_rejects_changed_batch(api):
    import pytest

    from app.ingestion import apply_batch, approve_batch, create_batch, grant_permit
    from app.models import PlaceExternalId

    _, factory = api
    sid = approved_source(factory)
    city = fixture_id("city")
    grant_permit(factory, sid, [city], 10, "TEST permit")
    records = [payload("one"), payload("two", "TEST second")]
    batch = create_batch(factory, sid, city, "attraction", records, "resume")
    approve_batch(factory, batch, "TEST review")
    result = apply_batch(factory, batch, max_rows=1)
    assert result["cursor"] == 1 and result["status"] == "approved"
    assert apply_batch(factory, batch)["applied"] == 2
    with pytest.raises(ValueError, match="IDEMPOTENCY"):
        create_batch(factory, sid, city, "attraction", [payload("different")], "resume")
    with factory() as db:
        original = db.scalar(
            select(PlaceExternalId).where(PlaceExternalId.external_id == "one")
        ).place_id
    update_record = payload("one", "TEST newer")
    batch = create_batch(factory, sid, city, "attraction", [update_record], "update")
    approve_batch(factory, batch, "TEST review")
    apply_batch(factory, batch)
    with factory() as db:
        assert db.get(Place, original).name == "TEST newer"
    old = payload("one", "TEST stale")
    old["observed_at"] = (utcnow() - timedelta(days=1)).isoformat()
    batch = create_batch(factory, sid, city, "attraction", [old], "old")
    approve_batch(factory, batch, "TEST review")
    assert apply_batch(factory, batch)["skipped"] == 1
    with factory() as db:
        assert db.get(Place, original).name == "TEST newer"


def test_policy_change_and_expiry_block_pending_import(api):
    import pytest

    from app.ingestion import apply_batch, approve_batch, create_batch, grant_permit
    from app.models import SourcePolicy

    _, factory = api
    sid = approved_source(factory)
    city = fixture_id("city")
    grant_permit(factory, sid, [city], 10, "TEST permit")
    batch = create_batch(factory, sid, city, "attraction", [payload()], "policy")
    approve_batch(factory, batch, "TEST review")
    with factory.begin() as db:
        db.get(SourcePolicy, sid).version += 1
    with pytest.raises(ValueError, match="POLICY_CHANGED"):
        apply_batch(factory, batch)
    with factory.begin() as db:
        db.get(SourcePolicy, sid).expires_at = utcnow() - timedelta(seconds=1)
    with pytest.raises(ValueError, match="SOURCE_NOT_AUTHORIZED"):
        apply_batch(factory, batch)


def test_cross_source_duplicate_requires_reviewed_alias(api):
    from app.ingestion import (
        apply_batch,
        approve_batch,
        create_batch,
        grant_permit,
        resolve_duplicate,
    )
    from app.models import ImportRow, PlaceExternalId

    _, factory = api
    city = fixture_id("city")
    ids = []
    for i in range(2):
        sid = approved_source(factory, "TEST source " + str(i))
        grant_permit(factory, sid, [city], 10, "TEST permit")
        batch = create_batch(factory, sid, city, "attraction", [payload()], "duplicate")
        approve_batch(factory, batch, "TEST review")
        result = apply_batch(factory, batch)
        ids.append(batch)
    assert result["duplicate"] == 1
    with factory() as db:
        target = db.scalar(
            select(PlaceExternalId).where(PlaceExternalId.external_id == "test-place")
        ).place_id
        row_id = db.scalar(select(ImportRow).where(ImportRow.batch_id == ids[1])).id
    resolve_duplicate(factory, row_id, target, "TEST same physical place verified")
    with factory() as db:
        assert (
            len(
                db.scalars(
                    select(PlaceExternalId).where(PlaceExternalId.external_id == "test-place")
                ).all()
            )
            == 2
        )
        assert db.get(ImportRow, row_id).review_reference == "TEST same physical place verified"


def test_rights_retraction_redacts_favorite_and_saved_trip_and_purges_staging(api):
    from app.ingestion import apply_batch, approve_batch, create_batch, grant_permit, revoke_source
    from app.models import ImportRow, PlaceExternalId, TripItem
    from test_api_accounts_catalog import auth, login, register

    client, factory = api
    city = fixture_id("city")
    sid = approved_source(factory)
    grant_permit(factory, sid, [city], 10, "TEST permit")
    batch = create_batch(factory, sid, city, "attraction", [payload()], "retract")
    approve_batch(factory, batch, "TEST review")
    apply_batch(factory, batch)
    with factory() as db:
        pid = db.scalar(select(PlaceExternalId).where(PlaceExternalId.source_id == sid)).place_id
    register(client)
    headers = auth(login(client))
    assert client.put("/api/v1/favorites/" + pid, headers=headers).status_code == 204
    trip = client.post(
        "/api/v1/trips",
        json={
            "title": "TEST rights",
            "city_id": city,
            "start_date": "2027-01-01",
            "end_date": "2027-01-02",
        },
        headers={**headers, "Idempotency-Key": str(uuid4())},
    ).json()["data"]
    trip = client.post(
        "/api/v1/trips/" + trip["id"] + "/items",
        json={
            "version": 1,
            "place_id": pid,
            "date": "2027-01-01",
            "start_minute": 600,
            "end_minute": 660,
        },
        headers=headers,
    ).json()["data"]
    revoke_source(factory, sid)
    assert client.get("/api/v1/places/" + pid).status_code == 404
    favorite = client.get("/api/v1/favorites", headers=headers).json()["data"][0]
    assert favorite["status"] == "inactive" and favorite["coordinates"] is None
    saved = client.get("/api/v1/trips/" + trip["id"], headers=headers).json()["data"]["items"][0]
    assert (
        saved["snapshot"]["name"] != "TEST imported place"
        and saved["snapshot"]["coordinates"] is None
    )
    revoke_source(factory, sid, purge=True)
    with factory() as db:
        assert db.get(Place, pid).longitude is None
        assert db.scalar(select(ImportRow)).payload is None
        assert db.scalar(select(TripItem)).snapshot["coordinates"] is None


def test_bad_category_rolls_back_place_external_id_and_checkpoint(api):
    import pytest

    from app.ingestion import apply_batch, approve_batch, create_batch, grant_permit, report
    from app.models import PlaceExternalId

    _, factory = api
    sid = approved_source(factory)
    city = fixture_id("city")
    grant_permit(factory, sid, [city], 10, "TEST permit")
    record = payload()
    record["category"] = "not-registered"
    batch = create_batch(factory, sid, city, "attraction", [record], "rollback")
    approve_batch(factory, batch, "TEST review")
    with pytest.raises(ValueError, match="CATEGORY_NOT_REGISTERED"):
        apply_batch(factory, batch)
    assert report(factory, batch)["cursor"] == 0
    with factory() as db:
        assert (
            db.scalars(select(PlaceExternalId).where(PlaceExternalId.source_id == sid)).all() == []
        )


def test_imported_price_keeps_conditions_in_api_and_provenance(api):
    from app.ingestion import apply_batch, approve_batch, create_batch, grant_permit
    from app.models import PlaceExternalId, PlaceFieldProvenance

    client, factory = api
    sid = approved_source(factory)
    city = fixture_id("city")
    grant_permit(factory, sid, [city], 10, "TEST permit")
    record = payload()
    record.update(price_minor=1000, price_unit="entry", price_conditions="TEST adult single entry")
    batch = create_batch(factory, sid, city, "attraction", [record], "price")
    approve_batch(factory, batch, "TEST review")
    apply_batch(factory, batch)
    with factory() as db:
        pid = db.scalar(select(PlaceExternalId).where(PlaceExternalId.source_id == sid)).place_id
    price = client.get("/api/v1/places/" + pid).json()["data"]["price"]
    assert price.get("conditions") == "TEST adult single entry"
    with factory() as db:
        assert (
            db.get(PlaceFieldProvenance, (pid, "price_minor")).context["conditions"]
            == "TEST adult single entry"
        )


def test_image_rights_are_checked_independently_of_place_source(api):
    from app.models import PlaceImage

    client, factory = api
    with factory.begin() as db:
        source = DataSource(name="TEST unlicensed image", kind="provider")
        db.add(source)
        db.flush()
        db.add(
            PlaceImage(
                place_id=fixture_id("fixture-attraction-1"),
                source_id=source.id,
                url="https://example.invalid/not-authorized.jpg",
                display_allowed=True,
            )
        )
    assert (
        client.get("/api/v1/places/" + fixture_id("fixture-attraction-1")).json()["data"]["images"]
        == []
    )


def test_failed_apply_has_persistent_safe_error_and_can_resume(api):
    import pytest

    from app.ingestion import apply_batch, approve_batch, create_batch, grant_permit, report
    from app.models import ImportBatch

    _, factory = api
    sid = approved_source(factory)
    city = fixture_id("city")
    grant_permit(factory, sid, [city], 10, "TEST permit")
    record = payload()
    record["category"] = "TEST missing category"
    batch = create_batch(factory, sid, city, "attraction", [record], "failed")
    approve_batch(factory, batch, "TEST review")
    with pytest.raises(ValueError):
        apply_batch(factory, batch)
    assert report(factory, batch)["status"] == "failed"
    with factory() as db:
        assert db.get(ImportBatch, batch).last_error == "CATEGORY_NOT_REGISTERED"

    from app.models import Category

    with factory.begin() as db:
        db.add(Category(code="TEST missing category", name="TEST category"))
    result = apply_batch(factory, batch)
    assert (
        result["status"] == "completed" and result["applied"] == 1 and result["last_error"] is None
    )


def test_cross_source_normalized_names_are_quarantined(api):
    from app.ingestion import apply_batch, approve_batch, create_batch, grant_permit

    _, factory = api
    city = fixture_id("city")
    first = approved_source(factory)
    second = approved_source(factory, "TEST other normalized source")
    for source, name in [(first, "ＴＥＳＴ  Museum"), (second, "test museum")]:
        grant_permit(factory, source, [city], 10, "TEST normalized permit")
        record = payload()
        record["name"] = name
        batch = create_batch(factory, source, city, "attraction", [record], "normalized")
        approve_batch(factory, batch, "TEST normalized review")
        result = apply_batch(factory, batch)
    assert result["duplicate"] == 1 and result["applied"] == 0


def test_concurrent_import_replay_keeps_one_place_and_checkpoint(api):
    import os
    from concurrent.futures import ThreadPoolExecutor

    import pytest
    from sqlalchemy import func, select

    from app.ingestion import apply_batch, approve_batch, create_batch, grant_permit
    from app.models import PlaceExternalId

    if not os.getenv("ITERATION_HTTP_DATABASE_URL"):
        pytest.skip("PostgreSQL row locks required")
    _, factory = api
    sid = approved_source(factory)
    city = fixture_id("city")
    grant_permit(factory, sid, [city], 10, "TEST concurrency permit")
    record = payload()
    with ThreadPoolExecutor(max_workers=2) as workers:
        batches = list(
            workers.map(
                lambda _: create_batch(factory, sid, city, "attraction", [record], "race"), range(2)
            )
        )
    assert batches[0] == batches[1]
    approve_batch(factory, batches[0], "TEST review")
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: apply_batch(factory, batches[0]), range(2)))
    assert all(r["cursor"] == 1 and r["applied"] == 1 for r in results)
    with factory() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(PlaceExternalId)
                .where(PlaceExternalId.source_id == sid)
            )
            == 1
        )


def test_narrower_field_policy_clears_old_facts_payloads_and_snapshots(api):
    from app.ingestion import (
        RECORD_FIELDS,
        apply_batch,
        approve_batch,
        create_batch,
        grant_permit,
        register_policy,
    )
    from app.models import ImportRow
    from test_api_accounts_catalog import auth, login, register

    client, factory = api
    source = approved_source(factory)
    city = fixture_id("city")
    grant_permit(factory, source, [city], 10, "TEST field scope")
    record = payload()
    record.update(
        address="TEST withdrawn address",
        price_minor=100,
        price_unit="entry",
        price_conditions="TEST adult",
    )
    batch = create_batch(factory, source, city, "attraction", [record], "field-shrink")
    approve_batch(factory, batch, "TEST review")
    apply_batch(factory, batch)
    with factory() as db:
        row = db.scalar(select(ImportRow).where(ImportRow.batch_id == batch))
        pid = row.place_id
    register(client)
    tokens = login(client)
    headers = auth(tokens)
    client.put("/api/v1/favorites/" + pid, headers=headers)
    trip = client.post(
        "/api/v1/trips",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "title": "TEST rights",
            "city_id": city,
            "start_date": "2027-01-01",
            "end_date": "2027-01-02",
        },
    ).json()["data"]
    client.post(
        "/api/v1/trips/" + trip["id"] + "/items",
        headers=headers,
        json={
            "version": 1,
            "place_id": pid,
            "date": "2027-01-01",
            "start_minute": 600,
            "end_minute": 660,
        },
    )
    register_policy(
        factory,
        "TEST licensed source",
        "https://example.invalid/license",
        "TEST narrower review",
        sorted(
            RECORD_FIELDS
            - {"coordinates", "address", "price_minor", "price_unit", "price_conditions"}
        ),
        True,
    )
    assert client.get("/api/v1/places/" + pid).status_code == 404
    favorite = client.get("/api/v1/favorites", headers=headers).json()["data"][0]
    assert (
        favorite["coordinates"] is None
        and favorite["price"] is None
        and favorite["address"] is None
    )
    historical = client.get("/api/v1/trips/" + trip["id"], headers=headers).json()["data"]["items"][
        0
    ]["snapshot"]
    assert (
        historical["coordinates"] is None
        and historical["price"] is None
        and historical["address"] is None
    )
    with factory() as db:
        assert db.get(Place, pid).longitude is None and db.get(Place, pid).price_minor is None
        assert db.scalar(select(ImportRow).where(ImportRow.batch_id == batch)).payload is None


def test_planning_respects_computation_permission_at_lookup_and_save(api):
    from app.ingestion import apply_batch, approve_batch, create_batch, grant_permit
    from app.models import SourcePolicy
    from app.planning import CatalogTools, run_once
    from test_api_accounts_catalog import auth, login, register

    client, factory = api
    source = approved_source(factory)
    city = fixture_id("city")
    grant_permit(factory, source, [city], 10, "TEST plan permit")
    batch = create_batch(factory, source, city, "attraction", [payload()], "plan-rights")
    approve_batch(factory, batch, "TEST review")
    apply_batch(factory, batch)
    with factory() as db:
        pid = db.scalar(select(Place.id).where(Place.source_id == source))
    with factory.begin() as db:
        db.get(SourcePolicy, source).computation_allowed = False
    assert client.get("/api/v1/places/" + pid).status_code == 200
    assert pid not in {
        v["place_id"] for v in CatalogTools(factory, city, []).search_places("attraction")
    }
    register(client)
    headers = auth(login(client))
    client.app.state.settings.ai_provider = "mock"
    with factory.begin() as db:
        db.get(SourcePolicy, source).computation_allowed = True
    job = client.post(
        "/api/v1/planning-jobs",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"city_id": city, "start_date": "2027-01-01", "end_date": "2027-01-01"},
    ).json()["data"]

    class WithdrawDuringPlan:
        def plan(self, payload, tools):
            assert pid in {v["place_id"] for v in tools.search_places("attraction")}
            with factory.begin() as db:
                db.get(SourcePolicy, source).computation_allowed = False
            return [{"place_id": pid, "date": "2027-01-01", "start_minute": 600, "end_minute": 660}]

    run_once(client.app.state.settings, factory, WithdrawDuringPlan())
    result = client.get("/api/v1/planning-jobs/" + job["id"], headers=headers).json()["data"]
    assert result["status"] == "failed" and result["trip_id"] is None


def test_expiration_rechecks_renewal_before_destructive_cleanup(api, monkeypatch):
    from app import ingestion
    from app.models import SourcePolicy

    client, factory = api
    source = approved_source(factory)
    city = fixture_id("city")
    ingestion.grant_permit(factory, source, [city], 10, "TEST expiry permit")
    batch = ingestion.create_batch(factory, source, city, "attraction", [payload()], "expiry-race")
    ingestion.approve_batch(factory, batch, "TEST review")
    ingestion.apply_batch(factory, batch)
    with factory() as db:
        pid = db.scalar(select(Place.id).where(Place.source_id == source))
    with factory.begin() as db:
        db.get(SourcePolicy, source).expires_at = utcnow() - timedelta(seconds=1)
    original = ingestion.revoke_source

    def renew_before_cleanup(sessions, source_id, **kwargs):
        ingestion.register_policy(
            sessions,
            "TEST licensed source",
            "https://example.invalid/license",
            "TEST renewed",
            sorted(ingestion.RECORD_FIELDS),
            True,
        )
        return original(sessions, source_id, **kwargs)

    monkeypatch.setattr(ingestion, "revoke_source", renew_before_cleanup)
    assert ingestion.expire_sources(factory)["expired_sources"] == 0
    assert client.get("/api/v1/places/" + pid).status_code == 200
    with factory() as db:
        assert db.get(Place, pid).name == "TEST imported place"


def test_import_name_normalization_expansion_is_bounded(api):
    from app.ingestion import apply_batch, approve_batch, create_batch, grant_permit

    _, factory = api
    source = approved_source(factory)
    city = fixture_id("city")
    grant_permit(factory, source, [city], 10, "TEST expanded names")
    batch = create_batch(
        factory, source, city, "attraction", [payload(name="ß" * 200)], "long-normalized"
    )
    approve_batch(factory, batch, "TEST review")
    assert apply_batch(factory, batch)["applied"] == 1
    with factory() as db:
        assert len(db.scalar(select(Place).where(Place.source_id == source)).normalized_name) <= 64


def test_primary_provenance_links_place_evidence(api):
    from app.ingestion import apply_batch, approve_batch, create_batch, grant_permit

    client, factory = api
    source = approved_source(factory)
    city = fixture_id("city")
    grant_permit(factory, source, [city], 10, "TEST evidence")
    record = payload()
    batch = create_batch(factory, source, city, "attraction", [record], "evidence-link")
    approve_batch(factory, batch, "TEST review")
    apply_batch(factory, batch)
    with factory() as db:
        pid = db.scalar(select(Place.id).where(Place.source_id == source))
    assert (
        client.get("/api/v1/places/" + pid).json()["data"]["provenance"]["source_url"]
        == record["source_url"]
    )


def test_cross_source_concurrent_names_are_quarantined(api):
    import os
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import pytest
    from sqlalchemy import event

    from app.ingestion import apply_batch, approve_batch, create_batch, grant_permit

    if not os.getenv("ITERATION_HTTP_DATABASE_URL"):
        pytest.skip("PostgreSQL row locks required")
    _, factory = api
    city = fixture_id("city")
    batches = []
    for name in ["TEST concurrent source A", "TEST concurrent source B"]:
        source = approved_source(factory, name)
        grant_permit(factory, source, [city], 10, "TEST shared city")
        batch = create_batch(
            factory,
            source,
            city,
            "attraction",
            [payload(name="TEST concurrent same museum")],
            "same-name",
        )
        approve_batch(factory, batch, "TEST review")
        batches.append(batch)
    barrier = threading.Barrier(2)

    def synchronize_reads(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("SELECT places.id") and "normalized_name" in statement:
            try:
                barrier.wait(timeout=1)
            except threading.BrokenBarrierError:
                pass

    engine = factory.kw["bind"]
    event.listen(engine, "after_cursor_execute", synchronize_reads)
    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda b: apply_batch(factory, b), batches))
    finally:
        event.remove(engine, "after_cursor_execute", synchronize_reads)
    assert sum(r["applied"] for r in results) == 1 and sum(r["duplicate"] for r in results) == 1
