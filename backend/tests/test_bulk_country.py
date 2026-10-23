"""Country runs reuse transactional city jobs; fixtures are synthetic evidence."""

import importlib
import importlib.util

import httpx
import pytest
from sqlalchemy import func, select
from test_bulk_collection import config
from test_bulk_collection import provider as provider

from app import bulk_collection as bulk
from app import wikidata_discovery as discovery
from app.models import CollectionRun, ImportPermit

__all__ = ["provider"]


def country():
    assert importlib.util.find_spec("app.bulk_country") is not None, "country runner missing"
    return importlib.import_module("app.bulk_country")


def test_city_discovery_is_fixed_scoped_and_budgeted(api, provider):
    _, factory = api
    run = bulk.start_run(factory, config())
    with factory() as db:
        source = db.get(CollectionRun, run).source_id

    def respond(request):
        query = request.url.params["query"]
        assert "wd:Q148" in query and "wd:Q515" in query
        assert "wd:Q8646" in query and "wd:Q14773" in query
        assert "LIMIT 3" in query
        return httpx.Response(
            200,
            json={
                "head": {"vars": ["item"]},
                "results": {
                    "bindings": [
                        {"item": {"type": "uri", "value": "http://www.wikidata.org/entity/" + v}}
                        for v in ["Q100", "Q101", "Q102"]
                    ]
                },
            },
        )

    fn = getattr(discovery, "discover_cities", None)
    assert callable(fn), "city discovery missing"
    page = fn(factory, source, page_size=2, transport=httpx.MockTransport(respond))
    assert page.ids == ["Q100", "Q101"] and page.next_cursor == "Q101"
    with factory() as db:
        assert db.scalar(select(ImportPermit)).used_requests == 1


def test_country_replay_does_not_fetch_or_duplicate(api, provider):
    mod = country()
    _, factory = api
    cfg = mod.CountryConfig.model_validate(config().model_dump())
    first = mod.execute_country(factory, cfg, apply=True)
    events = list(provider.events)
    second = mod.execute_country(factory, cfg, apply=True)
    assert first["inserted"] == second["inserted"] == 3
    assert first["status"] == second["status"] == "completed"
    assert provider.events == events


def test_country_config_change_fails_before_new_city_write(api, provider):
    mod = country()
    _, factory = api
    cfg = mod.CountryConfig.model_validate(config().model_dump())
    mod.execute_country(factory, cfg, apply=True)
    changed = cfg.model_copy(update={"cities": ["Q90004", "Q90003"]})
    before = list(provider.events)
    with pytest.raises(ValueError, match="CONFIG_CHANGED"):
        mod.execute_country(factory, changed, apply=True)
    assert provider.events == before
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(CollectionRun)) == 1


def test_bad_city_is_reported_and_other_city_is_processed(api, provider):
    mod = country()
    _, factory = api
    cfg = mod.CountryConfig.model_validate(
        {**config().model_dump(), "cities": ["Q90004", "Q90003"]}
    )
    result = mod.execute_country(factory, cfg, apply=True)
    assert result["status"] == "partial" and result["failed_cities"] == 1
    assert result["inserted"] == 3 and result["completed_cities"] == 1


def test_request_budget_failure_stops_campaign(api, provider):
    mod = country()
    _, factory = api
    cfg = mod.CountryConfig.model_validate(
        {**config().model_dump(), "cities": ["Q90003", "Q90004"], "request_budget": 1}
    )
    with pytest.raises(ValueError, match="REQUEST_BUDGET_EXHAUSTED"):
        mod.execute_country(factory, cfg, apply=True)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(CollectionRun)) == 1


def test_country_default_only_stages(api, provider):
    mod = country()
    _, factory = api
    cfg = mod.CountryConfig.model_validate(config().model_dump())
    result = mod.execute_country(factory, cfg)
    assert result["status"] == "staged" and result["staged"] == 3 and result["applied"] == 0


def test_preparation_refuses_overwrite_before_network(api, provider, tmp_path):
    mod = country()
    _, factory = api
    path = tmp_path / "config.json"
    path.write_text("original")
    with pytest.raises(ValueError, match="OUTPUT_EXISTS"):
        mod.prepare_config(factory, path, "TEST-country")
    assert path.read_text() == "original" and provider.events == []


def test_city_missing_label_does_not_block_other_cities(api, provider):
    from test_data_adapters import entity

    mod = country()
    _, factory = api
    provider.data["Q90004"] = entity(
        "Q90004", "TEST city", {"P17": [{"id": "Q148"}], "P31": [{"id": "Q515"}]}
    )
    provider.data["Q90004"]["labels"] = {}
    cfg = mod.CountryConfig.model_validate(
        {**config().model_dump(), "cities": ["Q90004", "Q90003"]}
    )
    result = mod.execute_country(factory, cfg, apply=True)
    assert result["failed_cities"] == 1 and result["inserted"] == 3


def test_prepare_saves_complete_catalog_and_preserves_used_budget(api, monkeypatch, tmp_path):
    from app.wikidata_source import reserve_request

    mod = country()
    _, factory = api
    source = mod._catalog_source(factory)
    reserve_request(factory, source)
    pages = [discovery.DiscoveryPage(["Q100"], "Q100"), discovery.DiscoveryPage(["Q101"], None)]

    def discover(sessions, source_id, **kwargs):
        reserve_request(sessions, source_id)
        return pages.pop(0)

    monkeypatch.setattr(mod, "discover_cities", discover)
    monkeypatch.setattr(
        mod,
        "fetch_entities",
        lambda sessions, source, ids, **kwargs: {q: {"id": q, "claims": {}} for q in ids},
    )
    monkeypatch.setattr(mod.time, "sleep", lambda _: None)
    output = tmp_path / "country.json"
    report = mod.prepare_config(factory, output, "TEST-country")
    cfg = mod.load_config(output)
    assert report["cities"] == 2 and cfg.cities == ["Q100", "Q101"]
    assert cfg.per_city_kind_limit == 10000 and cfg.request_budget == 100000
    with factory() as db:
        assert db.scalar(select(ImportPermit)).used_requests == 3
        assert db.scalar(select(func.count()).select_from(CollectionRun)) == 0


def test_prepare_does_not_renew_expired_permit(api, tmp_path):
    from datetime import timedelta

    from app.http import utcnow

    mod = country()
    _, factory = api
    mod._catalog_source(factory)
    with factory.begin() as db:
        db.scalar(select(ImportPermit)).expires_at = utcnow() - timedelta(seconds=1)
    output = tmp_path / "country.json"
    with pytest.raises(ValueError, match="PERMIT_EXPIRED_REVIEW_REQUIRED"):
        mod.prepare_config(factory, output, "TEST-country")
    assert not output.exists()


def test_failed_catalog_does_not_publish_partial_config(api, monkeypatch, tmp_path):
    mod = country()
    _, factory = api

    def failed(*args, **kwargs):
        raise ValueError("PROVIDER_UNAVAILABLE")

    monkeypatch.setattr(mod, "discover_cities", failed)
    monkeypatch.setattr(mod.time, "sleep", lambda _: None)
    output = tmp_path / "country.json"
    with pytest.raises(ValueError, match="PROVIDER_UNAVAILABLE"):
        mod.prepare_config(factory, output, "TEST-country")
    assert not output.exists()


def test_catalog_drops_nested_cities_and_excluded_region_descendants(api, monkeypatch):
    from test_data_adapters import entity

    mod = country()
    _, factory = api
    data = {
        "Q100": entity("Q100", "TEST parent", {}),
        "Q101": entity("Q101", "TEST child", {"P131": [{"id": "Q100"}]}),
        "Q102": entity("Q102", "TEST excluded", {"P131": [{"id": "Q8646"}]}),
        "Q8646": entity("Q8646", "TEST excluded ancestor", {}),
    }
    monkeypatch.setattr(
        mod,
        "fetch_entities",
        lambda sessions, source, ids, **kwargs: {q: data[q] for q in ids if q in data},
        raising=False,
    )
    fn = getattr(mod, "top_level_cities", None)
    assert callable(fn), "bounded hierarchy filter missing"
    assert fn(factory, "TEST", ["Q100", "Q101", "Q102"]) == ["Q100"]
