"""Actual PostgreSQL row-lock races; never infer locking from SQLite."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import IdempotencyRecord, Trip
from app.seed import fixture_id
from test_api_accounts_catalog import auth, login, register

pytestmark = pytest.mark.skipif(
    not os.getenv("ITERATION_HTTP_DATABASE_URL"),
    reason="Dedicated migrated PostgreSQL HTTP database required",
)


def test_concurrent_create_key_commits_only_one_trip(api):
    client, factory = api
    register(client)
    tokens = login(client)
    body = {
        "title": "【测试】并发保存",
        "city_id": fixture_id("city"),
        "start_date": "2027-01-01",
        "end_date": "2027-01-02",
    }
    headers = {**auth(tokens), "Idempotency-Key": str(uuid4())}
    barrier = Barrier(2)

    def create():
        barrier.wait(timeout=5)
        return client.post("/api/v1/trips", json=body, headers=headers)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: create(), range(2)))
    assert [r.status_code for r in responses] == [201, 201]
    assert responses[0].json()["data"]["id"] == responses[1].json()["data"]["id"]
    with factory() as db:
        assert len(db.scalars(select(Trip)).all()) == 1
        assert len(db.scalars(select(IdempotencyRecord)).all()) == 1


def test_concurrent_refresh_replay_revokes_winner(api):
    client, _ = api
    register(client)
    tokens = login(client)
    barrier = Barrier(2)

    def refresh():
        barrier.wait(timeout=5)
        return client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: refresh(), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 401]
    winner = next(r.json()["data"] for r in responses if r.status_code == 200)
    assert client.get("/api/v1/me", headers=auth(winner)).status_code == 401
