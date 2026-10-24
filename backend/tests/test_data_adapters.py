"""Provider contracts use visibly synthetic entities, not real travel facts."""

import pytest


def entity(qid, label, claims):
    return {
        "id": qid,
        "labels": {"zh": {"value": label}},
        "claims": {
            key: [
                {
                    "rank": "normal",
                    "mainsnak": {
                        "snaktype": "value",
                        "datavalue": {
                            "value": (
                                {"entity-type": "item", "numeric-id": int(v["id"][1:]), **v}
                                if isinstance(v, dict) and "id" in v
                                else v
                            )
                        },
                    },
                }
                for v in values
            ]
            for key, values in claims.items()
        },
    }


def test_wikidata_uses_explicit_types_and_verified_city_chain():
    from app.data_adapters import wikidata_record

    entities = {
        "Q90001": entity(
            "Q90001",
            "TEST museum",
            {
                "P31": [{"id": "Q33506"}],
                "P131": [{"id": "Q90002"}],
                "P625": [
                    {
                        "latitude": 1.0,
                        "longitude": 2.0,
                        "globe": "http://www.wikidata.org/entity/Q2",
                    }
                ],
            },
        ),
        "Q90002": entity("Q90002", "TEST district", {"P131": [{"id": "Q90003"}]}),
        "Q90003": entity("Q90003", "TEST city", {"P17": [{"id": "Q148"}]}),
    }
    result = wikidata_record(entities, "Q90001", "Q90003")
    assert result["name"] == "TEST museum" and result["kind"] == "attraction"
    assert result["coordinates"]["crs"] == "WGS84" and "price_minor" not in result
    assert result["evidence"]["city_chain"] == ["Q90002", "Q90003"]
    entities["Q90001"]["claims"]["P31"] = entities["Q90001"]["claims"]["P131"]
    with pytest.raises(ValueError, match="TYPE_NOT_SUPPORTED"):
        wikidata_record(entities, "Q90001", "Q90003")


def test_wikidata_missing_city_or_non_earth_coordinates_is_not_invented():
    from app.data_adapters import wikidata_record

    data = {
        "Q90001": entity(
            "Q90001", "TEST restaurant", {"P31": [{"id": "Q11707"}], "P159": [{"id": "Q90003"}]}
        ),
        "Q90003": entity("Q90003", "TEST city", {"P17": [{"id": "Q148"}]}),
    }
    with pytest.raises(ValueError, match="CITY_EVIDENCE_MISSING"):
        wikidata_record(data, "Q90001", "Q90003")
    data["Q90001"]["claims"]["P131"] = data["Q90001"]["claims"]["P159"]
    data["Q90001"]["claims"]["P625"] = [
        {
            "rank": "normal",
            "mainsnak": {
                "snaktype": "value",
                "datavalue": {
                    "value": {
                        "latitude": 1.0,
                        "longitude": 2.0,
                        "globe": "http://www.wikidata.org/entity/Q111",
                    }
                },
            },
        }
    ]
    assert wikidata_record(data, "Q90001", "Q90003")["coordinates"] is None


def test_osm_requires_source_city_evidence_and_never_parses_prices():
    from app.data_adapters import osm_record

    value = {
        "type": "node",
        "id": 1,
        "lat": 1.0,
        "lon": 2.0,
        "tags": {
            "name": "TEST cafe",
            "addr:city": "TEST city",
            "amenity": "cafe",
            "charge": "cheap",
        },
    }
    result = osm_record(value, "TEST city")
    assert (
        result["kind"] == "restaurant"
        and result["external_id"] == "node/1"
        and "price_minor" not in result
    )
    with pytest.raises(ValueError, match="CITY_EVIDENCE_MISSING"):
        osm_record(value, "other city")


def test_fetch_checks_permit_before_network_and_budgets_retries(api):
    import httpx
    from test_ingestion import approved_source

    from app.ingestion import grant_permit
    from app.models import ImportPermit
    from app.seed import fixture_id
    from app.wikidata_source import fetch_entities

    _, factory = api
    sid = approved_source(factory)
    calls = []

    def respond(request):
        calls.append(request)
        return (
            httpx.Response(429, headers={"Retry-After": "0"})
            if len(calls) == 1
            else httpx.Response(200, json={"entities": {"Q90001": {"id": "Q90001"}}})
        )

    transport = httpx.MockTransport(respond)
    with pytest.raises(ValueError, match="PERMIT"):
        fetch_entities(factory, sid, ["Q90001"], transport=transport)
    assert calls == []
    grant_permit(factory, sid, [fixture_id("city")], 10, "TEST permit")
    assert fetch_entities(factory, sid, ["Q90001"], transport=transport)["Q90001"]["id"] == "Q90001"
    assert len(calls) == 2 and calls[0].url.host == "www.wikidata.org"
    with factory() as db:
        from sqlalchemy import select

        permit = db.scalar(select(ImportPermit).where(ImportPermit.source_id == sid))
        assert permit.used_requests == 2


def test_fetch_rejects_arbitrary_ids_and_redirects(api):
    import httpx
    from test_ingestion import approved_source

    from app.ingestion import grant_permit
    from app.seed import fixture_id
    from app.wikidata_source import fetch_entities

    _, factory = api
    sid = approved_source(factory)
    grant_permit(factory, sid, [fixture_id("city")], 10, "TEST permit")
    with pytest.raises(ValueError, match="INVALID_ENTITY_ID"):
        fetch_entities(factory, sid, ["https://private.invalid"])
    with pytest.raises(ValueError, match="PROVIDER_HTTP_302"):
        fetch_entities(
            factory,
            sid,
            ["Q90001"],
            transport=httpx.MockTransport(
                lambda req: httpx.Response(302, headers={"Location": "http://127.0.0.1/"})
            ),
        )


@pytest.mark.parametrize(
    "property_id,value",
    [
        ("P582", "+2000-00-00T00:00:00Z"),
        ("P582", "+2000-05-00T00:00:00Z"),
        ("P580", "+2999-00-00T00:00:00Z"),
        ("P580", "+2999-05-00T00:00:00Z"),
    ],
)
def test_wikidata_uncertain_temporal_qualifiers_are_not_ignored(property_id, value):
    from app.data_adapters import claims

    item = entity("Q90001", "TEST dated claim", {"P131": [{"id": "Q90002"}]})
    item["claims"]["P131"][0]["qualifiers"] = {
        property_id: [
            {"snaktype": "value", "datavalue": {"value": {"time": value, "precision": 9}}}
        ]
    }
    assert claims(item, "P131") == []
