from sqlalchemy import select

from app.models import AuthSession, DeletionAudit, RecoveryToken, User
from test_api_accounts_catalog import auth, login, register


def test_mock_recovery_token_is_single_use_and_revokes_sessions(api):
    client, factory = api
    register(client)
    tokens = login(client)
    client.app.state.settings.mail_provider = "mock"
    response = client.post(
        "/api/v1/auth/password-reset/request", json={"email": "alice@example.com"}
    )
    assert response.status_code == 202, response.text
    token = client.app.state.mail_outbox[-1]["token"]
    body = {"token": token, "new_password": "NewOnly!Password123"}
    assert client.post("/api/v1/auth/password-reset/confirm", json=body).status_code == 204
    assert client.post("/api/v1/auth/password-reset/confirm", json=body).status_code == 422
    assert client.get("/api/v1/me", headers=auth(tokens)).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login", json={"identifier": "alice", "password": "NewOnly!Password123"}
        ).status_code
        == 200
    )
    with factory() as db:
        assert db.scalar(select(RecoveryToken)).token_hash != token


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


def test_login_rate_limit_is_shared_persistent_and_has_retry_header(api, monkeypatch):
    from types import SimpleNamespace

    from app import limiting

    # Fixed-window behavior must be tested within one deterministic minute.
    monkeypatch.setattr(limiting, "time", SimpleNamespace(time=lambda: 1800000010))
    client, _ = api
    responses = [
        client.post("/api/v1/auth/login", json={"identifier": "missing", "password": "wrong"})
        for _ in range(25)
    ]
    assert any(r.status_code == 429 for r in responses)
    limited = next(r for r in responses if r.status_code == 429)
    assert int(limited.headers["retry-after"]) >= 1
    assert limited.json()["error"]["code"] == "RATE_LIMITED"
