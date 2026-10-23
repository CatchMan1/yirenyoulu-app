"""Free-source expansion: freeze a city catalog, then reuse one durable job per city."""

import argparse
import json
import os
import tempfile
import time
from datetime import timedelta
from pathlib import Path

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from . import bulk_collection as bulk
from . import ingestion as imports
from .bulk_collect import check_readiness, emit, load_settings, safe_error
from .data_adapters import claims, qid
from .db import make_engine
from .http import aware, utcnow
from .models import CollectionRun, DataSource, ImportPermit
from .wikidata_discovery import discover_cities
from .wikidata_source import fetch_entities

MAX_BUDGET = 100000
CITY_ERRORS = {"CITY_COUNTRY_UNVERIFIED", "CITY_TYPE_UNVERIFIED", "LABEL_MISSING"}
TOTALS = (
    "discovered",
    "accepted",
    "rejected",
    "staged",
    "applied",
    "inserted",
    "updated",
    "duplicate",
    "skipped",
)


class CountryConfig(bulk.BulkConfig):
    run_key: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,59}$")
    cities: list[str] = Field(min_length=1, max_length=5000)


def _child(config: CountryConfig, city: str) -> bulk.BulkConfig:
    values = config.model_dump(mode="json")
    digest = imports.fingerprint(values)
    values.update(
        cities=[city],
        run_key=config.run_key + ":" + city,
        review_reference="Country config " + digest + "; " + config.review_reference[:400],
    )
    return bulk.BulkConfig.model_validate(values)


def execute_country(sessions, config: CountryConfig, apply=False, on_progress=None) -> dict:
    children = {city: _child(config, city) for city in config.cities}
    # Check the entire manifest before a changed file can create any new child jobs.
    with sessions() as db:
        source = db.scalar(select(DataSource.id).where(DataSource.name == bulk.SOURCE_NAME))
        existing = (
            list(
                db.scalars(
                    select(CollectionRun).where(
                        CollectionRun.source_id == source,
                        CollectionRun.run_key.startswith(config.run_key + ":", autoescape=True),
                    )
                )
            )
            if source
            else []
        )
        hashes = {
            value.run_key: imports.fingerprint(value.model_dump(mode="json"))
            for value in children.values()
        }
        if any(hashes.get(row.run_key) != row.config_hash for row in existing):
            raise ValueError("CONFIG_CHANGED")
    result = {key: 0 for key in TOTALS}
    completed, failures = 0, []
    for city, child in children.items():
        run_id = bulk.start_run(sessions, child)
        if on_progress:
            on_progress({"event": "city_started", "city_qid": city, "run_id": run_id})
        try:
            report = bulk.execute_run(
                sessions,
                run_id,
                apply=apply,
                on_progress=(
                    lambda report, city=city: on_progress(
                        {"event": "city_progress", "city_qid": city, **report}
                    )
                )
                if on_progress
                else None,
            )
        except ValueError as error:
            if str(error) not in CITY_ERRORS:
                raise
            failures.append({"city_qid": city, "run_id": run_id, "error": str(error)})
            if on_progress:
                on_progress({"event": "city_failed", **failures[-1]})
            continue
        completed += 1
        for key in TOTALS:
            result[key] += report[key]
        if on_progress:
            on_progress({"event": "city_finished", "city_qid": city, **report})
    return {
        "status": "partial" if failures else "completed" if apply else "staged",
        "run_key": config.run_key,
        "configured_cities": len(children),
        "completed_cities": completed,
        "failed_cities": len(failures),
        "failures": failures,
        **result,
    }


def _catalog_source(sessions):
    source = bulk._source_id(sessions, "Free Wikidata city catalog and bounded country expansion")
    with sessions.begin() as db:
        policy = imports.policy_for(db, source, True)
        if policy.license_url != bulk.CC0:
            raise ValueError("SOURCE_POLICY_REVIEW_REQUIRED")
        permit = db.scalar(select(ImportPermit).where(ImportPermit.source_id == source))
        if permit:
            if aware(permit.expires_at) <= utcnow():
                raise ValueError("PERMIT_EXPIRED_REVIEW_REQUIRED")
            permit.max_records = permit.max_requests = MAX_BUDGET
        else:
            db.add(
                ImportPermit(
                    source_id=source,
                    city_ids=[],
                    max_records=MAX_BUDGET,
                    max_requests=MAX_BUDGET,
                    reference="Free country catalog; no place import during preparation",
                    expires_at=utcnow() + timedelta(days=7),
                )
            )
    return source


def top_level_cities(sessions, source, cities: list[str], transport=None) -> list[str]:
    # Keep the public SPARQL query cheap; resolve parent evidence in bounded API batches.
    candidates = set(cities)
    graph: dict[str, set[str] | None] = {}
    pending = set(cities)
    for _ in range(10):
        if not pending:
            break
        if len(graph) + len(pending) > 10000:
            raise ValueError("CITY_HIERARCHY_LIMIT")
        requested = sorted(pending)
        for offset in range(0, len(requested), 25):
            time.sleep(2)
            ids = requested[offset : offset + 25]
            entities = fetch_entities(sessions, source, ids, transport=transport)
            for item in ids:
                value = entities.get(item)
                graph[item] = (
                    {
                        qid(parent["id"])
                        for parent in claims(value, "P131")
                        if isinstance(parent, dict) and isinstance(parent.get("id"), str)
                    }
                    if value and "missing" not in value
                    else None
                )
        pending = {
            parent for edges in graph.values() if edges for parent in edges if parent not in graph
        }
    selected = []
    for city in cities:
        todo, visited, valid = [city], set(), True
        while todo:
            item = todo.pop()
            if item in visited:
                continue
            visited.add(item)
            if item in {"Q8646", "Q14773"} or (item != city and item in candidates):
                valid = False
                break
            parents = graph.get(item)
            if parents is None or city in parents:
                valid = False
                break
            todo.extend(parents)
        if valid:
            selected.append(city)
    return selected


def prepare_config(sessions, output: Path, run_key: str, transport=None) -> dict:
    if output.exists():
        raise ValueError("OUTPUT_EXISTS")
    # Validate user parameters before policy/permit changes or requests.
    CountryConfig(run_key=run_key, cities=["Q956"], review_reference="Catalog parameter validation")
    output.parent.mkdir(parents=True, exist_ok=True)
    source = _catalog_source(sessions)
    cities: list[str] = []
    cursor = None
    while True:
        time.sleep(2)
        page = discover_cities(sessions, source, cursor=cursor, transport=transport)
        cities.extend(page.ids)
        if len(cities) > 5000 or (len(cities) == 5000 and page.next_cursor):
            raise ValueError("CITY_CATALOG_LIMIT")
        if page.next_cursor is None:
            break
        cursor = page.next_cursor
    discovered_count = len(cities)
    cities = top_level_cities(sessions, source, cities, transport)
    if not cities:
        raise ValueError("CITY_CATALOG_EMPTY")
    config = CountryConfig(
        run_key=run_key,
        cities=cities,
        per_city_kind_limit=10000,
        record_budget=MAX_BUDGET,
        request_budget=MAX_BUDGET,
        interval_seconds=2,
        review_reference="Free Wikidata CC0 structured data; country city candidates require raw entity verification; unknown facts remain unknown",
    )
    payload = (
        json.dumps(config.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    ).encode()
    # Publish only the complete file, atomically and without replacing user input.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output.parent, prefix=".city-catalog-", delete=False
        ) as file:
            temporary = Path(file.name)
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        try:
            os.link(temporary, output)
        except FileExistsError:
            raise ValueError("OUTPUT_EXISTS") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {
        "cities": len(cities),
        "discovered_city_candidates": discovered_count,
        "excluded_or_unresolved": discovered_count - len(cities),
        "config": str(output),
        "run_key": run_key,
        "record_budget": MAX_BUDGET,
        "request_budget": MAX_BUDGET,
        "note": "Source-listed city candidates, not an authoritative complete administrative directory",
    }


def load_config(path: Path) -> CountryConfig:
    try:
        with path.open("rb") as file:
            raw = file.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError
        return CountryConfig.model_validate(json.loads(raw))
    except (OSError, ValueError, TypeError):
        raise ValueError("CONFIG_INVALID") from None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare free-source country city candidates and run resumable city jobs"
    )
    parser.add_argument("--env-file", type=Path)
    actions = parser.add_subparsers(dest="action", required=True)
    prepare = actions.add_parser("prepare")
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--run-key", default="mainland-expanded-001")
    run = actions.add_parser("run")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    engine = None
    try:
        config = load_config(args.config) if args.action == "run" else None
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
        check_readiness(engine)
        sessions = sessionmaker(engine, expire_on_commit=False)
        if args.action == "prepare":
            result = prepare_config(sessions, args.output, args.run_key)
            emit("catalog_prepared", **result)
            return 0
        assert config is not None
        result = execute_country(
            sessions,
            config,
            args.apply,
            on_progress=lambda value: print(json.dumps(value, ensure_ascii=False), flush=True),
        )
        emit("country_report", **result)
        return 1 if result["status"] == "partial" else 0
    except KeyboardInterrupt:
        emit(
            "interrupted",
            error="INTERRUPTED",
            hint="Rerun the same country config; child jobs retain their checkpoints",
        )
        return 130
    except Exception as error:
        emit(
            "error",
            error=safe_error(error),
            hint="Keep the same config to resume; no automatic paid fallback",
        )
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
