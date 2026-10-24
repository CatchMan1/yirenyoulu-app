"""Automatic discovery contracts use synthetic SPARQL bindings only."""

import httpx
import pytest
from sqlalchemy import select
from test_ingestion import approved_source

from app.ingestion import grant_permit
from app.models import ImportPermit
from app.seed import fixture_id


def sparql_response(ids):
    return {
        "head": {"vars": ["item"]},
        "results": {
            "bindings": [
                {"item": {"type": "uri", "value": "http://www.wikidata.org/entity/" + item}}
                for item in ids
            ]
        },
    }


def authorized(factory):
    source = approved_source(factory)
    grant_permit(factory, source, [fixture_id("city")], 100, "TEST discovery permit")
    return source


def test_discovers_typed_city_candidates_with_stable_keyset_pages(api):
    from app.wikidata_discovery import discover_page

    _, factory = api
    source = authorized(factory)
    queries = []

    def respond(request):
        assert request.url == request.url.copy_with(scheme="https", host="query.wikidata.org")
        assert request.url.path == "/sparql"
        assert request.headers["user-agent"].startswith("YirenYoulu")
        query = request.url.params["query"]
        queries.append(query)
        assert "wdt:P131+ wd:Q90003" in query
        assert "wd:Q90003 wdt:P17 wd:Q148" in query
        assert "wd:Q11707" in query and "wd:Q27686" not in query
        assert "LIMIT 3" in query and "OFFSET" not in query
        if len(queries) == 1:
            return httpx.Response(200, json=sparql_response(["Q100", "Q20", "Q3"]))
        assert 'STR(?item) > "http://www.wikidata.org/entity/Q20"' in query
        return httpx.Response(200, json=sparql_response(["Q3"]))

    transport = httpx.MockTransport(respond)
    first = discover_page(factory, source, "Q90003", "restaurant", page_size=2, transport=transport)
    assert first.ids == ["Q100", "Q20"] and first.next_cursor == "Q20"
    second = discover_page(
        factory,
        source,
        "Q90003",
        "restaurant",
        cursor=first.next_cursor,
        page_size=2,
        transport=transport,
    )
    assert second.ids == ["Q3"] and second.next_cursor is None
    with factory() as db:
        permit = db.scalar(select(ImportPermit).where(ImportPermit.source_id == source))
        assert permit.used_requests == 2


def test_empty_and_exact_page_do_not_claim_more_results(api):
    from app.wikidata_discovery import discover_page

    _, factory = api
    source = authorized(factory)
    for ids in [[], ["Q1", "Q2"]]:
        page = discover_page(
            factory,
            source,
            "Q90003",
            "hotel",
            page_size=2,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=sparql_response(ids))
            ),
        )
        assert page.ids == ids and page.next_cursor is None


@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"city_qid": "Q0"}, "INVALID_ENTITY_ID"),
        ({"city_qid": "Q1 } SERVICE <https://private.invalid> {"}, "INVALID_ENTITY_ID"),
        ({"kind": "anything"}, "INVALID_PLACE_KIND"),
        ({"cursor": "Q0"}, "INVALID_ENTITY_ID"),
        ({"cursor": "https://www.wikidata.org/entity/Q1"}, "INVALID_ENTITY_ID"),
        ({"page_size": 0}, "INVALID_PAGE_SIZE"),
        ({"page_size": 21}, "INVALID_PAGE_SIZE"),
        ({"page_size": True}, "INVALID_PAGE_SIZE"),
        ({"page_size": 1.5}, "INVALID_PAGE_SIZE"),
    ],
)
def test_invalid_scope_cannot_consume_network_budget(api, kwargs, code):
    from app.wikidata_discovery import discover_page

    _, factory = api
    source = authorized(factory)
    args = {"city_qid": "Q90003", "kind": "hotel", **kwargs}
    with pytest.raises(ValueError, match="^" + code + "$"):
        discover_page(factory, source, **args)
    with factory() as db:
        permit = db.scalar(select(ImportPermit).where(ImportPermit.source_id == source))
        assert permit.used_requests == 0


def test_discovery_needs_permit_before_network(api):
    from app.wikidata_discovery import discover_page

    _, factory = api
    source = approved_source(factory)
    requests = []
    with pytest.raises(ValueError, match="PERMIT_REQUIRED"):
        discover_page(
            factory,
            source,
            "Q90003",
            "hotel",
            transport=httpx.MockTransport(lambda request: requests.append(request)),
        )
    assert requests == []


def test_discovery_retries_are_budgeted_and_retry_after_is_respected(api):
    from app.wikidata_discovery import discover_page

    _, factory = api
    source = authorized(factory)
    requests = []

    def respond(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json=sparql_response(["Q90001"]))

    page = discover_page(factory, source, "Q90003", "hotel", transport=httpx.MockTransport(respond))
    assert page.ids == ["Q90001"]
    with factory() as db:
        permit = db.scalar(select(ImportPermit).where(ImportPermit.source_id == source))
        assert permit.used_requests == 2
    with factory.begin() as db:
        permit = db.scalar(select(ImportPermit).where(ImportPermit.source_id == source))
        permit.max_requests = 3
    with pytest.raises(ValueError, match="REQUEST_BUDGET_EXHAUSTED"):
        discover_page(
            factory,
            source,
            "Q90003",
            "hotel",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(503, headers={"Retry-After": "0"})
            ),
        )
    with factory() as db:
        permit = db.scalar(select(ImportPermit).where(ImportPermit.source_id == source))
        assert permit.used_requests == 3


@pytest.mark.parametrize("status,retry", [(429, "90"), (503, "bad"), (302, None), (400, None)])
def test_discovery_does_not_follow_redirects_or_retry_unsafe_delays(api, status, retry):
    from app.wikidata_discovery import discover_page

    _, factory = api
    source = authorized(factory)
    expected = "PROVIDER_RETRY_LATER" if status in {429, 503} else "PROVIDER_HTTP_" + str(status)
    with pytest.raises(ValueError, match=expected):
        discover_page(
            factory,
            source,
            "Q90003",
            "hotel",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    status,
                    headers={"Retry-After": retry or "0", "Location": "http://127.0.0.1/"},
                )
            ),
        )
    with factory() as db:
        permit = db.scalar(select(ImportPermit).where(ImportPermit.source_id == source))
        assert permit.used_requests == 1


@pytest.mark.parametrize("ids", [["Q20", "Q100"], ["Q20", "Q20"], ["Q1"], ["Q20"]])
def test_regressing_or_duplicate_provider_cursor_is_not_saved(api, ids):
    from app.wikidata_discovery import discover_page

    _, factory = api
    source = authorized(factory)
    with pytest.raises(ValueError, match="INVALID_DISCOVERY_PAGE"):
        discover_page(
            factory,
            source,
            "Q90003",
            "hotel",
            cursor="Q20",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=sparql_response(ids))
            ),
        )


@pytest.mark.parametrize(
    "document",
    [
        [],
        {"results": {"bindings": []}},
        {"head": {"vars": ["item"]}, "results": {"bindings": {}}},
        {
            "head": {"vars": ["item"]},
            "results": {"bindings": [{"item": {"type": "literal", "value": "Q1"}}]},
        },
        {
            "head": {"vars": ["item"]},
            "results": {
                "bindings": [{"item": {"type": "uri", "value": "https://evil.invalid/Q1"}}]
            },
        },
        {
            "head": {"vars": ["item"]},
            "results": {
                "bindings": [
                    {"item": {"type": "uri", "value": "http://www.wikidata.org/entity/Q0"}}
                ]
            },
        },
    ],
)
def test_malformed_provider_data_cannot_become_candidates(api, document):
    from app.wikidata_discovery import discover_page

    _, factory = api
    source = authorized(factory)
    with pytest.raises(ValueError, match="INVALID_DISCOVERY_PAGE"):
        discover_page(
            factory,
            source,
            "Q90003",
            "hotel",
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=document)),
        )


def test_discovery_limits_rows_and_response_bytes(api):
    from app.wikidata_discovery import discover_page

    _, factory = api
    source = authorized(factory)
    for response, code in [
        (
            httpx.Response(200, json=sparql_response(["Q1", "Q2", "Q3", "Q4"])),
            "INVALID_DISCOVERY_PAGE",
        ),
        (httpx.Response(200, content=b" " * 100_001), "PROVIDER_RESPONSE_TOO_LARGE"),
        (httpx.Response(200, content=b"not json"), "INVALID_DISCOVERY_PAGE"),
    ]:
        with pytest.raises(ValueError, match=code):
            discover_page(
                factory,
                source,
                "Q90003",
                "hotel",
                page_size=2,
                transport=httpx.MockTransport(lambda request: response),
            )


def test_network_failure_has_safe_error_and_consumes_bounded_attempts(api):
    from app.wikidata_discovery import discover_page

    _, factory = api
    source = authorized(factory)

    def fail(request):
        raise httpx.ReadTimeout("TEST upstream internal diagnostic", request=request)

    with pytest.raises(ValueError, match="^PROVIDER_UNAVAILABLE$"):
        discover_page(factory, source, "Q90003", "hotel", transport=httpx.MockTransport(fail))
    with factory() as db:
        permit = db.scalar(select(ImportPermit).where(ImportPermit.source_id == source))
        assert permit.used_requests == 3


def test_retry_after_cannot_force_unbounded_integer_parsing(api):
    from app.wikidata_discovery import discover_page

    _, factory = api
    source = authorized(factory)
    with pytest.raises(ValueError, match="^PROVIDER_RETRY_LATER$"):
        discover_page(
            factory,
            source,
            "Q90003",
            "hotel",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(429, headers={"Retry-After": "9" * 5000})
            ),
        )
