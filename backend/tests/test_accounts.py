"""Password storage, token replay, private data and account erasure."""

import pytest
from sqlalchemy import select

from app.models import AuthSession, BehaviorEvent, DeletionAudit, Favorite, User
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
