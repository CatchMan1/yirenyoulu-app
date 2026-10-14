"""Observable HTTP behavior; SQLite is fast-test coverage, not locking evidence."""

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, BehaviorEvent, Favorite, User
from app.seed import fixture_id, seed_fixtures
from app.settings import Settings


@pytest.fixture
def api():
    settings = Settings(
        app_env="test",
        database_url="postgresql+psycopg://fixture@localhost/yirenyoulu_test",
        jwt_secret=uuid4().hex * 2,
    )
    pg_url = os.getenv("ITERATION_HTTP_DATABASE_URL")
    if pg_url:
        Settings(app_env="test", database_url=pg_url)
        engine = create_engine(pg_url, hide_parameters=True)
        with engine.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())
    else:
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        seed_fixtures(db, settings)
    from app.api import create_app

    app = create_app(settings, factory)
    with TestClient(app, raise_server_exceptions=False) as client:
        from wire_contract import check_response

        client.event_hooks["response"].append(lambda response: check_response(app, response))
        yield client, factory
    if pg_url:
        with engine.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())
    engine.dispose()


def register(client, name="alice"):
    response = client.post(
        "/api/v1/auth/register",
        json={"username": name, "email": name + "@example.com", "password": "TestOnly!Password12"},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def login(client, name="alice"):
    response = client.post(
        "/api/v1/auth/login", json={"identifier": name, "password": "TestOnly!Password12"}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["tokens"]


def auth(tokens):
    return {"Authorization": "Bearer " + tokens["access_token"]}


def test_register_commits_hash_and_never_returns_password(api):
    client, factory = api
    user = register(client)
    assert user["username"] == "alice" and user["email_verified"] is False
    assert "password" not in str(user)
    with factory() as db:
        assert db.get(User, user["id"]).password_hash.startswith("$argon2id$")
    duplicate = client.post(
        "/api/v1/auth/register",
        json={"username": "ALICE", "email": "other@example.com", "password": "TestOnly!Password12"},
    )
    assert duplicate.status_code == 409


def test_unknown_input_error_is_redacted(api):
    client, _ = api
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "bob",
            "email": "bob@example.com",
            "password": "DoNotEcho!123456",
            "is_admin": True,
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert "DoNotEcho" not in response.text
    assert body["error"]["details"] == [{"path": "body.is_admin", "code": "UNKNOWN_FIELD"}]
    assert response.headers["x-request-id"] == body["request_id"]


def test_refresh_rotation_and_old_replay_revoke_current_session(api):
    client, _ = api
    register(client)
    first = login(client)
    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert rotated.status_code == 200
    second = rotated.json()["data"]
    assert second["refresh_token"] != first["refresh_token"]
    assert client.get("/api/v1/me", headers=auth(second)).status_code == 200
    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
        ).status_code
        == 401
    )
    assert client.get("/api/v1/me", headers=auth(second)).status_code == 401


def test_logout_and_wrong_password_do_not_refresh(api):
    client, _ = api
    register(client)
    tokens = login(client)
    wrong = client.post(
        "/api/v1/me/password",
        json={"current_password": "wrong", "new_password": "Different!Password12"},
        headers=auth(tokens),
    )
    assert wrong.status_code == 401 and wrong.json()["error"]["code"] == "CURRENT_PASSWORD_INVALID"
    assert client.get("/api/v1/me", headers=auth(tokens)).status_code == 200
    response = client.post("/api/v1/auth/logout", headers=auth(tokens))
    assert response.status_code == 204 and response.content == b""
    assert client.get("/api/v1/me", headers=auth(tokens)).status_code == 401


def test_catalog_unknown_price_filter_and_pagination(api):
    client, _ = api
    response = client.get("/api/v1/places", params={"page_size": 2})
    assert response.status_code == 200
    assert len(response.json()["data"]) == 2
    assert response.json()["meta"] == {"page": 1, "page_size": 2, "total": 9, "has_more": True}
    assert response.json()["data"][0]["coordinates"] is None
    assert client.get("/api/v1/places", params={"price_max_minor": 100}).status_code == 422
    filtered = client.get("/api/v1/places", params={"price_max_minor": 100, "price_unit": "entry"})
    assert filtered.status_code == 200 and filtered.json()["data"] == []
    assert client.get("/api/v1/places", params={"page_size": True}).status_code == 422
    assert client.get("/api/v1/places?page=1&page=2").status_code == 422
    assert client.get("/api/v1/places?user_id=oops").status_code == 422


def test_favorites_are_private_and_idempotent(api):
    client, factory = api
    register(client)
    alice = login(client)
    register(client, "bob")
    bob = login(client, "bob")
    place = fixture_id("fixture-attraction-1")
    for _ in range(2):
        assert client.put("/api/v1/favorites/" + place, headers=auth(alice)).status_code == 204
    assert len(client.get("/api/v1/favorites", headers=auth(alice)).json()["data"]) == 1
    assert client.get("/api/v1/favorites", headers=auth(bob)).json()["data"] == []
    with factory() as db:
        assert len(db.scalars(select(Favorite)).all()) == 1
        assert len(db.scalars(select(BehaviorEvent)).all()) == 1
    assert client.delete("/api/v1/favorites/" + place, headers=auth(bob)).status_code == 204
    assert len(client.get("/api/v1/favorites", headers=auth(alice)).json()["data"]) == 1


def test_disabled_email_is_honest_and_navigation_degrades(api):
    client, _ = api
    response = client.post(
        "/api/v1/auth/password-reset/request", json={"email": "absent@example.com"}
    )
    assert response.status_code == 503
    place = fixture_id("fixture-attraction-1")
    response = client.get("/api/v1/places/" + place + "/navigation")
    assert response.status_code == 200
    assert response.json()["data"]["reason"] == "NO_COORDINATES"


def test_invalid_optional_identity_is_not_anonymous(api):
    client, _ = api
    assert (
        client.get(
            "/api/v1/recommendations", headers={"Authorization": "Bearer invalid"}
        ).status_code
        == 401
    )
