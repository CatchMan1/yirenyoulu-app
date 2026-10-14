"""Offline backups and test-only restore with mandatory erasure replay."""

import argparse
import json
import os
import subprocess
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from .db import make_engine
from .models import DeletionAudit
from .recovery import erase_subject
from .settings import Settings


def pg_environment(settings):
    url = make_url(settings.database_url)
    assert url.database is not None
    env: dict[str, str] = {
        **os.environ,
        "PGHOST": url.host or "localhost",
        "PGPORT": str(url.port or 5432),
        "PGDATABASE": url.database,
        "PGUSER": url.username or "",
        "PGPASSWORD": url.password or "",
        "PGCONNECT_TIMEOUT": "10",
    }
    for key, target in [("sslmode", "PGSSLMODE"), ("sslrootcert", "PGSSLROOTCERT")]:
        if key in url.query:
            value = url.query[key]
            if not isinstance(value, str):
                raise ValueError("Repeated database option")
            env[target] = value
    return env


def private_file(path, mode="wb"):
    # Exclusive create prevents symlink/overwrite accidents. Backups never enter Git.
    descriptor = os.open(Path(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    return os.fdopen(descriptor, mode)


def backup(settings, path, binary="pg_dump"):
    try:
        with private_file(path) as output:
            outcome = subprocess.run(  # noqa: S603 -- operator-owned binary, shell=False; no request input
                [binary, "--format=custom", "--no-owner", "--no-acl"],
                env=pg_environment(settings),
                stdout=output,
                stderr=subprocess.PIPE,
                timeout=120,
            )
        if outcome.returncode:
            raise RuntimeError("Backup failed; inspect database availability privately")
    except Exception:
        # Preserve existing files; remove only the file this call created.
        raise


def export_deletions(sessions, path):
    with sessions() as db:
        subjects = db.scalars(
            select(DeletionAudit.subject_id).order_by(DeletionAudit.subject_id)
        ).all()
    with private_file(path, "w") as output:
        json.dump({"version": 1, "subject_ids": subjects}, output)


def restore_test(settings, path, manifest, binary="pg_restore"):
    if settings.app_env != "test":
        raise ValueError("Automated replacement is restricted to the dedicated test database")
    data = json.loads(Path(manifest).read_text())
    if (
        set(data) != {"version", "subject_ids"}
        or data["version"] != 1
        or not isinstance(data["subject_ids"], list)
        or len(data["subject_ids"]) > 100000
    ):
        raise ValueError("Invalid deletion manifest")
    subjects = sorted({str(UUID(value)) for value in data["subject_ids"]})
    database = make_url(settings.database_url).database
    assert database is not None
    outcome = subprocess.run(  # noqa: S603 -- operator-owned binary, shell=False; no request input
        [
            binary,
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-acl",
            "--exit-on-error",
            "--dbname",
            database,
            str(path),
        ],
        env=pg_environment(settings),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        timeout=120,
    )
    if outcome.returncode:
        raise RuntimeError("Restore failed; service must remain offline")
    engine = make_engine(settings)
    try:
        sessions = sessionmaker(engine, expire_on_commit=False)
        with sessions.begin() as db:
            for subject in subjects:
                erase_subject(db, subject)
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Offline database maintenance")
    parser.add_argument("action", choices=["backup", "export-deletions", "restore-test"])
    parser.add_argument("path", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    settings = Settings()
    if args.action == "backup":
        return backup(settings, args.path)
    if args.action == "restore-test":
        if args.manifest is None:
            parser.error("--manifest is required")
        return restore_test(settings, args.path, args.manifest)
    engine = make_engine(settings)
    try:
        export_deletions(sessionmaker(engine), args.path)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
