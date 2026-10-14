"""Cross-process fixed-window limits backed by atomic database increments."""

import hashlib
import hmac
import time

from sqlalchemy import text

LIMITS = {
    "/api/v1/auth/login": 20,
    "/api/v1/auth/register": 10,
    "/api/v1/auth/refresh": 60,
    "/api/v1/auth/password-reset/request": 5,
    "/api/v1/auth/password-reset/confirm": 10,
    "/api/v1/auth/email-verification/request": 5,
    "/api/v1/auth/email-verification/confirm": 10,
}


def check_limit(sessions, secret, scope):
    limit = LIMITS.get(scope["path"]) if scope["method"] == "POST" else None
    if limit is None:
        return 0
    # Ignore untrusted forwarding headers; reverse-proxy trust is configured separately.
    host = (scope.get("client") or ("unknown", 0))[0]
    key = hmac.new(
        secret.encode(), (scope["path"] + ":" + host).encode(), hashlib.sha256
    ).hexdigest()
    now = int(time.time())
    window = now // 60 * 60
    with sessions.begin() as db:
        count = db.scalar(
            text("""
            INSERT INTO api_throttles (key_hash, window_start, count)
            VALUES (:key, :window, 1)
            ON CONFLICT (key_hash) DO UPDATE SET
              count = CASE WHEN api_throttles.window_start = :window
                           THEN api_throttles.count + 1 ELSE 1 END,
              window_start = :window
            RETURNING count
        """),
            {"key": key, "window": window},
        )
    return 60 - now % 60 if count > limit else 0
