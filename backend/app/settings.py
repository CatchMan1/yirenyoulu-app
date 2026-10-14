"""Only the new project's explicitly named databases may be connected."""

from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", hide_input_in_errors=True)
    app_env: Literal["development", "test", "production"] = "development"
    database_url: str
    jwt_secret: SecretStr = SecretStr("")
    jwt_issuer: str = "yirenyoulu-app"
    jwt_audience: str = "yirenyoulu-mobile"
    ai_provider: Literal["disabled", "mock"] = "disabled"
    mail_provider: Literal["disabled", "mock"] = "disabled"

    @model_validator(mode="after")
    def isolated_environment(self):
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
