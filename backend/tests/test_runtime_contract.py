"""Compare executable routes and wire responses to the published contract."""

import json
from pathlib import Path

from fastapi.routing import APIRoute

from test_api_accounts_catalog import auth, login, register

CONTRACT = json.loads(
    (Path(__file__).resolve().parents[2] / "docs/技术开发/02接口与权限/openapi.json").read_text()
)


def test_all_declared_operations_are_executable_with_typed_responses(api):
    client, _ = api
    routes = {
        (r.path.removeprefix("/api/v1"), method.lower()): r
        for r in client.app.routes
        if isinstance(r, APIRoute)
        for method in r.methods
    }
    for path, methods in CONTRACT["paths"].items():
        for method, operation in methods.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            route = routes[(path, method)]
            assert route.operation_id == operation["operationId"]
            code = next(code for code in operation["responses"] if code.startswith("2"))
            if code != "204":
                assert route.response_model is not None
                schema = route.response_model.model_json_schema()
                assert "dict" not in route.response_model.__name__.lower(), route.operation_id
                assert schema["properties"]["request_id"].get("format") == "uuid"


def test_unknown_query_is_rejected_on_scalar_and_no_query_routes(api):
    client, _ = api
    register(client)
    tokens = login(client)
    response = client.get("/api/v1/me?user_id=other", headers=auth(tokens))
    assert response.status_code == 422
    assert response.json()["error"]["details"] == [
        {"path": "query.user_id", "code": "UNKNOWN_FIELD"}
    ]


def test_generated_openapi_declares_actual_authentication(api):
    client, _ = api
    schema = client.get("/openapi.json").json()
    assert "BearerAuth" in schema["components"]["securitySchemes"]
    assert schema["paths"]["/api/v1/me"]["get"]["security"] == [{"BearerAuth": []}]
    assert schema["paths"]["/api/v1/auth/login"]["post"].get("security", []) == []


def test_database_timezone_is_normalized_to_utc_wire_format():
    from datetime import datetime, timedelta, timezone

    from app.catalog import timestamp

    assert (
        timestamp(datetime(2027, 1, 1, 8, tzinfo=timezone(timedelta(hours=8))))
        == "2027-01-01T00:00:00Z"
    )


def test_readiness_requires_migrated_database(api):
    import os

    client, _ = api
    response = client.get("/api/v1/health/ready")
    assert response.status_code == (200 if os.getenv("ITERATION_HTTP_DATABASE_URL") else 503)
