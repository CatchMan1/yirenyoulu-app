"""Trusted local operator commands. No public ingestion or approval endpoint."""

import argparse
import json
import os
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from . import ingestion as service
from .data_adapters import claims, osm_record, qid, wikidata_record
from .data_quality import quality_report
from .db import make_engine
from .http import utcnow
from .models import City, ImportRow, Place
from .settings import Settings
from .source_access import source_clause
from .wikidata_source import fetch_entities


def read_json(path):
    with Path(path).open("rb") as file:
        raw = file.read(10_000_001)
    if len(raw) > 10_000_000:
        raise ValueError("FILE_TOO_LARGE")
    return json.loads(raw)


def private_json(path, data):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def collect(sessions, source_id, city_id, city_qid, kind, ids, output):
    # This connector only handles CC0 structured facts; source review is independent of a permit.
    with sessions() as db:
        policy = service.policy_for(db, source_id)
        if policy.license_url != "https://creativecommons.org/publicdomain/zero/1.0/":
            raise ValueError("WIKIDATA_CC0_POLICY_REQUIRED")
        from .models import CityAlias, ImportPermit

        alias = db.scalar(
            select(CityAlias).where(
                CityAlias.city_id == city_id,
                CityAlias.namespace == "wikidata",
                CityAlias.external_id == qid(city_qid),
            )
        )
        permit = db.scalar(select(ImportPermit).where(ImportPermit.source_id == source_id))
        if not alias or not permit or city_id not in permit.city_ids:
            raise ValueError("CITY_PERMIT_REQUIRED")
    requested = list(dict.fromkeys([qid(city_qid), *[qid(v) for v in ids]]))
    entities = fetch_entities(sessions, source_id, requested)
    for _ in range(5):
        parents = {
            v.get("id")
            for entity in entities.values()
            for v in claims(entity, "P131")
            if isinstance(v, dict)
        }
        missing = sorted(p for p in parents if p and p not in entities)
        if not missing:
            break
        # Bounded ancestry lookup. Unknown locations stay rejected when the budget is reached.
        entities.update(fetch_entities(sessions, source_id, missing[:25]))
    records = []
    rejected = []
    observed = utcnow()
    for value in ids:
        try:
            record = wikidata_record(entities, value, city_qid, observed)
            if record["kind"] != kind:
                raise ValueError("KIND_MISMATCH")
            service.PlaceRecord.model_validate(record)
            records.append(record)
        except (ValueError, KeyError, TypeError):
            rejected.append({"external_id": value, "error": "SOURCE_EVIDENCE_INCOMPLETE"})
    manifest = {
        "source_id": source_id,
        "city_id": city_id,
        "kind": kind,
        "records": records,
        "rejected": rejected,
        "fetched_at": observed.isoformat(),
    }
    private_json(output, manifest)
    return {"accepted": len(records), "rejected": len(rejected), "output": str(output)}


def execute(args, sessions):
    action = args.action
    if action == "source":
        config = read_json(args.file)
        return {"source_id": service.register_policy(sessions, **config)}
    if action == "city":
        return {"city_id": service.register_city(sessions, **read_json(args.file))}
    if action == "permit":
        service.grant_permit(
            sessions,
            args.source,
            args.cities.split(","),
            args.limit,
            args.reference,
            max_requests=args.requests,
        )
        return {"permit": "recorded", "record_limit": args.limit}
    if action == "stage":
        data = read_json(args.file)
        if isinstance(data, dict):
            if any(
                data.get(key) != expected
                for key, expected in [
                    ("source_id", args.source),
                    ("city_id", args.city),
                    ("kind", args.kind),
                ]
            ):
                raise ValueError("MANIFEST_SCOPE_MISMATCH")
            data = data["records"]
        if not isinstance(data, list):
            raise ValueError("RECORD_LIST_REQUIRED")
        return {
            "batch_id": service.create_batch(
                sessions, args.source, args.city, args.kind, data, args.key
            )
        }
    if action == "approve":
        service.approve_batch(sessions, args.batch, args.reference)
        return {"review": "recorded"}
    if action == "apply":
        return service.apply_batch(sessions, args.batch, args.limit)
    if action == "report":
        result = service.report(sessions, args.batch)
        with sessions() as db:
            result["rows"] = [
                {
                    "row_id": row.id,
                    "external_id": row.external_id,
                    "status": row.status,
                    "error": row.error_code,
                }
                for row in db.scalars(
                    select(ImportRow)
                    .where(ImportRow.batch_id == args.batch)
                    .order_by(ImportRow.sequence)
                )
            ]
        return result
    if action == "resolve":
        service.resolve_duplicate(sessions, args.row, args.place, args.reference)
        return {"alias": "reviewed"}
    if action in {"revoke", "purge"}:
        service.revoke_source(sessions, args.source, purge=action == "purge")
        return {"source": "revoked", "purged": action == "purge"}
    if action == "expire":
        return service.expire_sources(sessions)
    if action == "fetch":
        return collect(
            sessions,
            args.source,
            args.city,
            args.city_qid,
            args.kind,
            args.ids.split(","),
            args.output,
        )
    if action == "map-osm":
        records = []
        rejected = 0
        for value in read_json(args.file)["elements"]:
            try:
                records.append(osm_record(value, args.city_name))
            except (ValueError, TypeError, KeyError):
                rejected += 1
        private_json(
            args.output,
            {
                "source_id": args.source,
                "city_id": args.city,
                "kind": args.kind,
                "records": [r for r in records if r["kind"] == args.kind],
            },
        )
        return {"mapped": len(records), "rejected": rejected}
    if action == "quality":
        return quality_report(sessions, city_id=args.city, stale_days=args.stale_days)
    if action == "coverage":
        with sessions() as db:
            rows = db.execute(
                select(Place.city_id, City.name, Place.kind, func.count())
                .join(City, City.id == Place.city_id)
                .where(Place.status == "active", source_clause())
                .group_by(Place.city_id, City.name, Place.kind)
                .order_by(City.name, Place.city_id, Place.kind)
            ).all()
            data = {}
            for city, name, kind, count in rows:
                if city not in data:
                    data[city] = {
                        "city_id": city,
                        "city_name": name,
                        "kinds": {},
                    }
                data[city]["kinds"][kind] = count
            return {
                "cities": list(data.values()),
                "note": "counts only, not city completeness or recommendation efficacy",
            }
    raise ValueError("UNKNOWN_ACTION")


def parser():
    root = argparse.ArgumentParser(
        description="Reviewed place data import; commands never grant supplier rights by themselves"
    )
    commands = root.add_subparsers(dest="action", required=True)
    for action in ["source", "city"]:
        item = commands.add_parser(action, help="register reviewed " + action + " from local JSON")
        item.add_argument("--file", type=Path, required=True)
    item = commands.add_parser(
        "permit", help="record product-approved city scope and cumulative record budget"
    )
    item.add_argument("--source", required=True)
    item.add_argument("--cities", required=True)
    item.add_argument("--limit", type=int, default=100)
    item.add_argument("--reference", required=True)
    item.add_argument("--requests", type=int, default=None)
    item = commands.add_parser(
        "stage", help="validate records into isolation; does not activate places"
    )
    for key in ["source", "city", "kind", "key"]:
        item.add_argument("--" + key, required=True)
    item.add_argument("--file", type=Path, required=True)
    for action in ["approve", "apply", "report"]:
        item = commands.add_parser(action)
        item.add_argument("--batch", required=True)
        if action == "approve":
            item.add_argument("--reference", required=True)
        if action == "apply":
            item.add_argument("--limit", type=int, default=None)
    item = commands.add_parser("resolve")
    item.add_argument("--row", required=True)
    item.add_argument("--place", required=True)
    item.add_argument("--reference", required=True)
    for action in ["revoke", "purge"]:
        item = commands.add_parser(action)
        item.add_argument("--source", required=True)
    item = commands.add_parser("fetch", help="small official Wikidata structured samples only")
    for key in ["source", "city", "city-qid", "kind", "ids"]:
        item.add_argument("--" + key, required=True)
    item.add_argument("--output", type=Path, required=True)
    item = commands.add_parser(
        "map-osm", help="map an already licensed offline JSON extract, no download"
    )
    for key in ["source", "city", "city-name", "kind"]:
        item.add_argument("--" + key, required=True)
    item.add_argument("--file", type=Path, required=True)
    item.add_argument("--output", type=Path, required=True)
    commands.add_parser("expire")
    commands.add_parser("coverage")
    item = commands.add_parser("quality", help="read-only city inventory and usable-fact quality")
    item.add_argument("--city", type=lambda value: str(UUID(value)), default=None)
    item.add_argument(
        "--stale-days", type=int, choices=range(1, 3651), metavar="1..3650", default=30
    )
    return root


def main():
    args = parser().parse_args()
    engine = make_engine(Settings())
    try:
        result = execute(args, sessionmaker(engine, expire_on_commit=False))
        print(json.dumps(result, ensure_ascii=False))
    except (ValueError, TypeError, KeyError, OSError, SQLAlchemyError):
        # Raw provider payloads, file contents and connection credentials are never printed.
        raise SystemExit(
            "DATA_OPERATION_FAILED: inspect input scope, source rights and private operator records"
        ) from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
