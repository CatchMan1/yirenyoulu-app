"""Owner isolation, durable idempotency and transactional trip changes."""

from uuid import uuid4

from sqlalchemy import select

from app.models import Trip, TripItem
from support import auth, fixture_id, login, register


def create(client, tokens, key=None, **changes):
    body = {
        "title": "【测试】两日行程",
        "city_id": fixture_id("city"),
        "start_date": "2027-01-01",
        "end_date": "2027-01-02",
    }
    body.update(changes)
    return client.post(
        "/api/v1/trips", json=body, headers={**auth(tokens), "Idempotency-Key": key or str(uuid4())}
    )


def test_creation_is_durable_idempotent_and_owner_scoped(api):
    client, factory = api
    register(client)
    alice = login(client)
    register(client, "bob")
    bob = login(client, "bob")
    key = str(uuid4())
    first = create(client, alice, key)
    assert first.status_code == 201, first.text
    trip = first.json()["data"]
    assert trip["preferences"] == {"tags": [], "pace": "normal"}
    assert create(client, alice, key).json()["data"]["id"] == trip["id"]
    assert create(client, alice, key, title="different").status_code == 409
    assert client.get("/api/v1/trips/" + trip["id"], headers=auth(bob)).status_code == 404
    assert (
        client.delete(
            "/api/v1/trips/" + trip["id"], params={"version": 1}, headers=auth(alice)
        ).status_code
        == 204
    )
    assert create(client, alice, key).status_code == 410
    with factory() as db:
        assert db.scalars(select(Trip)).all() == []


def test_invalid_schedule_rolls_back_and_wrong_child_is_not_found(api):
    client, factory = api
    register(client)
    tokens = login(client)
    first = create(client, tokens)
    assert first.status_code == 201, first.text
    tid = first.json()["data"]["id"]
    path = "/api/v1/trips/" + tid + "/items"
    payload = {
        "version": 1,
        "place_id": fixture_id("fixture-attraction-1"),
        "date": "2027-01-01",
        "start_minute": 600,
        "end_minute": 660,
    }
    response = client.post(path, json=payload, headers=auth(tokens))
    assert response.status_code == 201, response.text
    item = response.json()["data"]["items"][0]["id"]
    other = create(client, tokens).json()["data"]["id"]
    assert (
        client.delete(
            "/api/v1/trips/" + other + "/items/" + item, params={"version": 1}, headers=auth(tokens)
        ).status_code
        == 404
    )
    payload.update(
        version=2, place_id=fixture_id("fixture-attraction-2"), start_minute=630, end_minute=700
    )
    assert client.post(path, json=payload, headers=auth(tokens)).status_code == 422
    with factory() as db:
        assert len(db.scalars(select(TripItem).where(TripItem.trip_id == tid)).all()) == 1
        assert db.get(Trip, tid).version == 2


def test_commit_failure_never_returns_created_or_keeps_partial_state(api):
    from sqlalchemy import event, select
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import Session

    from app.models import BehaviorEvent, IdempotencyRecord, Trip

    client, factory = api
    register(client)
    tokens = login(client)

    def reject_trip_flush(session, flush_context, instances):
        if any(isinstance(row, Trip) for row in session.new):
            raise OperationalError(None, None, RuntimeError("simulated commit storage failure"))

    event.listen(Session, "before_flush", reject_trip_flush)
    try:
        response = client.post(
            "/api/v1/trips",
            json={
                "title": "【测试】失败保存",
                "city_id": fixture_id("city"),
                "start_date": "2027-01-01",
                "end_date": "2027-01-02",
            },
            headers={**auth(tokens), "Idempotency-Key": str(uuid4())},
        )
    finally:
        event.remove(Session, "before_flush", reject_trip_flush)
    assert (
        response.status_code == 503 and response.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"
    )
    assert "storage failure" not in response.text
    with factory() as db:
        for model in (Trip, IdempotencyRecord, BehaviorEvent):
            assert db.scalars(select(model)).all() == []


def test_known_fact_over_budget_rolls_back_item_version_and_behavior(api):
    from app.models import BehaviorEvent, Place

    client, factory = api
    register(client)
    tokens = login(client)
    place_id = fixture_id("fixture-attraction-1")
    # Synthetic fact exists only in the isolated fixture transaction, never a real price.
    with factory.begin() as db:
        place = db.get(Place, place_id)
        place.price_minor = 200
        place.price_unit = "entry"
    trip = client.post(
        "/api/v1/trips",
        json={
            "title": "【测试】预算边界",
            "city_id": fixture_id("city"),
            "start_date": "2027-01-01",
            "end_date": "2027-01-02",
            "budget_minor": 100,
        },
        headers={**auth(tokens), "Idempotency-Key": str(uuid4())},
    ).json()["data"]
    response = client.post(
        "/api/v1/trips/" + trip["id"] + "/items",
        json={
            "version": 1,
            "place_id": place_id,
            "date": "2027-01-01",
            "start_minute": 600,
            "end_minute": 660,
        },
        headers=auth(tokens),
    )
    assert response.status_code == 422 and response.json()["error"]["code"] == "BUDGET_EXCEEDED"
    unchanged = client.get("/api/v1/trips/" + trip["id"], headers=auth(tokens)).json()["data"]
    assert unchanged["version"] == 1 and unchanged["items"] == []
    with factory() as db:
        assert db.scalars(select(BehaviorEvent)).all() == []
