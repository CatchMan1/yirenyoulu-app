"""FastAPI application factory; database resources have explicit ownership."""

from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException

from . import schemas as dto
from .auth import (
    Principal,
    _dummy_hash,
    checked_session,
    decode,
    digest,
    issue,
    password_hasher,
    principal,
    public_user,
    verify_password,
)
from .catalog import (
    city_data,
    emit_behavior,
    filtered_places,
    named,
    paginate,
    place_data,
    valid_place,
)
from .db import make_engine
from .http import ApiError, ProtocolMiddleware, StrictRoute, fail, result, utcnow
from .models import AuthSession, Category, City, Favorite, Place, Tag, User
from .responses import RESPONSE_MODELS
from .settings import Settings


def create_app(settings: Settings, sessions=None):
    if len(settings.jwt_secret.get_secret_value()) < 32:
        raise ValueError("JWT_SECRET must be independently configured (at least 32 characters)")
    if sessions is not None and settings.app_env != "test":
        raise ValueError("Session injection is restricted to isolated tests")
    expected_revision = ScriptDirectory.from_config(
        Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    ).get_current_head()
    engine = None
    if sessions is None:
        from sqlalchemy.orm import sessionmaker

        engine = make_engine(settings)
        sessions = sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(app):
        yield
        if engine is not None:
            engine.dispose()

    app = FastAPI(title="一人有路", version="0.1.0", lifespan=lifespan, redirect_slashes=False)
    app.router.route_class = StrictRoute
    app.state.settings, app.state.sessions = settings, sessions
    app.add_middleware(
        ProtocolMiddleware, sessions=sessions, secret=settings.jwt_secret.get_secret_value()
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Accept", "Authorization", "Content-Type", "Idempotency-Key"],
            expose_headers=["X-Request-ID", "Retry-After"],
        )

    @app.exception_handler(ApiError)
    async def business_error(request, error):
        headers = {"WWW-Authenticate": "Bearer"} if error.status == 401 else {}
        return JSONResponse(
            {
                "error": {"code": error.code, "message": error.message, "details": error.details},
                "request_id": request.state.request_id,
            },
            status_code=error.status,
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, error):
        mapping = {
            "extra_forbidden": "UNKNOWN_FIELD",
            "missing": "REQUIRED",
            "literal_error": "INVALID_ENUM",
        }
        details = [
            {
                "path": ".".join(str(x) for x in e["loc"]),
                "code": mapping.get(e["type"], "INVALID_FORMAT"),
            }
            for e in error.errors()
        ][:20]
        return await business_error(
            request, ApiError(422, "INVALID_INPUT", "请求字段不合法", details)
        )

    @app.exception_handler(HTTPException)
    async def framework_error(request, error):
        return await business_error(
            request,
            ApiError(
                error.status_code,
                "NOT_FOUND" if error.status_code == 404 else "BAD_REQUEST",
                "请求无法完成",
            ),
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, error):
        return await business_error(
            request, ApiError(503, "PROVIDER_UNAVAILABLE", "数据库暂不可用")
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request, error):
        return await business_error(request, ApiError(500, "INTERNAL_ERROR", "服务暂不可用"))

    prefix = "/api/v1"

    @app.post(
        prefix + "/auth/register",
        status_code=201,
        response_model=RESPONSE_MODELS["register"],
        operation_id="register",
    )
    def register(request: Request, body: dto.Register):
        try:
            with sessions.begin() as db:
                if db.scalar(
                    select(User).where(
                        or_(User.username == body.username, User.email == str(body.email).lower())
                    )
                ):
                    fail(409, "ACCOUNT_CONFLICT")
                user = User(
                    username=body.username,
                    email=str(body.email).lower(),
                    password_hash=password_hasher.hash(body.password),
                    nickname=body.nickname.strip(),
                    preferences=dto.Preferences().model_dump(),
                )
                db.add(user)
                db.flush()
                data = public_user(user)
        except IntegrityError:
            fail(409, "ACCOUNT_CONFLICT")
        return result(request, data)

    @app.post(prefix + "/auth/login", response_model=RESPONSE_MODELS["login"], operation_id="login")
    def login(request: Request, body: dto.Login):
        with sessions.begin() as db:
            identifier = body.identifier.strip().lower()
            user = db.scalar(
                select(User)
                .where(or_(User.username == identifier, User.email == identifier))
                .with_for_update()
            )
            correct = verify_password(user.password_hash if user else _dummy_hash, body.password)
            if not user or not correct or user.status == "deleted":
                fail(401, "INVALID_CREDENTIALS", "用户名或密码不正确")
            if user.status != "active":
                fail(403, "ACCOUNT_DISABLED")
            session = AuthSession(
                id=str(uuid4()),
                user_id=user.id,
                refresh_hash=uuid4().hex + uuid4().hex,
                expires_at=utcnow() + timedelta(days=30),
                generation=0,
            )
            db.add(session)
            tokens = issue(settings, user, session)
            db.flush()
            data = {"tokens": tokens, "user": public_user(user)}
        return result(request, data)

    @app.post(
        prefix + "/auth/refresh", response_model=RESPONSE_MODELS["refresh"], operation_id="refresh"
    )
    def refresh(request: Request, body: dto.Refresh):
        claims = decode(settings, body.refresh_token, "refresh")
        rejected = False
        with sessions.begin() as db:
            user, session = checked_session(db, Principal(claims["sub"], claims["sid"]), lock=True)
            if (
                claims.get("gen") != session.generation
                or digest(body.refresh_token) != session.refresh_hash
            ):
                session.revoked_at = utcnow()
                rejected = True
            else:
                session.previous_refresh_hash = session.refresh_hash
                session.generation += 1
                tokens = issue(settings, user, session)
        # Revocation must commit even though the HTTP response is an error.
        if rejected:
            fail(401, "SESSION_INVALID")
        return result(request, tokens)

    @app.post(prefix + "/auth/logout", status_code=204, operation_id="logout")
    def logout(request: Request):
        actor = principal(request)
        with sessions.begin() as db:
            _, session = checked_session(db, actor, lock=True)
            session.revoked_at = utcnow()
        return Response(status_code=204)

    @app.get(prefix + "/me", response_model=RESPONSE_MODELS["getMe"], operation_id="getMe")
    def me(request: Request):
        actor = principal(request)
        with sessions() as db:
            user, _ = checked_session(db, actor)
            data = public_user(user)
        return result(request, data)

    @app.patch(prefix + "/me", response_model=RESPONSE_MODELS["updateMe"], operation_id="updateMe")
    def profile(request: Request, body: dto.ProfileUpdate):
        actor = principal(request)
        changes = body.model_dump(exclude_unset=True)
        if "preferences" in changes:
            changes["preferences"] = body.preferences.model_dump()
        if not changes:
            fail(422, "INVALID_INPUT")
        with sessions.begin() as db:
            user, _ = checked_session(db, actor, lock=True)
            for key, value in changes.items():
                if key == "preferences" and any(
                    db.get(Tag, t) is None for t in value.get("tags", [])
                ):
                    fail(422, "INVALID_INPUT")
                setattr(user, key, value.strip() if isinstance(value, str) else value)
            db.flush()
            data = public_user(user)
        return result(request, data)

    @app.post(prefix + "/me/password", status_code=204, operation_id="changePassword")
    def change_password(request: Request, body: dto.PasswordChange):
        actor = principal(request)
        with sessions.begin() as db:
            user, _ = checked_session(db, actor, lock=True)
            if not verify_password(user.password_hash, body.current_password):
                fail(401, "CURRENT_PASSWORD_INVALID")
            user.password_hash = password_hasher.hash(body.new_password)
            db.execute(
                update(AuthSession)
                .where(AuthSession.user_id == user.id)
                .values(revoked_at=utcnow())
            )
        return Response(status_code=204)

    @app.get(
        prefix + "/places", response_model=RESPONSE_MODELS["listPlaces"], operation_id="listPlaces"
    )
    def places(request: Request, query: Annotated[dto.PlaceQuery, Query()]):
        with sessions() as db:
            data, meta = paginate(
                db, filtered_places(query), query, lambda row: place_data(db, row)
            )
        return result(request, data, meta)

    @app.get(
        prefix + "/places/{place_id}",
        response_model=RESPONSE_MODELS["getPlace"],
        operation_id="getPlace",
    )
    def place(request: Request, place_id: dto.UUIDText):
        with sessions() as db:
            data = place_data(db, valid_place(db, place_id), True)
        return result(request, data)

    @app.get(
        prefix + "/places/{place_id}/navigation",
        response_model=RESPONSE_MODELS["getNavigation"],
        operation_id="getNavigation",
    )
    def navigation(
        request: Request,
        place_id: dto.UUIDText,
        mode: Annotated[str, Query(pattern="^(walking|driving|transit|cycling)$")] = "walking",
        provider: Annotated[str | None, Query(pattern="^(amap|google)$")] = None,
    ):
        with sessions() as db:
            row = valid_place(db, place_id)
            data = place_data(db, row)
        return result(
            request,
            {
                "status": "unavailable",
                "provider": "none",
                "mode": mode,
                "destination": {
                    "place_id": row.id,
                    "name": row.name,
                    "address": row.address,
                    "coordinates": data["coordinates"],
                },
                "url": None,
                "reason": "NO_COORDINATES" if data["coordinates"] is None else "PROVIDER_DISABLED",
            },
        )

    def directory(model, serializer, operation_id):
        def endpoint(request: Request, query: Annotated[dto.DirectoryQuery, Query()]):
            stmt = select(model)
            if query.q:
                stmt = stmt.where(model.name.contains(query.q.strip(), autoescape=True))
            with sessions() as db:
                data, meta = paginate(db, stmt.order_by(model.name, model.id), query, serializer)
            return result(request, data, meta)

        app.add_api_route(
            prefix
            + "/"
            + {"City": "cities", "Category": "categories", "Tag": "tags"}[model.__name__],
            endpoint,
            methods=["GET"],
            response_model=RESPONSE_MODELS[operation_id],
            operation_id=operation_id,
        )

    directory(City, city_data, "listCities")
    directory(Category, named, "listCategories")
    directory(Tag, named, "listTags")

    @app.get(
        prefix + "/favorites",
        response_model=RESPONSE_MODELS["listFavorites"],
        operation_id="listFavorites",
    )
    def favorites(request: Request, query: Annotated[dto.FavoriteQuery, Query()]):
        actor = principal(request)
        with sessions() as db:
            checked_session(db, actor)
            stmt = select(Place).join(Favorite).where(Favorite.user_id == actor.user_id)
            if query.kind:
                stmt = stmt.where(Place.kind == query.kind)
            data, meta = paginate(
                db,
                stmt.order_by(Favorite.created_at.desc(), Favorite.id.desc()),
                query,
                lambda row: place_data(db, row),
            )
        return result(request, data, meta)

    @app.get(
        prefix + "/favorites/{place_id}",
        response_model=RESPONSE_MODELS["getFavoriteStatus"],
        operation_id="getFavoriteStatus",
    )
    def favorite_status(request: Request, place_id: dto.UUIDText):
        actor = principal(request)
        with sessions() as db:
            checked_session(db, actor)
            existing = db.scalar(
                select(Favorite.id).where(
                    Favorite.user_id == actor.user_id, Favorite.place_id == place_id
                )
            )
        return result(request, {"place_id": place_id, "is_favorited": existing is not None})

    @app.put(prefix + "/favorites/{place_id}", status_code=204, operation_id="addFavorite")
    def add_favorite(request: Request, place_id: dto.UUIDText):
        actor = principal(request)
        with sessions.begin() as db:
            checked_session(db, actor, lock=True)
            existing = db.scalar(
                select(Favorite).where(
                    Favorite.user_id == actor.user_id, Favorite.place_id == place_id
                )
            )
            if not existing:
                valid_place(db, place_id)
                db.add(Favorite(user_id=actor.user_id, place_id=place_id))
                emit_behavior(
                    db, actor.user_id, place_id, "favorite", settings.app_env == "production"
                )
        return Response(status_code=204)

    @app.delete(prefix + "/favorites/{place_id}", status_code=204, operation_id="removeFavorite")
    def remove_favorite(request: Request, place_id: dto.UUIDText):
        actor = principal(request)
        with sessions.begin() as db:
            checked_session(db, actor, lock=True)
            existing = db.scalar(
                select(Favorite).where(
                    Favorite.user_id == actor.user_id, Favorite.place_id == place_id
                )
            )
            if existing:
                db.delete(existing)
                emit_behavior(
                    db, actor.user_id, place_id, "unfavorite", settings.app_env == "production"
                )
        return Response(status_code=204)

    @app.get(
        prefix + "/health/live", response_model=RESPONSE_MODELS["liveness"], operation_id="liveness"
    )
    def live(request: Request):
        return result(request, {"status": "ok"})

    @app.get(
        prefix + "/health/ready",
        response_model=RESPONSE_MODELS["readiness"],
        operation_id="readiness",
    )
    def ready(request: Request):
        from sqlalchemy import text

        with sessions() as db:
            revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
            if revision != expected_revision:
                fail(503, "PROVIDER_UNAVAILABLE", "数据库迁移尚未就绪")
        return result(request, {"status": "ok"})

    from .trips import install as install_trips

    install_trips(app, sessions)
    from .chat import install as install_chat
    from .planning import install as install_planning
    from .recommendations import install as install_recommendations

    install_planning(app, sessions)
    install_chat(app, sessions)
    install_recommendations(app, sessions)
    from .recovery import install as install_recovery

    install_recovery(app, sessions)
    return app
