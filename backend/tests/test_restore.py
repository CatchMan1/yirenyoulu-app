"""Backup/restore drill is explicitly destructive to the dedicated test database only."""

import os

import pytest
from sqlalchemy import select

from app.models import AuthSession, DeletionAudit, User
from test_api_accounts_catalog import auth, login, register

pytestmark = pytest.mark.skipif(
    not os.getenv("ITERATION_HTTP_DATABASE_URL") or not os.getenv("PG_DUMP_PATH"),
    reason="Isolated PostgreSQL and backup binaries required",
)


def test_restore_old_backup_replays_minimal_deletion_manifest(api, tmp_path):
    from app.maintenance import backup, export_deletions, restore_test
    from app.settings import Settings

    client, factory = api
    settings = Settings(app_env="test", database_url=os.environ["ITERATION_HTTP_DATABASE_URL"])
    user = register(client)
    login(client)
    dump = tmp_path / "before-delete.dump"
    manifest = tmp_path / "deletions.json"
    backup(settings, dump, os.environ["PG_DUMP_PATH"])
    tokens = login(client)
    assert (
        client.request(
            "DELETE",
            "/api/v1/me",
            json={"current_password": "TestOnly!Password12"},
            headers=auth(tokens),
        ).status_code
        == 204
    )
    export_deletions(factory, manifest)
    assert "alice" not in manifest.read_text() and "@" not in manifest.read_text()
    restore_test(settings, dump, manifest, os.environ["PG_RESTORE_PATH"])
    with factory() as db:
        assert db.get(User, user["id"]).status == "deleted"
        assert db.scalar(select(DeletionAudit)).subject_id == user["id"]
        assert db.scalars(select(AuthSession)).all() == []
    assert dump.stat().st_mode & 0o777 == 0o600
