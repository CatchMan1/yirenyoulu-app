"""Passwords, signed tokens and revocable database sessions."""

from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from secrets import token_urlsafe
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Request
from sqlalchemy import select

from .http import aware, fail, utcnow
from .models import AuthSession, User

password_hasher = PasswordHasher()
# A dummy hash keeps unknown-user password verification on the same expensive path.
_dummy_hash = password_hasher.hash(token_urlsafe(24))


def verify_password(hashed: str, raw: str) -> bool:
    try:
        return password_hasher.verify(hashed, raw)
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False


def digest(raw: str) -> str:
    return sha256(raw.encode()).hexdigest()


def public_user(user: User):
    return {
        k: getattr(user, k)
        for k in (
            "id",
            "username",
            "email",
            "email_verified",
            "nickname",
            "signature",
            "preferences",
        )
    }


@dataclass(frozen=True)
class Principal:
    user_id: str
    session_id: str


def decode(settings, token: str, token_type: str):
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "sid", "typ", "iat", "exp", "iss", "aud", "jti"]},
        )
        if (
            claims["typ"] != token_type
            or not isinstance(claims["sub"], str)
            or not isinstance(claims["sid"], str)
        ):
            fail(401, "SESSION_INVALID")
        return claims
    except jwt.InvalidTokenError:
        fail(401, "SESSION_INVALID", "会话失效，请重新登录")


def issue(settings, user: User, session: AuthSession):
    now = utcnow()
    common = {
        "sub": user.id,
        "sid": session.id,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
    }
    access = jwt.encode(
        {**common, "typ": "access", "jti": str(uuid4()), "exp": now + timedelta(minutes=15)},
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )
    refresh = jwt.encode(
        {
            **common,
            "typ": "refresh",
            "jti": str(uuid4()),
            "gen": session.generation,
            "exp": aware(session.expires_at),
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )
    session.refresh_hash = digest(refresh)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "Bearer",
        "expires_in": 900,
        "refresh_expires_at": aware(session.expires_at).isoformat().replace("+00:00", "Z"),
    }


def checked_session(db, principal: Principal, lock=False):
    # All mutations use this order: user, then auth session, then domain rows.
    user_q = select(User).where(User.id == principal.user_id)
    if lock:
        user_q = user_q.with_for_update()
    user = db.scalar(user_q)
    session_q = select(AuthSession).where(
        AuthSession.id == principal.session_id, AuthSession.user_id == principal.user_id
    )
    if lock:
        session_q = session_q.with_for_update()
    session = db.scalar(session_q)
    if (
        not user
        or not session
        or session.revoked_at
        or aware(session.expires_at) <= utcnow()
        or user.status == "deleted"
    ):
        fail(401, "SESSION_INVALID")
    if user.status != "active":
        fail(403, "ACCOUNT_DISABLED")
    return user, session


def principal(request: Request, optional=False):
    header = request.headers.get("authorization")
    if not header:
        if optional:
            return None
        fail(401, "SESSION_INVALID")
    parts = header.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        fail(401, "SESSION_INVALID")
    claims = decode(request.app.state.settings, parts[1], "access")
    actor = Principal(claims["sub"], claims["sid"])
    with request.app.state.sessions() as db:
        checked_session(db, actor)
    return actor
