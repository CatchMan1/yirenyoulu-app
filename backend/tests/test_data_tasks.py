"""Import and background-task integrity, plus bounded collection resume."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.http import utcnow
from app.models import DataSource, PlanningJob, Trip
from support import auth, fixture_id, login, register


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


def test_planning_is_persistent_and_worker_saves_once(api):
    client, factory = api
    register(client)
    tokens = login(client)
    client.app.state.settings.ai_provider = "mock"
    key = str(uuid4())
    body = {"city_id": fixture_id("city"), "start_date": "2027-01-01", "end_date": "2027-01-02"}
    response = client.post(
        "/api/v1/planning-jobs", json=body, headers={**auth(tokens), "Idempotency-Key": key}
    )
    assert response.status_code == 202, response.text
    jid = response.json()["data"]["id"]
    assert response.json()["data"]["trip_id"] is None
    from app.planning import run_once

    assert run_once(client.app.state.settings, factory) is True
    assert run_once(client.app.state.settings, factory) is False
    result = client.get("/api/v1/planning-jobs/" + jid, headers=auth(tokens)).json()["data"]
    assert result["status"] == "succeeded" and result["trip_id"]
    assert (
        client.post(
            "/api/v1/planning-jobs", json=body, headers={**auth(tokens), "Idempotency-Key": key}
        ).json()["data"]["id"]
        == jid
    )
    with factory() as db:
        assert len(db.scalars(select(Trip)).all()) == 1
    assert (
        client.delete(
            "/api/v1/trips/" + result["trip_id"], params={"version": 1}, headers=auth(tokens)
        ).status_code
        == 204
    )
    assert (
        client.get("/api/v1/planning-jobs/" + jid, headers=auth(tokens)).json()["data"][
            "result_deleted"
        ]
        is True
    )


def test_chat_history_context_idempotency_and_owner_isolation(api):
    client, factory = api
    register(client)
    alice = login(client)
    register(client, "bob")
    bob = login(client, "bob")
    client.app.state.settings.ai_provider = "mock"
    created = client.post("/api/v1/chat-sessions", json={}, headers=auth(alice))
    assert created.status_code == 201, created.text
    sid = created.json()["data"]["id"]
    path = "/api/v1/chat-sessions/" + sid + "/messages"
    assert client.get(path, headers=auth(bob)).status_code == 404
    mid = str(uuid4())
    body = {"message_id": mid, "content": "记住暗号：向日葵"}
    first = client.post(path, json=body, headers=auth(alice))
    assert first.status_code == 201, first.text
    again = client.post(path, json=body, headers=auth(alice))
    assert (
        again.status_code == 201
        and again.json()["data"]["assistant_message"]["id"]
        == first.json()["data"]["assistant_message"]["id"]
    )
    assert (
        client.post(path, json={**body, "content": "changed"}, headers=auth(alice)).status_code
        == 409
    )
    second = client.post(
        path, json={"message_id": str(uuid4()), "content": "之前的暗号是什么"}, headers=auth(alice)
    )
    assert second.status_code == 201
    assert "向日葵" in second.json()["data"]["assistant_message"]["content"]
    history = client.get(path, headers=auth(alice)).json()
    assert len(history["data"]) == 4 and history["meta"]["has_more"] is False


def test_expired_worker_lease_cannot_commit_even_before_reclaim(api):
    client, factory = api
    register(client)
    tokens = login(client)
    client.app.state.settings.ai_provider = "mock"
    body = {"city_id": fixture_id("city"), "start_date": "2027-01-01", "end_date": "2027-01-02"}
    jid = client.post(
        "/api/v1/planning-jobs",
        json=body,
        headers={**auth(tokens), "Idempotency-Key": str(uuid4())},
    ).json()["data"]["id"]
    from app.planning import CatalogTools, FakePlanner, claim, finish

    info = claim(factory)
    output = FakePlanner().plan(info[3], CatalogTools(factory, body["city_id"], []))
    with factory.begin() as db:
        db.get(PlanningJob, jid).lease_until = utcnow() - timedelta(seconds=1)
    assert finish(factory, info, output=output) is False
    with factory() as db:
        assert db.scalars(select(Trip)).all() == []


def test_saturated_tile_reports_incomplete_then_resumes_next_page(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace

    import overture_expansion as expansion
    from collect_overture import RELEASE
    from collect_overture_batch import completed

    cfg = {"qid": "Q100", "names": ["TEST City"], "bounds": [116.4, 39.9, 116.41, 39.91]}
    sources = [
        {"url": "https://example.test/part-00015-test.parquet", "bounds": [104, 18, 180, 77]}
    ]
    args = SimpleNamespace(tile_km=20, max_pages_per_tile=1, output_dir=tmp_path, apply=True)
    calls = []
    imports = []
    monkeypatch.setattr(expansion.time, "sleep", lambda seconds: None)

    def download(cfg, path, url, *, query_bounds, after):
        calls.append(after)
        ids = [f"{i:05}" for i in range(2000)] if after is None else ["02000"]
        path.write_text(
            json.dumps(
                {
                    "release": RELEASE,
                    "city": cfg,
                    "source_url": url,
                    "query_bounds": query_bounds,
                    "after": after,
                    "records": [{"id": i} for i in ids],
                }
            )
        )

    def apply(path, catalog, args):
        imports.append(path.name)
        return True

    failed, limited = expansion.collect_region(
        cfg, sources, args, tmp_path / "cities.json", download, completed, apply
    )
    assert failed == [] and limited
    args.max_pages_per_tile = 2
    assert expansion.collect_region(
        cfg, sources, args, tmp_path / "cities.json", download, completed, apply
    ) == ([], [])
    assert calls == [None, "01999"]
    assert len(imports) == 3  # Cached pages still receive idempotent import.


def test_run_download_guard_stops_before_network(tmp_path):
    from types import SimpleNamespace

    from overture_expansion import collect_region

    cfg = {"qid": "Q100", "names": ["TEST City"], "bounds": [116.4, 39.9, 116.41, 39.91]}
    sources = [
        {"url": "https://example.test/part-00015-test.parquet", "bounds": [104, 18, 180, 77]}
    ]
    args = SimpleNamespace(
        tile_km=20,
        max_pages_per_tile=10,
        output_dir=tmp_path,
        apply=False,
        new_pages=1,
        max_new_pages=1,
    )
    failed, limited = collect_region(
        cfg,
        sources,
        args,
        tmp_path / "cities.json",
        lambda *a, **kw: pytest.fail("Download guard must run before collection"),
        lambda *a: False,
        lambda *a: True,
    )
    assert failed == [] and limited
