"""Durable chat turns with owner scope, bounded context and fencing."""

from datetime import timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import Query, Request, Response
from sqlalchemy import delete, func, select

from . import schemas as dto
from .auth import checked_session, digest, principal
from .catalog import paginate, timestamp
from .http import ApiError, aware, fail, result, utcnow
from .models import ChatMessage, ChatSession
from .responses import RESPONSE_MODELS
from .trips import owned_trip, trip_summary


def session_data(row):
    return {
        "id": row.id,
        "title": row.title,
        "trip_id": row.trip_id,
        "created_at": timestamp(row.created_at),
        "updated_at": timestamp(row.updated_at),
    }


def message_data(row):
    return {
        "id": row.id,
        "message_id": row.client_message_id,
        "sequence": row.sequence,
        "role": row.role,
        "content": row.content,
        "status": row.status,
        "error_code": row.error_code,
        "created_at": timestamp(row.created_at),
    }


def owned(db, actor, sid):
    row = db.scalar(
        select(ChatSession)
        .where(ChatSession.id == sid, ChatSession.user_id == actor.user_id)
        .with_for_update()
    )
    if row is None:
        fail(404, "NOT_FOUND")
    return row


class FakeChat:
    def reply(self, messages, trip):
        prior = "；".join(m["content"] for m in messages if m["role"] == "user")
        return ("【模拟服务】仅用于多轮上下文验证：" + prior)[:8000]


def context(db, sid, current):
    # Select completed turns, not orphan user messages from failed turns.
    candidates = db.scalars(
        select(ChatMessage)
        .where(
            ChatMessage.session_id == sid,
            ChatMessage.sequence < current.sequence,
            ChatMessage.role == "assistant",
            ChatMessage.status == "succeeded",
        )
        .order_by(ChatMessage.sequence.desc())
        .limit(10)
    ).all()
    complete = []
    for assistant in reversed(candidates):
        user = db.scalar(
            select(ChatMessage).where(
                ChatMessage.session_id == sid,
                ChatMessage.client_message_id == assistant.client_message_id,
                ChatMessage.role == "user",
                ChatMessage.status == "succeeded",
            )
        )
        if user:
            complete.extend(
                [
                    {"role": "user", "content": user.content},
                    {"role": "assistant", "content": assistant.content},
                ]
            )
    while complete and sum(len(m["content"]) for m in complete) + len(current.content) > 14000:
        complete = complete[2:]
    return [*complete, {"role": "user", "content": current.content}]


def send_turn(settings, sessions, actor, sid, body, provider=None):
    with sessions.begin() as db:
        checked_session(db, actor, True)
        chat = owned(db, actor, sid)
        user = db.scalar(
            select(ChatMessage).where(
                ChatMessage.session_id == sid,
                ChatMessage.client_message_id == body.message_id,
                ChatMessage.role == "user",
            )
        )
        if user:
            if user.content_hash != digest(body.content):
                fail(409, "IDEMPOTENCY_CONFLICT")
            assistant = db.scalar(
                select(ChatMessage).where(
                    ChatMessage.session_id == sid,
                    ChatMessage.client_message_id == body.message_id,
                    ChatMessage.role == "assistant",
                )
            )
            if assistant.status == "succeeded":
                return {
                    "user_message": message_data(user),
                    "assistant_message": message_data(assistant),
                    "provider_mode": assistant.provider_mode,
                }
            later = db.scalar(
                select(func.count())
                .select_from(ChatMessage)
                .where(
                    ChatMessage.session_id == sid,
                    ChatMessage.role == "user",
                    ChatMessage.sequence > user.sequence,
                )
            )
            if later:
                fail(409, "MESSAGE_RETRY_EXPIRED")
        else:
            assistant = None
        running = db.scalars(
            select(ChatMessage).where(
                ChatMessage.session_id == sid,
                ChatMessage.role == "assistant",
                ChatMessage.status.in_(["pending", "running"]),
            )
        ).all()
        if running and chat.lease_until and aware(chat.lease_until) > utcnow():
            fail(409, "MESSAGE_IN_PROGRESS" if user else "SESSION_BUSY")
        for row in running:
            row.status = "failed"
            row.error_code = "PROVIDER_TIMEOUT"
            row.content = ""
        if user is None:
            user = ChatMessage(
                id=str(uuid4()),
                session_id=sid,
                client_message_id=body.message_id,
                content_hash=digest(body.content),
                sequence=chat.next_sequence,
                role="user",
                content=body.content,
                status="succeeded",
            )
            assistant = ChatMessage(
                id=str(uuid4()),
                session_id=sid,
                client_message_id=body.message_id,
                content_hash=digest(body.content),
                sequence=chat.next_sequence + 1,
                role="assistant",
                content="",
                status="pending",
            )
            chat.next_sequence += 2
            db.add_all([user, assistant])
            db.flush()
        assistant.provider_mode = (
            settings.ai_provider if settings.app_env != "production" else "disabled"
        )
        assistant.status = "running"
        assistant.error_code = None
        assistant.content = ""
        chat.lease_generation += 1
        generation = chat.lease_generation
        chat.lease_until = utcnow() + timedelta(seconds=45)
        history = context(db, sid, user)
        trip = None
        if chat.trip_id:
            trip = trip_summary(owned_trip(db, actor, chat.trip_id))
    error = None
    reply = ""
    try:
        if settings.ai_provider != "mock" or settings.app_env == "production":
            raise ApiError(503, "PROVIDER_UNAVAILABLE", "模型服务未配置")
        reply = (provider or FakeChat()).reply(history, trip)
        if not isinstance(reply, str) or not reply.strip() or len(reply) > 8000:
            raise ApiError(503, "PROVIDER_UNAVAILABLE", "模型结果不合法")
    except TimeoutError:
        error = ApiError(504, "PROVIDER_TIMEOUT", "模型服务超时")
    except ApiError as exc:
        error = exc
    except Exception:
        error = ApiError(503, "PROVIDER_UNAVAILABLE", "模型服务不可用")
    with sessions.begin() as db:
        checked_session(db, actor, True)
        chat = owned(db, actor, sid)
        if chat.lease_generation != generation:
            fail(409, "MESSAGE_IN_PROGRESS")
        assistant = db.scalar(
            select(ChatMessage).where(
                ChatMessage.session_id == sid,
                ChatMessage.client_message_id == body.message_id,
                ChatMessage.role == "assistant",
            )
        )
        user = db.scalar(
            select(ChatMessage).where(
                ChatMessage.session_id == sid,
                ChatMessage.client_message_id == body.message_id,
                ChatMessage.role == "user",
            )
        )
        if aware(chat.lease_until) <= utcnow():
            error = ApiError(504, "PROVIDER_TIMEOUT", "模型服务超时")
        assistant.status = "failed" if error else "succeeded"
        assistant.error_code = error.code if error else None
        assistant.content = "" if error else reply
        chat.lease_until = None
        db.flush()
        data = {
            "user_message": message_data(user),
            "assistant_message": message_data(assistant),
            "provider_mode": assistant.provider_mode,
        }
    if error:
        raise error
    return data


def install(app, sessions):
    prefix = "/api/v1/chat-sessions"
    settings = app.state.settings

    @app.post(
        prefix,
        status_code=201,
        response_model=RESPONSE_MODELS["createChatSession"],
        operation_id="createChatSession",
    )
    def create(request: Request, body: dto.ChatCreate):
        actor = principal(request)
        with sessions.begin() as db:
            checked_session(db, actor, True)
            if body.trip_id:
                owned_trip(db, actor, body.trip_id)
            chat = ChatSession(user_id=actor.user_id, title=body.title, trip_id=body.trip_id)
            db.add(chat)
            db.flush()
            data = session_data(chat)
        return result(request, data)

    @app.get(
        prefix, response_model=RESPONSE_MODELS["listChatSessions"], operation_id="listChatSessions"
    )
    def listing(request: Request, query: Annotated[dto.PageQuery, Query()]):
        actor = principal(request)
        with sessions() as db:
            checked_session(db, actor)
            data, meta = paginate(
                db,
                select(ChatSession)
                .where(ChatSession.user_id == actor.user_id)
                .order_by(ChatSession.created_at.desc(), ChatSession.id.desc()),
                query,
                session_data,
            )
        return result(request, data, meta)

    @app.get(
        prefix + "/{session_id}",
        response_model=RESPONSE_MODELS["getChatSession"],
        operation_id="getChatSession",
    )
    def detail(request: Request, session_id: dto.UUIDText):
        actor = principal(request)
        with sessions() as db:
            checked_session(db, actor)
            data = session_data(owned(db, actor, session_id))
        return result(request, data)

    @app.patch(
        prefix + "/{session_id}",
        response_model=RESPONSE_MODELS["updateChatSession"],
        operation_id="updateChatSession",
    )
    def rename(request: Request, session_id: dto.UUIDText, body: dto.ChatUpdate):
        actor = principal(request)
        with sessions.begin() as db:
            checked_session(db, actor, True)
            chat = owned(db, actor, session_id)
            chat.title = body.title.strip()
            if not chat.title:
                fail(422, "INVALID_INPUT")
            db.flush()
            data = session_data(chat)
        return result(request, data)

    @app.delete(prefix + "/{session_id}", status_code=204, operation_id="deleteChatSession")
    def remove(request: Request, session_id: dto.UUIDText):
        actor = principal(request)
        with sessions.begin() as db:
            checked_session(db, actor, True)
            chat = owned(db, actor, session_id)
            db.execute(delete(ChatMessage).where(ChatMessage.session_id == chat.id))
            db.delete(chat)
        return Response(status_code=204)

    @app.get(
        prefix + "/{session_id}/messages",
        response_model=RESPONSE_MODELS["listMessages"],
        operation_id="listMessages",
    )
    def messages(
        request: Request, session_id: dto.UUIDText, query: Annotated[dto.MessageQuery, Query()]
    ):
        actor = principal(request)
        with sessions.begin() as db:
            checked_session(db, actor, True)
            chat = owned(db, actor, session_id)
            if chat.lease_until and aware(chat.lease_until) <= utcnow():
                for row in db.scalars(
                    select(ChatMessage).where(
                        ChatMessage.session_id == session_id,
                        ChatMessage.role == "assistant",
                        ChatMessage.status.in_(["pending", "running"]),
                    )
                ):
                    row.status = "failed"
                    row.error_code = "PROVIDER_TIMEOUT"
                    row.content = ""
                chat.lease_generation += 1
                chat.lease_until = None
                db.flush()
            stmt = select(ChatMessage).where(ChatMessage.session_id == session_id)
            if query.before_sequence is not None:
                stmt = stmt.where(ChatMessage.sequence < query.before_sequence)
            rows = db.scalars(
                stmt.order_by(ChatMessage.sequence.desc()).limit(query.limit + 1)
            ).all()
            more = len(rows) > query.limit
            rows = list(reversed(rows[: query.limit]))
            data = [message_data(m) for m in rows]
            meta = {"next_before_sequence": rows[0].sequence if more else None, "has_more": more}
        return result(request, data, meta)

    @app.post(
        prefix + "/{session_id}/messages",
        status_code=201,
        response_model=RESPONSE_MODELS["sendMessage"],
        operation_id="sendMessage",
    )
    def send(request: Request, session_id: dto.UUIDText, body: dto.MessageCreate):
        return result(request, send_turn(settings, sessions, principal(request), session_id, body))
