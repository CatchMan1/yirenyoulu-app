"""Resumable city imports use real transactions and synthetic provider evidence."""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from test_data_adapters import entity

from app import bulk_collection as bulk
from app.http import utcnow
from app.models import CityAlias, CollectionPage, CollectionRun, ImportPermit, Place, SourcePolicy
from app.wikidata_source import reserve_request


def config(**changes):
    value = {
        "run_key": "TEST-city-bulk-001",
        "cities": ["Q90003"],
        "kinds": ["attraction"],
        "per_city_kind_limit": 3,
        "page_size": 2,
        "record_budget": 100,
        "request_budget": 100,
        "interval_seconds": 1,
        "review_reference": "TEST synthetic CC0 rule approval",
    }
    return bulk.BulkConfig.model_validate({**value, **changes})


@pytest.fixture
def provider(monkeypatch):
    events = []
    data = {
        "Q90003": entity(
            "Q90003", "TEST source city", {"P17": [{"id": "Q148"}], "P31": [{"id": "Q515"}]}
        ),
        **{
            q: entity(
                q, "TEST museum " + q, {"P31": [{"id": "Q33506"}], "P131": [{"id": "Q90003"}]}
            )
            for q in ["Q91001", "Q91002", "Q91003"]
        },
    }

    def fetch(sessions, source, ids, transport=None):
        reserve_request(sessions, source)
        events.append(("fetch", tuple(ids)))
        return {qid: data[qid] for qid in ids if qid in data}

    def discover(sessions, source, city, kind, cursor=None, page_size=20, transport=None):
        reserve_request(sessions, source)
        events.append(("discover", cursor))
        ids = ["Q91001", "Q91002", "Q91003"]
        remaining = [v for v in ids if cursor is None or v > cursor]
        selected = remaining[:page_size]
        return SimpleNamespace(
            ids=selected, next_cursor=selected[-1] if len(remaining) > len(selected) else None
        )

    monkeypatch.setattr(bulk, "fetch_entities", fetch)
    monkeypatch.setattr(bulk, "discover_page", discover)
    monkeypatch.setattr(bulk, "time", SimpleNamespace(sleep=lambda _: None))
    return SimpleNamespace(events=events, data=data, fetch=fetch, discover=discover)


def test_run_discovers_pages_and_publishes_without_place_ids(api, provider):
    client, factory = api
    run = bulk.start_run(factory, config())
    result = bulk.execute_run(factory, run, apply=True)
    assert result["status"] == "completed"
    assert result["discovered"] == 3 and result["applied"] == 3 and result["rejected"] == 0
    with factory() as db:
        job = db.get(CollectionRun, run)
        assert (
            db.scalar(
                select(func.count()).select_from(Place).where(Place.source_id == job.source_id)
            )
            == 3
        )
        city = db.scalar(select(CityAlias).where(CityAlias.external_id == "Q90003"))
    assert len(client.get("/api/v1/places", params={"city_id": city.city_id}).json()["data"]) == 3
    before = list(provider.events)
    assert bulk.start_run(factory, config()) == run
    assert bulk.execute_run(factory, run, apply=True)["applied"] == 3
    assert provider.events == before


def test_stage_can_be_applied_later_without_refetching(api, provider):
    _, factory = api
    run = bulk.start_run(factory, config())
    staged = bulk.execute_run(factory, run)
    assert staged["status"] == "staged" and staged["staged"] == 3 and staged["applied"] == 0
    before = list(provider.events)
    result = bulk.execute_run(factory, run, apply=True)
    assert result["status"] == "completed" and result["applied"] == 3
    assert provider.events == before


def test_failed_second_page_resumes_after_committed_checkpoint(api, provider, monkeypatch):
    _, factory = api

    def failing(*args, **kwargs):
        if kwargs.get("cursor") is not None:
            raise ValueError("PROVIDER_UNAVAILABLE")
        return provider.discover(*args, **kwargs)

    monkeypatch.setattr(bulk, "discover_page", failing)
    run = bulk.start_run(factory, config())
    with pytest.raises(ValueError, match="PROVIDER_UNAVAILABLE"):
        bulk.execute_run(factory, run, apply=True)
    report = bulk.get_report(factory, run)
    assert report["status"] == "failed" and report["applied"] == 2
    monkeypatch.setattr(bulk, "discover_page", provider.discover)
    assert bulk.execute_run(factory, run, apply=True)["applied"] == 3
    assert [e for e in provider.events if e == ("discover", None)] == [("discover", None)]


def test_changed_config_cannot_reuse_run_key(api, provider):
    _, factory = api
    bulk.start_run(factory, config())
    with pytest.raises(ValueError, match="CONFIG_CHANGED"):
        bulk.start_run(factory, config(per_city_kind_limit=4))


def test_candidate_limit_does_not_promise_city_completeness(api, provider):
    _, factory = api
    run = bulk.start_run(factory, config(per_city_kind_limit=1))
    result = bulk.execute_run(factory, run, apply=True)
    assert result["applied"] == 1 and result["discovered"] == 1
    assert next(iter(result["progress"].values()))["state"] == "limited"


def test_invalid_city_is_not_registered_with_fabricated_label(api, provider):
    _, factory = api
    provider.data["Q90003"] = entity("Q90003", "TEST other country", {"P17": [{"id": "Q999"}]})
    run = bulk.start_run(factory, config())
    with pytest.raises(ValueError, match="CITY_COUNTRY_UNVERIFIED"):
        bulk.execute_run(factory, run, apply=True)
    with factory() as db:
        assert db.scalar(select(CityAlias).where(CityAlias.external_id == "Q90003")) is None
        permit = db.scalar(select(ImportPermit))
        assert permit.used_requests == 1 and permit.city_ids == []


def test_unproven_candidates_are_reported_without_fake_facts(api, provider):
    _, factory = api
    provider.data["Q91002"]["claims"].pop("P131")
    run = bulk.start_run(factory, config())
    result = bulk.execute_run(factory, run, apply=True)
    assert result["applied"] == 2 and result["rejected"] == 1 and result["discovered"] == 3


def test_run_busy_and_stale_lease_cannot_write_page(api, provider, monkeypatch):
    _, factory = api
    run = bulk.start_run(factory, config())
    with factory.begin() as db:
        row = db.get(CollectionRun, run)
        row.lease_token = "another-process"
        row.lease_until = utcnow() + timedelta(minutes=10)
    with pytest.raises(ValueError, match="RUN_BUSY"):
        bulk.execute_run(factory, run, apply=True)
    with factory.begin() as db:
        db.get(CollectionRun, run).lease_until = utcnow() - timedelta(seconds=1)

    def steal(*args, **kwargs):
        page = provider.discover(*args, **kwargs)
        with factory.begin() as db:
            row = db.get(CollectionRun, run)
            row.lease_token = "replacement"
            row.lease_until = utcnow() + timedelta(minutes=10)
        return page

    monkeypatch.setattr(bulk, "discover_page", steal)
    with pytest.raises(ValueError, match="LEASE_LOST"):
        bulk.execute_run(factory, run, apply=True)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(CollectionPage)) == 0
        assert db.get(CollectionRun, run).lease_token == "replacement"


def test_source_version_change_stops_old_run_before_saving_facts(api, provider, monkeypatch):
    _, factory = api
    run = bulk.start_run(factory, config())

    def change_after_fetch(*args, **kwargs):
        entities = provider.fetch(*args, **kwargs)
        if "Q91001" in args[2]:
            with factory.begin() as db:
                source = db.get(CollectionRun, run).source_id
                db.get(SourcePolicy, source).version += 1
        return entities

    monkeypatch.setattr(bulk, "fetch_entities", change_after_fetch)
    with pytest.raises(ValueError, match="POLICY_CHANGED"):
        bulk.execute_run(factory, run, apply=True)
    assert bulk.get_report(factory, run)["applied"] == 0


def test_record_budget_is_cumulative_across_runs(api, provider):
    from app.ingestion import grant_permit

    _, factory = api
    run = bulk.start_run(factory, config(record_budget=2))
    with pytest.raises(ValueError, match="PERMIT_EXHAUSTED"):
        bulk.execute_run(factory, run, apply=True)
    assert bulk.get_report(factory, run)["applied"] == 2
    with factory() as db:
        job = db.get(CollectionRun, run)
        permit = db.scalar(select(ImportPermit))
        assert permit.used_records == 2
        cities = list(permit.city_ids)
    grant_permit(factory, job.source_id, cities, 10, "TEST expanded budget", max_requests=100)
    assert bulk.execute_run(factory, run, apply=True)["applied"] == 3


def test_purge_clears_collection_payloads_and_prevents_resume(api, provider):
    from app.ingestion import revoke_source

    _, factory = api
    run = bulk.start_run(factory, config())
    bulk.execute_run(factory, run)
    with factory() as db:
        source = db.get(CollectionRun, run).source_id
    revoke_source(factory, source, purge=True)
    with factory() as db:
        assert all(p.records is None for p in db.scalars(select(CollectionPage)))
    with pytest.raises(ValueError):
        bulk.execute_run(factory, run, apply=True)


def test_crash_after_batch_commit_recovers_without_extra_budget(api, provider, monkeypatch):
    from app import ingestion

    _, factory = api
    original = ingestion.create_batch
    fail_once = [True]

    def committed_then_lost(*args, **kwargs):
        result = original(*args, **kwargs)
        if fail_once.pop() if fail_once else False:
            raise ValueError("SIMULATED_COMMIT_LOSS")
        return result

    monkeypatch.setattr(ingestion, "create_batch", committed_then_lost)
    run = bulk.start_run(factory, config())
    with pytest.raises(ValueError, match="SIMULATED_COMMIT_LOSS"):
        bulk.execute_run(factory, run, apply=True)
    assert bulk.execute_run(factory, run, apply=True)["applied"] == 3
    with factory() as db:
        assert db.scalar(select(ImportPermit)).used_records == 3


def test_ctrl_c_releases_lease_and_resumes_checkpoint(api, provider, monkeypatch):
    _, factory = api

    def interrupted(*args, **kwargs):
        if kwargs.get("cursor") is not None:
            raise KeyboardInterrupt
        return provider.discover(*args, **kwargs)

    monkeypatch.setattr(bulk, "discover_page", interrupted)
    run = bulk.start_run(factory, config())
    with pytest.raises(KeyboardInterrupt):
        bulk.execute_run(factory, run, apply=True)
    assert bulk.get_report(factory, run)["status"] == "paused"
    with factory() as db:
        assert db.get(CollectionRun, run).lease_token is None
    monkeypatch.setattr(bulk, "discover_page", provider.discover)
    assert bulk.execute_run(factory, run, apply=True)["applied"] == 3


def test_new_run_updates_existing_places_and_preserves_identity(api, provider):
    _, factory = api
    first = bulk.start_run(factory, config())
    assert bulk.execute_run(factory, first, apply=True)["inserted"] == 3
    with factory() as db:
        source = db.get(CollectionRun, first).source_id
        before = set(db.scalars(select(Place.id).where(Place.source_id == source)))
    second = bulk.start_run(factory, config(run_key="TEST-city-bulk-002"))
    result = bulk.execute_run(factory, second, apply=True)
    assert result["updated"] == 3 and result["inserted"] == 0
    with factory() as db:
        assert set(db.scalars(select(Place.id).where(Place.source_id == source))) == before
        assert db.scalar(select(ImportPermit)).used_records == 6


def test_oversized_retry_header_has_stable_safe_error(api):
    import httpx
    from test_ingestion import approved_source

    from app.ingestion import grant_permit
    from app.seed import fixture_id
    from app.wikidata_source import fetch_entities

    _, factory = api
    source = approved_source(factory)
    grant_permit(factory, source, [fixture_id("city")], 10, "TEST request budget")
    with pytest.raises(ValueError, match="PROVIDER_RETRY_LATER"):
        fetch_entities(
            factory,
            source,
            ["Q91001"],
            transport=httpx.MockTransport(
                lambda _: httpx.Response(429, headers={"Retry-After": "9" * 5000})
            ),
        )


def test_chinese_non_city_entity_cannot_be_registered_as_city(api, provider):
    _, factory = api
    provider.data["Q90003"] = entity(
        "Q90003", "TEST palace", {"P17": [{"id": "Q148"}], "P31": [{"id": "Q16560"}]}
    )
    run = bulk.start_run(factory, config())
    with pytest.raises(ValueError, match="CITY_TYPE_UNVERIFIED"):
        bulk.execute_run(factory, run, apply=True)
    with factory() as db:
        assert db.scalar(select(CityAlias).where(CityAlias.external_id == "Q90003")) is None


def test_city_subclass_evidence_is_resolved_before_registration(api, provider):
    _, factory = api
    provider.data["Q90003"]["claims"]["P31"] = entity("Q1", "TEST", {"P31": [{"id": "Q90044"}]})[
        "claims"
    ]["P31"]
    provider.data["Q90044"] = entity("Q90044", "TEST city type", {"P279": [{"id": "Q515"}]})
    run = bulk.start_run(factory, config())
    assert bulk.execute_run(factory, run, apply=True)["applied"] == 3


def test_lease_lost_after_approval_cannot_publish_places(api, provider, monkeypatch):
    from app import ingestion

    _, factory = api
    run = bulk.start_run(factory, config())
    original = ingestion.approve_batch

    def approve_then_replace(*args, **kwargs):
        original(*args, **kwargs)
        with factory.begin() as db:
            job = db.get(CollectionRun, run)
            job.lease_token = "replacement-worker"
            job.lease_until = utcnow() + timedelta(minutes=10)

    monkeypatch.setattr(ingestion, "approve_batch", approve_then_replace)
    with pytest.raises(ValueError, match="LEASE_LOST"):
        bulk.execute_run(factory, run, apply=True)
    with factory() as db:
        job = db.get(CollectionRun, run)
        assert job.lease_token == "replacement-worker"
        assert (
            db.scalar(
                select(func.count()).select_from(Place).where(Place.source_id == job.source_id)
            )
            == 0
        )


def test_postgres_two_workers_cannot_collect_same_run(api, provider, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    _, factory = api
    with factory() as db:
        if db.bind.dialect.name != "postgresql":
            pytest.skip("PostgreSQL locking evidence requires the isolated HTTP test database")
    run = bulk.start_run(factory, config())
    entered, release = Event(), Event()

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(10), "test worker did not release provider"
        return provider.discover(*args, **kwargs)

    monkeypatch.setattr(bulk, "discover_page", blocked)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(bulk.execute_run, factory, run, True)
        try:
            assert entered.wait(10), "first worker did not reach provider"
            with pytest.raises(ValueError, match="RUN_BUSY"):
                bulk.execute_run(factory, run, apply=True)
        finally:
            release.set()
        assert first.result(timeout=10)["inserted"] == 3
    assert [e for e in provider.events if e == ("discover", None)] == [("discover", None)]
