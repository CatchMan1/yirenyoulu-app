"""The operator entry point keeps credentials private and never bootstraps an unmigrated DB."""

import json
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Column, MetaData, String, Table, create_engine, func, insert, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker
from test_bulk_collection import provider as provider

from app import bulk_collect as cli
from app.models import Base, CollectionRun, DataSource, Place


@pytest.fixture
def operator(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + str(tmp_path / "operator.db"))
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(cli, "make_engine", lambda settings: engine)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://operator@ambient/yirenyoulu_test")
    monkeypatch.setenv("JWT_SECRET", "TEST ambient secret")
    yield engine, factory
    engine.dispose()


def ready(engine):
    heads = ScriptDirectory.from_config(Config(str(cli.ALEMBIC_CONFIG))).get_heads()
    table = Table("alembic_version", MetaData(), Column("version_num", String(100)))
    table.create(engine)
    with engine.begin() as connection:
        connection.execute(insert(table), [{"version_num": value} for value in heads])


def config_file(tmp_path, **changes):
    payload = {
        "run_key": "TEST-operator-001",
        "cities": ["Q90003"],
        "kinds": ["attraction"],
        "per_city_kind_limit": 3,
        "page_size": 2,
        "record_budget": 100,
        "request_budget": 100,
        "interval_seconds": 1,
        "review_reference": "TEST synthetic operator rule authorization",
        **changes,
    }
    file = tmp_path / "bulk.json"
    file.write_text(json.dumps(payload))
    return file


def messages(capsys):
    return [json.loads(line) for line in capsys.readouterr().out.splitlines()]


def test_unmigrated_database_fails_before_source_or_network(operator, tmp_path, capsys):
    _, factory = operator
    result = cli.main(["run", "--config", str(config_file(tmp_path))])
    assert result != 0
    assert messages(capsys)[-1]["error"] == "DATABASE_MIGRATION_REQUIRED"
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(DataSource)) == 0


@pytest.mark.usefixtures("provider")
def test_default_run_stages_then_explicit_resume_applies(operator, tmp_path, capsys):
    engine, factory = operator
    ready(engine)
    result = cli.main(["run", "--config", str(config_file(tmp_path))])
    assert result == 0
    output = messages(capsys)
    report = output[-1]
    assert report["status"] == "staged" and report["staged"] == 3 and report["applied"] == 0
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Place)) == 0
    assert cli.main(["resume", "--run-id", report["run_id"], "--apply"]) == 0
    assert messages(capsys)[-1]["applied"] == 3
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Place)) == 3
    assert cli.main(["status", "--run-key", "TEST-operator-001"]) == 0
    assert messages(capsys)[-1]["run_id"] == report["run_id"]
    assert cli.main(["status", "--run-id", report["run_id"]]) == 0
    assert messages(capsys)[-1]["status"] == "completed"


def test_explicit_env_file_wins_without_printing_secrets(operator, tmp_path, capsys):
    engine, _ = operator
    ready(engine)
    file = tmp_path / "operator.env"
    password = uuid4().hex
    database_url = URL.create(
        "postgresql+psycopg",
        username="private_user",
        password=password,
        host="explicit",
        port=55432,
        database="yirenyoulu_dev",
    ).render_as_string(hide_password=False)
    file.write_text(
        "APP_ENV=development\n"
        f"DATABASE_URL={database_url}\n"
        "JWT_SECRET=private_jwt\n"
        "UNRELATED_SECRET=never_print_me\n"
    )
    assert cli.main(["--env-file", str(file), "status", "--run-key", "missing"]) != 0
    output = capsys.readouterr().out
    assert '"host": "explicit"' in output
    assert '"database": "yirenyoulu_dev"' in output
    assert '"port": 55432' in output
    for secret in ["private_user", password, "private_jwt", "never_print_me"]:
        assert secret not in output


def test_missing_and_invalid_config_are_safe_failures(operator, tmp_path, capsys):
    _, factory = operator
    assert cli.main(["run", "--config", str(tmp_path / "absent.json")]) != 0
    assert messages(capsys)[-1]["error"] == "CONFIG_UNAVAILABLE"
    file = config_file(tmp_path, secret="private-config-value")
    assert cli.main(["run", "--config", str(file)]) != 0
    output = capsys.readouterr().out
    assert "CONFIG_INVALID" in output and "private-config-value" not in output
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(DataSource)) == 0


@pytest.mark.usefixtures("provider")
def test_interrupt_retains_run_id_for_resume(operator, tmp_path, capsys, monkeypatch):
    from app import bulk_collection as bulk

    engine, factory = operator
    ready(engine)

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(bulk, "discover_page", interrupted)
    assert cli.main(["run", "--config", str(config_file(tmp_path)), "--apply"]) == 130
    output = messages(capsys)
    with factory() as db:
        job = db.scalar(select(CollectionRun))
        assert job.status == "paused"
        assert output[-1]["run_id"] == job.id
    assert output[-1]["error"] == "INTERRUPTED"
    assert "resume" in output[-1]["hint"]


@pytest.mark.usefixtures("provider")
def test_provider_error_is_redacted_and_run_remains_resumable(
    operator, tmp_path, capsys, monkeypatch
):
    from app import bulk_collection as bulk

    engine, factory = operator
    ready(engine)

    def failed(*args, **kwargs):
        raise ValueError("https://private-host/?token=private_provider_value")

    monkeypatch.setattr(bulk, "discover_page", failed)
    assert cli.main(["run", "--config", str(config_file(tmp_path)), "--apply"]) != 0
    output = capsys.readouterr().out
    assert "COLLECTION_FAILED" in output and "private_provider_value" not in output
    with factory() as db:
        job = db.scalar(select(CollectionRun))
        assert job.status == "failed" and job.id in output


def test_old_migration_does_not_create_source(operator, tmp_path, capsys):
    engine, factory = operator
    table = Table("alembic_version", MetaData(), Column("version_num", String(100)))
    table.create(engine)
    with engine.begin() as connection:
        connection.execute(insert(table), {"version_num": "0001_old"})
    assert cli.main(["run", "--config", str(config_file(tmp_path))]) != 0
    assert messages(capsys)[-1]["error"] == "DATABASE_MIGRATION_REQUIRED"
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(DataSource)) == 0


def test_status_does_not_implicitly_load_working_directory_env(
    operator, tmp_path, monkeypatch, capsys
):
    engine, _ = operator
    ready(engine)
    (tmp_path / ".env").write_text(
        "APP_ENV=production\nDATABASE_URL=postgresql+psycopg://private@unexpected/yirenyoulu_prod\n"
    )
    monkeypatch.chdir(tmp_path)
    assert cli.main(["status", "--run-key", "missing"]) != 0
    target = messages(capsys)[0]
    assert target["environment"] == "test" and target["host"] == "ambient"


def test_invalid_environment_does_not_leak_database_credentials(operator, monkeypatch, capsys):
    password = uuid4().hex
    database_url = URL.create(
        "postgresql+psycopg",
        username="private",
        password=password,
        host="invalid",
        database="old_project_database",
    ).render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", database_url)
    assert cli.main(["status", "--run-key", "missing"]) != 0
    output = capsys.readouterr().out
    assert "SETTINGS_INVALID" in output
    assert password not in output and "old_project_database" not in output
