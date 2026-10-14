"""Single-use recovery and transactional erasure, shared by restore replay."""

from datetime import timedelta
from secrets import token_urlsafe
from uuid import uuid4

from fastapi import Request, Response
from sqlalchemy import delete, select, update

from . import schemas as dto
from .auth import checked_session, digest, password_hasher, principal, verify_password
from .http import aware, fail, result, utcnow
from .models import (
    AuthSession,
    BehaviorEvent,
    ChatMessage,
    ChatSession,
    DeletionAudit,
    Favorite,
    IdempotencyRecord,
    PlanningJob,
    RecommendationRun,
    RecoveryToken,
    Trip,
    TripItem,
    User,
)
from .responses import RESPONSE_MODELS


def erase_subject(db, user_id):
    """Caller holds subject row lock. Repeatable after restoring an old backup."""
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        return
    chat_ids = select(ChatSession.id).where(ChatSession.user_id == user_id)
    trip_ids = select(Trip.id).where(Trip.user_id == user_id)
    db.execute(delete(ChatMessage).where(ChatMessage.session_id.in_(chat_ids)))
    db.execute(delete(ChatSession).where(ChatSession.user_id == user_id))
    db.execute(delete(TripItem).where(TripItem.trip_id.in_(trip_ids)))
    db.execute(delete(Trip).where(Trip.user_id == user_id))
    for model in (
        PlanningJob,
        Favorite,
        BehaviorEvent,
        IdempotencyRecord,
        RecoveryToken,
        AuthSession,
    ):
        db.execute(delete(model).where(model.user_id == user_id))
    db.execute(update(RecommendationRun).values(expires_at=utcnow()))
    user.status = "deleted"
    user.username = "deleted_" + uuid4().hex
    user.email = uuid4().hex + "@deleted.invalid"
    user.password_hash = password_hasher.hash(token_urlsafe(48))
    user.nickname = user.signature = ""
    user.preferences = {}
    user.email_verified = False
    if not db.scalar(select(DeletionAudit).where(DeletionAudit.subject_id == user_id)):
        db.add(DeletionAudit(subject_id=user_id))


def install(app, sessions):
    prefix = "/api/v1"
    app.state.mail_outbox = []  # Explicit local test transport; never exposed by an API.

    def mail_ready():
        settings = app.state.settings
        if settings.mail_provider != "mock" or settings.app_env == "production":
            fail(503, "PROVIDER_UNAVAILABLE", "邮件服务未配置")

    def new_token(db, user, purpose):
        raw = token_urlsafe(48)
        db.add(
            RecoveryToken(
                user_id=user.id,
                purpose=purpose,
                token_hash=digest(raw),
                expires_at=utcnow() + timedelta(minutes=15 if purpose == "reset" else 30),
            )
        )
        return {"to": user.email, "purpose": purpose, "token": raw}

    def consume(db, raw, purpose, owner=None):
        # Discover the subject without locking; all writes lock user before token.
        candidate = db.scalar(
            select(RecoveryToken).where(
                RecoveryToken.token_hash == digest(raw), RecoveryToken.purpose == purpose
            )
        )
        if candidate is None or (owner is not None and candidate.user_id != owner):
            fail(
                422, "VERIFICATION_TOKEN_INVALID" if purpose == "verify" else "RESET_TOKEN_INVALID"
            )
        user = db.scalar(select(User).where(User.id == candidate.user_id).with_for_update())
        token = db.scalar(
            select(RecoveryToken)
            .where(RecoveryToken.id == candidate.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            not user
            or user.status != "active"
            or not token
            or token.consumed_at
            or aware(token.expires_at) <= utcnow()
        ):
            fail(
                422, "VERIFICATION_TOKEN_INVALID" if purpose == "verify" else "RESET_TOKEN_INVALID"
            )
        token.consumed_at = utcnow()
        return user

    @app.post(
        prefix + "/auth/password-reset/request",
        status_code=202,
        response_model=RESPONSE_MODELS["requestPasswordReset"],
        operation_id="requestPasswordReset",
    )
    def request_reset(request: Request, body: dto.RecoveryRequest):
        mail_ready()
        outgoing = None
        with sessions.begin() as db:
            user = db.scalar(
                select(User)
                .where(User.email == str(body.email).lower(), User.status == "active")
                .with_for_update()
            )
            if user:
                outgoing = new_token(db, user, "reset")
        if outgoing:
            app.state.mail_outbox.append(outgoing)
        return result(request, {"status": "accepted"})

    @app.post(
        prefix + "/auth/password-reset/confirm",
        status_code=204,
        operation_id="confirmPasswordReset",
    )
    def confirm_reset(body: dto.RecoveryConfirm):
        with sessions.begin() as db:
            user = consume(db, body.token, "reset")
            user.password_hash = password_hasher.hash(body.new_password)
            db.execute(
                update(AuthSession)
                .where(AuthSession.user_id == user.id)
                .values(revoked_at=utcnow())
            )
            # Another outstanding reset link must not restore the previous owner's access.
            db.execute(
                update(RecoveryToken)
                .where(RecoveryToken.user_id == user.id, RecoveryToken.purpose == "reset")
                .values(consumed_at=utcnow())
            )
        return Response(status_code=204)

    @app.post(
        prefix + "/auth/email-verification/request",
        status_code=202,
        response_model=RESPONSE_MODELS["requestVerification"],
        operation_id="requestVerification",
    )
    def request_verification(request: Request):
        actor = principal(request)
        mail_ready()
        outgoing = None
        with sessions.begin() as db:
            user, _ = checked_session(db, actor, lock=True)
            if not user.email_verified:
                outgoing = new_token(db, user, "verify")
        if outgoing:
            app.state.mail_outbox.append(outgoing)
        return result(request, {"status": "accepted"})

    @app.post(
        prefix + "/auth/email-verification/confirm",
        status_code=204,
        operation_id="confirmVerification",
    )
    def confirm_verification(request: Request, body: dto.VerificationConfirm):
        actor = principal(request)
        with sessions.begin() as db:
            checked_session(db, actor, lock=True)
            consume(db, body.token, "verify", actor.user_id).email_verified = True
        return Response(status_code=204)

    @app.delete(prefix + "/me", status_code=204, operation_id="deleteAccount")
    def delete_account(request: Request, body: dto.AccountDelete):
        actor = principal(request)
        with sessions.begin() as db:
            user, _ = checked_session(db, actor, lock=True)
            if not verify_password(user.password_hash, body.current_password):
                fail(401, "CURRENT_PASSWORD_INVALID")
            erase_subject(db, user.id)
        return Response(status_code=204)
