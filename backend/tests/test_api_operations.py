"""Exercise every published operation with isolated fixtures and mock providers."""

import json
import os
from pathlib import Path
from uuid import uuid4

from fastapi.routing import APIRoute

from app.http import utcnow
from app.seed import fixture_id


def test_all_44_operations_have_observed_contract_responses(api):
    client, _ = api
    client.app.state.settings.ai_provider = "mock"
    client.app.state.settings.mail_provider = "mock"
    seen = set()

    def record(response):
        route = next(
            (
                r
                for r in client.app.routes
                if isinstance(r, APIRoute)
                and r.path_regex.fullmatch(response.request.url.path)
                and response.request.method in r.methods
            ),
            None,
        )
        if route:
            seen.add(route.operation_id)

    client.event_hooks["response"].append(record)

    def call(method, path, expected, body=None, headers=None):
        response = client.request(method, "/api/v1" + path, json=body, headers=headers)
        assert response.status_code == expected, (method, path, response.status_code)
        return response.json().get("data") if response.content else None

    account = {"username": "alice", "email": "alice@example.com", "password": "TestOnly!Password12"}
    call("POST", "/auth/register", 201, account)

    def login(password):
        data = call("POST", "/auth/login", 200, {"identifier": "alice", "password": password})
        return data["tokens"], {"Authorization": "Bearer " + data["tokens"]["access_token"]}

    tokens, headers = login(account["password"])
    rotated = call("POST", "/auth/refresh", 200, {"refresh_token": tokens["refresh_token"]})
    headers = {"Authorization": "Bearer " + rotated["access_token"]}
    call("GET", "/me", 200, headers=headers)
    call(
        "PATCH",
        "/me",
        200,
        {"nickname": "【测试】资料", "signature": "仅供接口验证", "preferences": {}},
        headers,
    )
    call("POST", "/auth/email-verification/request", 202, headers=headers)
    raw = client.app.state.mail_outbox[-1]["token"]
    call("POST", "/auth/email-verification/confirm", 204, {"token": raw}, headers)
    call(
        "POST",
        "/me/password",
        204,
        {"current_password": account["password"], "new_password": "ChangedOnly!Password123"},
        headers,
    )
    tokens, headers = login("ChangedOnly!Password123")
    call("POST", "/auth/password-reset/request", 202, {"email": account["email"]})
    raw = client.app.state.mail_outbox[-1]["token"]
    call(
        "POST",
        "/auth/password-reset/confirm",
        204,
        {"token": raw, "new_password": "ResetOnly!Password123"},
    )
    tokens, headers = login("ResetOnly!Password123")
    for path in ["/cities", "/categories", "/tags", "/places"]:
        call("GET", path, 200)
    place = fixture_id("fixture-attraction-1")
    call("GET", "/places/" + place, 200)
    call("GET", "/places/" + place + "/navigation", 200)
    call("PUT", "/favorites/" + place, 204, headers=headers)
    call("GET", "/favorites", 200, headers=headers)
    call("DELETE", "/favorites/" + place, 204, headers=headers)
    call(
        "POST",
        "/behavior-events",
        202,
        {
            "event_id": str(uuid4()),
            "place_id": place,
            "type": "view",
            "occurred_at": utcnow().isoformat().replace("+00:00", "Z"),
        },
        headers,
    )
    call("GET", "/recommendations", 200, headers=headers)
    body = {
        "title": "【测试】完整操作",
        "city_id": fixture_id("city"),
        "start_date": "2027-01-01",
        "end_date": "2027-01-02",
    }
    trip = call("POST", "/trips", 201, body, {**headers, "Idempotency-Key": str(uuid4())})
    tid = trip["id"]
    base = "/trips/" + tid
    call("GET", "/trips", 200, headers=headers)
    call("GET", base, 200, headers=headers)
    trip = call(
        "POST",
        base + "/items",
        201,
        {
            "version": trip["version"],
            "place_id": place,
            "date": "2027-01-01",
            "start_minute": 600,
            "end_minute": 660,
        },
        headers,
    )
    item = trip["items"][0]["id"]
    trip = call(
        "PATCH",
        base + "/items/" + item,
        200,
        {"version": trip["version"], "note": "【测试】更新"},
        headers,
    )
    trip = call(
        "DELETE", base + "/items/" + item + "?version=" + str(trip["version"]), 200, headers=headers
    )
    trip = call(
        "PATCH", base, 200, {"version": trip["version"], "title": "【测试】更新标题"}, headers
    )
    job = call(
        "POST",
        "/planning-jobs",
        202,
        {key: value for key, value in body.items() if key != "title"},
        {**headers, "Idempotency-Key": str(uuid4())},
    )
    call("GET", "/planning-jobs", 200, headers=headers)
    call("GET", "/planning-jobs/" + job["id"], 200, headers=headers)
    call("DELETE", "/planning-jobs/" + job["id"], 200, headers=headers)
    chat = call("POST", "/chat-sessions", 201, {"trip_id": tid}, headers)
    chatpath = "/chat-sessions/" + chat["id"]
    call("GET", "/chat-sessions", 200, headers=headers)
    call("GET", chatpath, 200, headers=headers)
    call("PATCH", chatpath, 200, {"title": "【测试】会话标题"}, headers)
    call(
        "POST",
        chatpath + "/messages",
        201,
        {"message_id": str(uuid4()), "content": "【测试】多轮接口"},
        headers,
    )
    call("GET", chatpath + "/messages", 200, headers=headers)
    call("DELETE", chatpath, 204, headers=headers)
    call("DELETE", base + "?version=" + str(trip["version"]), 204, headers=headers)
    call("GET", "/health/live", 200)
    call("GET", "/health/ready", 200 if os.getenv("ITERATION_HTTP_DATABASE_URL") else 503)
    call("POST", "/auth/logout", 204, headers=headers)
    tokens, headers = login("ResetOnly!Password123")
    call("DELETE", "/me", 204, {"current_password": "ResetOnly!Password123"}, headers)
    contract = json.loads(
        (
            Path(__file__).resolve().parents[2] / "docs/技术开发/02接口与权限/openapi.json"
        ).read_text()
    )
    operations = {
        op["operationId"]
        for methods in contract["paths"].values()
        for method, op in methods.items()
        if method in {"get", "post", "put", "patch", "delete"}
    }
    assert len(operations) == 44 and seen == operations
