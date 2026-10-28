"""Password storage, token replay, private data and account erasure."""

import pytest
from sqlalchemy import select

from app.models import AuthSession, BehaviorEvent, DataSource, DeletionAudit, Favorite, Place, User
from app.settings import Settings
from support import auth, fixture_id, login, register


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


def test_favorite_status_is_private_and_does_not_create_behavior(api):
    client, factory = api
    register(client)
    alice = login(client)
    register(client, "bob")
    bob = login(client, "bob")
    place = fixture_id("fixture-attraction-1")
    assert client.put("/api/v1/favorites/" + place, headers=auth(alice)).status_code == 204

    for tokens, expected in [(alice, True), (bob, False), (alice, True)]:
        response = client.get("/api/v1/favorites/" + place, headers=auth(tokens))
        assert response.status_code == 200
        assert response.json()["data"] == {"place_id": place, "is_favorited": expected}
        assert response.json()["meta"] is None
        assert response.headers["x-request-id"] == response.json()["request_id"]
        assert response.headers["cache-control"] == "no-store"
    with factory() as db:
        assert len(db.scalars(select(Favorite)).all()) == 1
        assert len(db.scalars(select(BehaviorEvent)).all()) == 1


@pytest.mark.parametrize("unavailable", ["inactive", "source-withdrawn"])
def test_favorite_status_ignores_place_availability(api, unavailable):
    client, factory = api
    register(client)
    tokens = login(client)
    saved = fixture_id("fixture-attraction-1")
    unsaved = fixture_id("fixture-attraction-2")
    assert client.put("/api/v1/favorites/" + saved, headers=auth(tokens)).status_code == 204
    with factory.begin() as db:
        if unavailable == "inactive":
            db.get(Place, saved).status = "inactive"
            db.get(Place, unsaved).status = "inactive"
        else:
            db.get(DataSource, fixture_id("source")).kind = "manual"
    for place, expected in [(saved, True), (unsaved, False), (fixture_id("missing"), False)]:
        response = client.get("/api/v1/favorites/" + place, headers=auth(tokens))
        assert response.status_code == 200
        assert response.json()["data"] == {"place_id": place, "is_favorited": expected}
    with factory() as db:
        assert len(db.scalars(select(BehaviorEvent)).all()) == 1


def test_favorite_status_requires_a_valid_session_and_uuid(api):
    client, _ = api
    register(client)
    tokens = login(client)
    url = "/api/v1/favorites/" + fixture_id("fixture-attraction-1")
    for headers in [{}, {"Authorization": "Bearer invalid"}]:
        response = client.get(url, headers=headers)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "SESSION_INVALID"
    invalid = client.get("/api/v1/favorites/not-a-uuid", headers=auth(tokens))
    assert invalid.status_code == 422
    assert invalid.json()["error"]["details"] == [
        {"path": "path.place_id", "code": "INVALID_FORMAT"}
    ]
    assert client.post("/api/v1/auth/logout", headers=auth(tokens)).status_code == 204
    assert client.get(url, headers=auth(tokens)).status_code == 401


def test_account_delete_cleans_private_data_and_keeps_minimal_audit(api):
    client, factory = api
    user = register(client)
    tokens = login(client)
    response = client.request(
        "DELETE",
        "/api/v1/me",
        json={"current_password": "TestOnly!Password12"},
        headers=auth(tokens),
    )
    assert response.status_code == 204, response.text
    assert client.get("/api/v1/me", headers=auth(tokens)).status_code == 401
    with factory() as db:
        grave = db.get(User, user["id"])
        assert (
            grave.status == "deleted"
            and grave.email != "alice@example.com"
            and grave.nickname == ""
        )
        assert db.scalar(select(DeletionAudit)).subject_id == user["id"]
        assert db.scalars(select(AuthSession)).all() == []


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///travel_app.db",
        "postgresql://localhost/old",
        "postgresql://localhost/yirenyoulu_prod",
    ],
)
def test_test_environment_refuses_nonisolated_database(url):
    with pytest.raises(ValueError):
        Settings(app_env="test", database_url=url)


def test_production_refuses_mock_provider():
    with pytest.raises(ValueError):
        Settings(
            app_env="production",
            database_url="postgresql+psycopg://localhost/yirenyoulu_prod",
            ai_provider="mock",
        )


def test_cors_origins_require_explicit_origins_and_production_https(monkeypatch):
    database_url = "postgresql+psycopg://fixture@localhost/yirenyoulu_test"
    assert Settings(app_env="test", database_url=database_url).cors_origins == []
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:8081", "http://192.168.1.20:8081"]')
    configured = Settings(app_env="test", database_url=database_url)
    assert configured.cors_origins == ["http://localhost:8081", "http://192.168.1.20:8081"]
    for origin in [
        "*",
        "https://*.example.com",
        "https://user:secret@example.com",
        "https://example.com/path",
        "https://example.com/",
        "https://example.com?query=1",
        "https://example.com#fragment",
        "http://example.com",
        "file:///preview",
    ]:
        with pytest.raises(ValueError):
            Settings(app_env="test", database_url=database_url, cors_origins=[origin])
    with pytest.raises(ValueError):
        Settings(
            app_env="production",
            database_url="postgresql+psycopg://fixture@localhost/yirenyoulu_prod",
            cors_origins=["http://localhost:8081"],
        )
    assert Settings(
        app_env="production",
        database_url="postgresql+psycopg://fixture@localhost/yirenyoulu_prod",
        cors_origins=["https://preview.example.com"],
    ).cors_origins == ["https://preview.example.com"]


def test_cors_preflight_only_allows_configured_origin_and_preserves_auth(api):
    from fastapi.testclient import TestClient

    from app.api import create_app

    client, factory = api
    origin = "http://localhost:8081"
    headers = {
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Authorization, Content-Type, Idempotency-Key",
    }
    assert (
        "access-control-allow-origin"
        not in client.options("/api/v1/auth/login", headers=headers).headers
    )
    settings = Settings(
        app_env="test",
        database_url="postgresql+psycopg://fixture@localhost/yirenyoulu_test",
        jwt_secret=client.app.state.settings.jwt_secret,
        cors_origins=[origin],
    )
    with TestClient(create_app(settings, factory)) as preview:
        approved = preview.options("/api/v1/auth/login", headers=headers)
        assert approved.status_code == 200
        assert approved.headers["access-control-allow-origin"] == origin
        assert "access-control-allow-credentials" not in approved.headers
        assert {"authorization", "content-type", "idempotency-key"} <= {
            value.strip().lower()
            for value in approved.headers["access-control-allow-headers"].split(",")
        }
        assert set(approved.headers["access-control-allow-methods"].split(", ")) == {
            "GET",
            "POST",
            "PATCH",
            "PUT",
            "DELETE",
            "OPTIONS",
        }
        rejected = preview.options(
            "/api/v1/auth/login", headers={**headers, "Origin": "http://unapproved.invalid"}
        )
        assert rejected.status_code == 400
        assert "access-control-allow-origin" not in rejected.headers
        unauthorized = preview.get("/api/v1/me", headers={"Origin": origin})
        assert unauthorized.status_code == 401
        assert unauthorized.json()["error"]["code"] == "SESSION_INVALID"
        assert unauthorized.headers["access-control-allow-origin"] == origin
        assert unauthorized.headers["access-control-expose-headers"] == "X-Request-ID, Retry-After"
        assert unauthorized.json()["request_id"] == unauthorized.headers["x-request-id"]
