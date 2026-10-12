"""Only the new project's explicitly named databases may be connected."""
from typing import Literal
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra='ignore')
    app_env: Literal['development', 'test', 'production'] = 'development'
    database_url: str
    ai_provider: Literal['disabled', 'mock'] = 'disabled'

    @model_validator(mode='after')
    def isolated_environment(self):
        url = make_url(self.database_url)
        expected = {'development': 'yirenyoulu_dev', 'test': 'yirenyoulu_test', 'production': 'yirenyoulu_prod'}
        if url.drivername != 'postgresql+psycopg' or url.database != expected[self.app_env]:
            raise ValueError('Use the dedicated PostgreSQL database for APP_ENV')
        if self.app_env == 'production' and self.ai_provider == 'mock':
            raise ValueError('Mock providers are forbidden in production')
        return self
