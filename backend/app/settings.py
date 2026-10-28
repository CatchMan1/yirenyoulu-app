"""Only the new project's explicitly named databases may be connected."""

import ipaddress
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", hide_input_in_errors=True)
    app_env: Literal["development", "test", "production"] = "development"
    database_url: str
    jwt_secret: SecretStr = SecretStr("")
    jwt_issuer: str = "yirenyoulu-app"
    jwt_audience: str = "yirenyoulu-mobile"
    cors_origins: list[str] = Field(default_factory=list)
    ai_provider: Literal["disabled", "mock"] = "disabled"
    mail_provider: Literal["disabled", "mock"] = "disabled"

    @model_validator(mode="after")
    def isolated_environment(self):
        for origin in self.cors_origins:
            parts = urlsplit(origin)
            if (
                not parts.hostname
                or "*" in origin
                or parts.username
                or parts.password
                or parts.path
                or parts.query
                or parts.fragment
            ):
                raise ValueError("CORS must use explicit origins without credentials or paths")
            if parts.scheme != "https":
                if self.app_env == "production" or parts.scheme != "http":
                    raise ValueError("Production CORS requires HTTPS")
                if parts.hostname != "localhost":
                    try:
                        host = ipaddress.ip_address(parts.hostname)
                        if not (host.is_private or host.is_loopback):
                            raise ValueError("Development HTTP CORS requires a local address")
                    except ValueError:
                        raise ValueError("Development HTTP CORS requires a local address") from None
            if parts.port is not None and not 1 <= parts.port <= 65535:
                raise ValueError("Invalid CORS port")
        url = make_url(self.database_url)
        allowed_query = {"sslmode", "sslrootcert", "connect_timeout", "application_name"}
        if set(url.query) - allowed_query:
            raise ValueError("Database query parameters cannot override the connection target")
        expected = {
            "development": "yirenyoulu_dev",
            "test": "yirenyoulu_test",
            "production": "yirenyoulu_prod",
        }
        if url.drivername != "postgresql+psycopg" or url.database != expected[self.app_env]:
            raise ValueError("Use the dedicated PostgreSQL database for APP_ENV")
        if self.app_env == "production" and "mock" in {self.ai_provider, self.mail_provider}:
            raise ValueError("Mock providers are forbidden in production")
        return self
