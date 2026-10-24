"""Local operator command for bounded, checkpointed city collection."""

import argparse
import json
import re
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from dotenv import dotenv_values
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from . import bulk_collection as service
from .db import make_engine
from .models import CollectionRun, DataSource
from .settings import Settings

ALEMBIC_CONFIG = Path(__file__).resolve().parents[1] / "alembic.ini"
ENV_KEYS = {"APP_ENV", "DATABASE_URL", "JWT_SECRET", "AI_PROVIDER", "MAIL_PROVIDER"}


def parser():
    root = argparse.ArgumentParser(
        description="Discover Wikidata places by city with bounded requests and checkpointed imports"
    )
    root.add_argument(
        "--env-file",
        type=Path,
        help="explicit environment file; selected values override the shell",
    )
    commands = root.add_subparsers(dest="action", required=True)
    item = commands.add_parser("run", help="start or continue the same immutable configuration")
    item.add_argument("--config", type=Path, required=True)
    item.add_argument("--apply", action="store_true", help="approve validated rows by fixed rules")
    item = commands.add_parser("resume", help="continue a saved run; no config file needed")
    item.add_argument("--run-id", required=True)
    item.add_argument("--apply", action="store_true", help="approve validated rows by fixed rules")
    item = commands.add_parser("status", help="read the saved report without provider requests")
    identity = item.add_mutually_exclusive_group(required=True)
    identity.add_argument("--run-id")
    identity.add_argument("--run-key")
    return root


def load_config(path):
    try:
        with path.open("rb") as file:
            raw = file.read(1_000_001)
    except OSError:
        raise ValueError("CONFIG_UNAVAILABLE") from None
    if len(raw) > 1_000_000:
        raise ValueError("CONFIG_TOO_LARGE")
    try:
        return service.BulkConfig.model_validate(json.loads(raw))
    except (ValueError, TypeError):
        # Validation errors include input values; never print them from operator commands.
        raise ValueError("CONFIG_INVALID") from None


def load_settings(env_file):
    values: dict[str, Any] = {}
    if env_file is not None:
        try:
            with env_file.open(encoding="utf-8") as file:
                values = {
                    key.lower(): value
                    for key, value in dotenv_values(stream=file, interpolate=False).items()
                    if key in ENV_KEYS and value is not None
                }
        except (OSError, UnicodeError):
            raise ValueError("SETTINGS_FILE_UNAVAILABLE") from None
    try:
        # BaseSettings already disables automatic .env discovery. Explicit kwargs win over env.
        return Settings(**values)
    except (ValidationError, ValueError, TypeError):
        raise ValueError("SETTINGS_INVALID") from None


def check_readiness(engine):
    expected = set(ScriptDirectory.from_config(Config(str(ALEMBIC_CONFIG))).get_heads())
    with engine.connect() as connection:
        actual = set(MigrationContext.configure(connection).get_current_heads())
    if not expected or actual != expected:
        raise ValueError("DATABASE_MIGRATION_REQUIRED")


def emit(event, **values):
    print(json.dumps({"event": event, **values}, ensure_ascii=False), flush=True)


def safe_error(error):
    if isinstance(error, SQLAlchemyError):
        return "STORAGE_UNAVAILABLE"
    value = str(error)
    return value if re.fullmatch(r"[A-Z][A-Z0-9_]{0,98}", value) else "COLLECTION_FAILED"


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    engine = None
    run_id = None
    try:
        if args.action == "run":
            config = load_config(args.config)
        settings = load_settings(args.env_file)
        target = make_url(settings.database_url)
        emit(
            "target",
            environment=settings.app_env,
            database=target.database,
            host=target.host,
            port=target.port or 5432,
        )
        engine = make_engine(settings)
        # This must precede source/policy/permit bootstrap as well as any provider request.
        check_readiness(engine)
        sessions = sessionmaker(bind=engine, expire_on_commit=False)
        if args.action == "run":
            run_id = service.start_run(sessions, config)
        elif args.action == "resume" or args.run_id:
            run_id = args.run_id
        else:
            with sessions() as db:
                run_id = db.scalar(
                    select(CollectionRun.id)
                    .join(DataSource, CollectionRun.source_id == DataSource.id)
                    .where(
                        DataSource.name == service.SOURCE_NAME,
                        CollectionRun.run_key == args.run_key,
                    )
                )
            if run_id is None:
                raise ValueError("RUN_NOT_FOUND")
        if args.action == "status":
            result = service.get_report(sessions, run_id)
        else:
            emit("run_started", run_id=run_id, apply=args.apply)
            result = service.execute_run(
                sessions,
                run_id,
                apply=args.apply,
                on_progress=lambda report: emit("progress", **report),
            )
        emit("report", **result)
        return 1 if result["status"] == "failed" else 0
    except KeyboardInterrupt:
        emit(
            "interrupted",
            error="INTERRUPTED",
            run_id=run_id,
            hint="Use resume --run-id with this run_id after checking status"
            if run_id
            else "No run was started; rerun the command after checking the database",
        )
        return 130
    except Exception as error:
        emit("error", error=safe_error(error), run_id=run_id)
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
