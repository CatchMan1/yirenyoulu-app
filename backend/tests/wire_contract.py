"""Validate observed responses, including conditional contract invariants."""

import json
from pathlib import Path

from fastapi.routing import APIRoute
from jsonschema import Draft202012Validator, FormatChecker

CONTRACT = json.loads(
    (Path(__file__).resolve().parents[2] / "docs/技术开发/02接口与权限/openapi.json").read_text()
)


def check_response(app, response):
    path = response.request.url.path
    route = next(
        (
            r
            for r in app.routes
            if isinstance(r, APIRoute)
            and r.path_regex.fullmatch(path)
            and response.request.method in r.methods
        ),
        None,
    )
    if route is None:
        return
    operation = CONTRACT["paths"][route.path.removeprefix("/api/v1")][
        response.request.method.lower()
    ]
    definition = operation["responses"].get(str(response.status_code))
    assert definition is not None, (route.operation_id, response.status_code)
    if "$ref" in definition:
        definition = CONTRACT["components"]["responses"][definition["$ref"].split("/")[-1]]
    response.read()
    assert response.headers.get("cache-control") == "no-store"
    if response.status_code == 204:
        assert response.content == b""
        return
    schema = definition["content"]["application/json"]["schema"]
    validator = Draft202012Validator(
        {**schema, "components": CONTRACT["components"]}, format_checker=FormatChecker()
    )
    errors = list(validator.iter_errors(response.json()))
    assert not errors, (
        route.operation_id,
        response.status_code,
        [(list(e.path), list(e.schema_path)) for e in errors],
    )
    assert response.headers.get("x-request-id") == response.json()["request_id"]
