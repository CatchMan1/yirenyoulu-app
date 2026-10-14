import pytest

from app.settings import Settings


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///travel_app.db",
        "postgresql://localhost/old",
        "postgresql://localhost/yirenyoulu_prod",
    ],
)
def test_test_environment_refuses_nonisolated_database(url):
    with pytest.raises(ValueError):
        Settings(app_env="test", database_url=url)


def test_production_refuses_mock_provider():
    with pytest.raises(ValueError):
        Settings(
            app_env="production",
            database_url="postgresql+psycopg://localhost/yirenyoulu_prod",
            ai_provider="mock",
        )


def test_fixture_environment_allows_only_owned_database_name():
    settings = Settings(
        app_env="test", database_url="postgresql+psycopg://localhost/yirenyoulu_test"
    )
    assert settings.database_url.endswith("/yirenyoulu_test")


def test_default_has_no_database_connection(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValueError):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    "query",
    [
        "dbname=yirenyoulu_prod",
        "service=production",
        "host=production",
        "options=-csearch_path=private",
        "user=legacy",
        "port=5433",
    ],
)
def test_query_cannot_override_validated_connection(query):
    with pytest.raises(ValueError):
        Settings(
            app_env="test", database_url="postgresql+psycopg://localhost/yirenyoulu_test?" + query
        )
