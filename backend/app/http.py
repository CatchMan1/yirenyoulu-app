"""HTTP errors and envelopes; never echo submitted values."""

from typing import Generic, NoReturn, TypeVar
from uuid import uuid4

from fastapi import Request
from fastapi.routing import APIRoute
from pydantic import BaseModel

T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    data: T
    meta: dict | None = None
    request_id: str


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: list | None = None):
        self.status, self.code, self.message = status, code, message
        self.details = details or []


def fail(status: int, code: str, message: str = "请求无法完成") -> NoReturn:
    raise ApiError(status, code, message)


def result(request: Request, data, meta=None):
    return {"data": data, "meta": meta, "request_id": request.state.request_id}


def utcnow():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def aware(value):
    from datetime import timezone

    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


class ProtocolMiddleware:
    """Bound request buffering before parsing; impose server-owned request IDs."""

    def __init__(self, app, sessions, secret):
        self.app = app
        self.sessions, self.secret = sessions, secret

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        from urllib.parse import parse_qsl

        from starlette.responses import JSONResponse

        rid = str(uuid4())
        scope.setdefault("state", {})["request_id"] = rid
        headers = dict(scope.get("headers", []))
        chunks = bytearray()
        error = None
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunks.extend(message.get("body", b""))
            if len(chunks) > 65536:
                error = (413, "PAYLOAD_TOO_LARGE")
                break
            if not message.get("more_body", False):
                break
        if (
            chunks
            and headers.get(b"content-type", b"").split(b";")[0].strip().lower()
            != b"application/json"
        ):
            error = (415, "UNSUPPORTED_MEDIA_TYPE")
        seen = set()
        for key, _ in parse_qsl(
            scope.get("query_string", b"").decode("utf-8", errors="replace"), keep_blank_values=True
        ):
            if key in seen and key not in {"explicit_tags", "preferred_tags", "status"}:
                error = (422, "INVALID_INPUT")
            seen.add(key)
        started = False

        async def response_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                existing = [
                    (k, v)
                    for k, v in message.get("headers", [])
                    if k.lower() not in {b"x-request-id", b"cache-control"}
                ]
                message["headers"] = existing + [
                    (b"x-request-id", rid.encode()),
                    (b"cache-control", b"no-store"),
                ]
            await send(message)

        if error:
            response = JSONResponse(
                {
                    "error": {"code": error[1], "message": "请求格式不合法", "details": []},
                    "request_id": rid,
                },
                status_code=error[0],
            )
            return await response(scope, receive, response_send)
        from anyio import to_thread
        from sqlalchemy.exc import SQLAlchemyError

        from .limiting import check_limit

        try:
            retry = await to_thread.run_sync(check_limit, self.sessions, self.secret, scope)
        except SQLAlchemyError:
            response = JSONResponse(
                {
                    "error": {
                        "code": "PROVIDER_UNAVAILABLE",
                        "message": "数据库暂不可用",
                        "details": [],
                    },
                    "request_id": rid,
                },
                status_code=503,
            )
            return await response(scope, receive, response_send)
        if retry:
            response = JSONResponse(
                {
                    "error": {"code": "RATE_LIMITED", "message": "请求过于频繁", "details": []},
                    "request_id": rid,
                },
                status_code=429,
                headers={"Retry-After": str(retry)},
            )
            return await response(scope, receive, response_send)
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(chunks), "more_body": False}
            return await receive()

        try:
            await self.app(scope, replay, response_send)
        except Exception:
            if started:
                raise
            # Unexpected errors are redacted within this boundary so headers remain uniform.
            response = JSONResponse(
                {
                    "error": {"code": "INTERNAL_ERROR", "message": "服务暂不可用", "details": []},
                    "request_id": rid,
                },
                status_code=500,
            )
            await response(scope, receive, response_send)


class StrictRoute(APIRoute):
    def __init__(self, *args, **kwargs):
        from fastapi import Depends
        from fastapi.security import HTTPBearer

        from .responses import ERROR_CODES, ErrorResponse

        operation = kwargs.get("operation_id")
        public = {
            "register",
            "login",
            "refresh",
            "requestPasswordReset",
            "confirmPasswordReset",
            "listCities",
            "listCategories",
            "listTags",
            "listPlaces",
            "getPlace",
            "getNavigation",
            "liveness",
            "readiness",
            "getRecommendations",
        }
        if operation not in public or operation == "getRecommendations":
            kwargs["dependencies"] = [
                *(kwargs.get("dependencies") or []),
                Depends(HTTPBearer(scheme_name="BearerAuth", auto_error=False)),
            ]
        if operation == "getRecommendations":
            kwargs["openapi_extra"] = {"security": [{}, {"BearerAuth": []}]}
        kwargs["responses"] = {
            **(kwargs.get("responses") or {}),
            **{
                code: {"model": ErrorResponse, "description": "统一错误响应"}
                for code in ERROR_CODES.get(operation or "", [])
            },
        }
        super().__init__(*args, **kwargs)

    def get_route_handler(self):
        handler = super().get_route_handler()
        allowed = set()
        for field in self.dependant.query_params:
            model = field.field_info.annotation
            if isinstance(model, type) and issubclass(model, BaseModel):
                allowed.update(model.model_fields)
            else:
                allowed.add(field.alias)

        async def checked(request):
            unknown = sorted(set(request.query_params) - allowed)
            if unknown:
                raise ApiError(
                    422,
                    "INVALID_INPUT",
                    "请求字段不合法",
                    [{"path": "query." + key, "code": "UNKNOWN_FIELD"} for key in unknown][:20],
                )
            return await handler(request)

        return checked
