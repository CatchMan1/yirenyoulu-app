from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select

from app.http import utcnow
from app.models import ChatMessage, PlanningJob, Trip
from app.seed import fixture_id
from test_api_accounts_catalog import auth, login, register


def test_planning_is_persistent_and_worker_saves_once(api):
    client, factory = api
    register(client)
    tokens = login(client)
    client.app.state.settings.ai_provider = "mock"
    key = str(uuid4())
    body = {"city_id": fixture_id("city"), "start_date": "2027-01-01", "end_date": "2027-01-02"}
    response = client.post(
        "/api/v1/planning-jobs", json=body, headers={**auth(tokens), "Idempotency-Key": key}
    )
    assert response.status_code == 202, response.text
    jid = response.json()["data"]["id"]
    assert response.json()["data"]["trip_id"] is None
    from app.planning import run_once

    assert run_once(client.app.state.settings, factory) is True
    assert run_once(client.app.state.settings, factory) is False
    result = client.get("/api/v1/planning-jobs/" + jid, headers=auth(tokens)).json()["data"]
    assert result["status"] == "succeeded" and result["trip_id"]
    assert (
        client.post(
            "/api/v1/planning-jobs", json=body, headers={**auth(tokens), "Idempotency-Key": key}
        ).json()["data"]["id"]
        == jid
    )
    with factory() as db:
        assert len(db.scalars(select(Trip)).all()) == 1
    assert (
        client.delete(
            "/api/v1/trips/" + result["trip_id"], params={"version": 1}, headers=auth(tokens)
        ).status_code
        == 204
    )
    assert (
        client.get("/api/v1/planning-jobs/" + jid, headers=auth(tokens)).json()["data"][
            "result_deleted"
        ]
        is True
    )


def test_cancel_and_expired_task_cannot_save(api):
    client, factory = api
    register(client)
    tokens = login(client)
    client.app.state.settings.ai_provider = "mock"
    body = {"city_id": fixture_id("city"), "start_date": "2027-01-01", "end_date": "2027-01-02"}
    response = client.post(
        "/api/v1/planning-jobs",
        json=body,
        headers={**auth(tokens), "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 202, response.text
    jid = response.json()["data"]["id"]
    assert (
        client.delete("/api/v1/planning-jobs/" + jid, headers=auth(tokens)).json()["data"]["status"]
        == "cancelled"
    )
    from app.planning import run_once

    assert run_once(client.app.state.settings, factory) is False
    another = client.post(
        "/api/v1/planning-jobs",
        json=body,
        headers={**auth(tokens), "Idempotency-Key": str(uuid4())},
    ).json()["data"]["id"]
    with factory.begin() as db:
        db.get(PlanningJob, another).deadline = utcnow() - timedelta(seconds=1)
    run_once(client.app.state.settings, factory)
    assert (
        client.get("/api/v1/planning-jobs/" + another, headers=auth(tokens)).json()["data"][
            "status"
        ]
        == "timed_out"
    )
    with factory() as db:
        assert db.scalars(select(Trip)).all() == []


def test_chat_history_context_idempotency_and_owner_isolation(api):
    client, factory = api
    register(client)
    alice = login(client)
    register(client, "bob")
    bob = login(client, "bob")
    client.app.state.settings.ai_provider = "mock"
    created = client.post("/api/v1/chat-sessions", json={}, headers=auth(alice))
    assert created.status_code == 201, created.text
    sid = created.json()["data"]["id"]
    path = "/api/v1/chat-sessions/" + sid + "/messages"
    assert client.get(path, headers=auth(bob)).status_code == 404
    mid = str(uuid4())
    body = {"message_id": mid, "content": "记住暗号：向日葵"}
    first = client.post(path, json=body, headers=auth(alice))
    assert first.status_code == 201, first.text
    again = client.post(path, json=body, headers=auth(alice))
    assert (
        again.status_code == 201
        and again.json()["data"]["assistant_message"]["id"]
        == first.json()["data"]["assistant_message"]["id"]
    )
    assert (
        client.post(path, json={**body, "content": "changed"}, headers=auth(alice)).status_code
        == 409
    )
    second = client.post(
        path, json={"message_id": str(uuid4()), "content": "之前的暗号是什么"}, headers=auth(alice)
    )
    assert second.status_code == 201
    assert "向日葵" in second.json()["data"]["assistant_message"]["content"]
    history = client.get(path, headers=auth(alice)).json()
    assert len(history["data"]) == 4 and history["meta"]["has_more"] is False


def test_behavior_replay_ignores_new_receive_window(api):
    client, factory = api
    register(client)
    tokens = login(client)
    event = {
        "event_id": str(uuid4()),
        "place_id": fixture_id("fixture-attraction-1"),
        "type": "view",
        "occurred_at": utcnow().isoformat().replace("+00:00", "Z"),
    }
    first = client.post("/api/v1/behavior-events", json=event, headers=auth(tokens))
    assert first.status_code == 202, first.text
    assert (
        client.post("/api/v1/behavior-events", json=event, headers=auth(tokens)).json()["data"][
            "status"
        ]
        == "duplicate"
    )
    assert (
        client.post(
            "/api/v1/behavior-events",
            json={**event, "place_id": fixture_id("fixture-attraction-2")},
            headers=auth(tokens),
        ).status_code
        == 409
    )


def test_expired_worker_lease_cannot_commit_even_before_reclaim(api):
    client, factory = api
    register(client)
    tokens = login(client)
    client.app.state.settings.ai_provider = "mock"
    body = {"city_id": fixture_id("city"), "start_date": "2027-01-01", "end_date": "2027-01-02"}
    jid = client.post(
        "/api/v1/planning-jobs",
        json=body,
        headers={**auth(tokens), "Idempotency-Key": str(uuid4())},
    ).json()["data"]["id"]
    from app.planning import CatalogTools, FakePlanner, claim, finish

    info = claim(factory)
    output = FakePlanner().plan(info[3], CatalogTools(factory, body["city_id"], []))
    with factory.begin() as db:
        db.get(PlanningJob, jid).lease_until = utcnow() - timedelta(seconds=1)
    assert finish(factory, info, output=output) is False
    with factory() as db:
        assert db.scalars(select(Trip)).all() == []


def test_cancelled_and_deleted_subject_fence_inflight_worker(api):
    client, factory = api
    register(client)
    tokens = login(client)
    client.app.state.settings.ai_provider = "mock"
    body = {"city_id": fixture_id("city"), "start_date": "2027-01-01", "end_date": "2027-01-02"}
    from app.planning import CatalogTools, FakePlanner, claim, finish

    for erase in (False, True):
        jid = client.post(
            "/api/v1/planning-jobs",
            json=body,
            headers={**auth(tokens), "Idempotency-Key": str(uuid4())},
        ).json()["data"]["id"]
        info = claim(factory)
        output = FakePlanner().plan(info[3], CatalogTools(factory, body["city_id"], []))
        if erase:
            assert (
                client.request(
                    "DELETE",
                    "/api/v1/me",
                    json={"current_password": "TestOnly!Password12"},
                    headers=auth(tokens),
                ).status_code
                == 204
            )
        else:
            assert (
                client.delete("/api/v1/planning-jobs/" + jid, headers=auth(tokens)).status_code
                == 200
            )
        assert finish(factory, info, output=output) is False
        with factory() as db:
            assert db.scalars(select(Trip)).all() == []


def test_recovery_delivery_has_public_receipt_and_verification_is_owner_scoped(api):
    client, factory = api
    register(client)
    alice = login(client)
    register(client, "bob")
    bob = login(client, "bob")
    client.app.state.settings.mail_provider = "mock"
    response = client.post(
        "/api/v1/auth/password-reset/request", json={"email": "absent@example.com"}
    )
    assert response.json()["data"] == {"status": "accepted"}
    response = client.post("/api/v1/auth/email-verification/request", headers=auth(alice))
    assert response.status_code == 202 and response.json()["data"] == {"status": "accepted"}
    token = client.app.state.mail_outbox[-1]["token"]
    path = "/api/v1/auth/email-verification/confirm"
    denied = client.post(path, json={"token": token}, headers=auth(bob))
    assert (
        denied.status_code == 422 and denied.json()["error"]["code"] == "VERIFICATION_TOKEN_INVALID"
    )
    assert client.post(path, json={"token": token}, headers=auth(alice)).status_code == 204
    assert client.post(path, json={"token": token}, headers=auth(alice)).status_code == 422
    assert client.get("/api/v1/me", headers=auth(alice)).json()["data"]["email_verified"] is True


def test_chat_provider_result_after_lease_expiry_is_failed_and_retriable(api):
    import pytest

    from app.auth import Principal, decode
    from app.chat import send_turn
    from app.http import ApiError
    from app.models import ChatSession
    from app.schemas import MessageCreate

    client, factory = api
    register(client)
    tokens = login(client)
    settings = client.app.state.settings
    settings.ai_provider = "mock"
    sid = client.post("/api/v1/chat-sessions", json={}, headers=auth(tokens)).json()["data"]["id"]
    claims = decode(settings, tokens["access_token"], "access")
    actor = Principal(claims["sub"], claims["sid"])
    body = MessageCreate(message_id=str(uuid4()), content="【测试】迟到结果")

    class ExpiredProvider:
        def reply(self, messages, trip):
            with factory.begin() as db:
                db.get(ChatSession, sid).lease_until = utcnow() - timedelta(seconds=1)
            return "【测试】迟到回答"

    with pytest.raises(ApiError) as captured:
        send_turn(settings, factory, actor, sid, body, ExpiredProvider())
    assert captured.value.status == 504
    with factory() as db:
        assistant = db.scalar(select(ChatMessage).where(ChatMessage.role == "assistant"))
        assert (
            assistant.status == "failed"
            and assistant.content == ""
            and assistant.error_code == "PROVIDER_TIMEOUT"
        )
    assert (
        send_turn(settings, factory, actor, sid, body)["assistant_message"]["status"] == "succeeded"
    )


def test_completed_mock_results_keep_their_mode_after_configuration_changes(api):
    client, factory = api
    register(client)
    tokens = login(client)
    settings = client.app.state.settings
    settings.ai_provider = "mock"
    sid = client.post("/api/v1/chat-sessions", json={}, headers=auth(tokens)).json()["data"]["id"]
    body = {"message_id": str(uuid4()), "content": "【测试】结果来源"}
    path = "/api/v1/chat-sessions/" + sid + "/messages"
    assert (
        client.post(path, json=body, headers=auth(tokens)).json()["data"]["provider_mode"] == "mock"
    )
    settings.ai_provider = "disabled"
    assert (
        client.post(path, json=body, headers=auth(tokens)).json()["data"]["provider_mode"] == "mock"
    )


def test_planner_cannot_save_fabricated_place_or_use_arbitrary_tools(api):
    import pytest

    from app.http import ApiError
    from app.planning import CatalogTools, run_once

    client, factory = api
    register(client)
    tokens = login(client)
    client.app.state.settings.ai_provider = "mock"
    body = {"city_id": fixture_id("city"), "start_date": "2027-01-01", "end_date": "2027-01-02"}
    jid = client.post(
        "/api/v1/planning-jobs",
        json=body,
        headers={**auth(tokens), "Idempotency-Key": str(uuid4())},
    ).json()["data"]["id"]
    tools = CatalogTools(factory, body["city_id"], [])
    assert not hasattr(tools, "execute_sql")
    with pytest.raises(ApiError):
        tools.search_places("SELECT * FROM users")

    class FabricatingProvider:
        def plan(self, payload, tools):
            return [
                {
                    "place_id": str(uuid4()),
                    "date": "2027-01-01",
                    "start_minute": 600,
                    "end_minute": 660,
                }
            ]

    assert run_once(client.app.state.settings, factory, FabricatingProvider())
    result = client.get("/api/v1/planning-jobs/" + jid, headers=auth(tokens)).json()["data"]
    assert result["status"] == "failed" and result["error_code"] == "PLAN_INVALID"
    with factory() as db:
        assert db.scalars(select(Trip)).all() == []


def test_polling_expires_queued_job_when_worker_is_offline(api):
    client, factory = api
    register(client)
    tokens = login(client)
    client.app.state.settings.ai_provider = "mock"
    body = {"city_id": fixture_id("city"), "start_date": "2027-01-01", "end_date": "2027-01-02"}
    jid = client.post(
        "/api/v1/planning-jobs",
        json=body,
        headers={**auth(tokens), "Idempotency-Key": str(uuid4())},
    ).json()["data"]["id"]
    with factory.begin() as db:
        db.get(PlanningJob, jid).deadline = utcnow() - timedelta(seconds=1)
    response = client.get("/api/v1/planning-jobs/" + jid, headers=auth(tokens))
    assert response.json()["data"]["status"] == "timed_out"
    with factory() as db:
        assert db.get(PlanningJob, jid).status == "timed_out"


def test_chat_history_recovers_expired_reply_slot_without_new_message(api):
    from app.models import ChatSession

    client, factory = api
    register(client)
    tokens = login(client)
    client.app.state.settings.ai_provider = "mock"
    sid = client.post("/api/v1/chat-sessions", json={}, headers=auth(tokens)).json()["data"]["id"]
    path = "/api/v1/chat-sessions/" + sid + "/messages"
    body = {"message_id": str(uuid4()), "content": "【测试】中断回复"}
    assert client.post(path, json=body, headers=auth(tokens)).status_code == 201
    with factory.begin() as db:
        assistant = db.scalar(select(ChatMessage).where(ChatMessage.role == "assistant"))
        assistant.status = "running"
        assistant.content = ""
        assistant.error_code = None
        db.get(ChatSession, sid).lease_until = utcnow() - timedelta(seconds=1)
    history = client.get(path, headers=auth(tokens)).json()["data"]
    assert history[-1]["status"] == "failed" and history[-1]["error_code"] == "PROVIDER_TIMEOUT"
    assert client.post(path, json=body, headers=auth(tokens)).status_code == 201
