"""Validate a local Overture snapshot; explicitly apply at most 30 places per kind."""

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from collect_overture import CITIES, RELEASE
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app import ingestion
from app.bulk_collect import check_readiness, load_settings, safe_error
from app.db import make_engine
from app.models import CityAlias, DataSource, ImportPermit, Place
from app.overture import adapt_record, import_snapshot, separate_duplicates

SOURCE = "Overture Maps Places — see source attribution"
LICENSE = "https://docs.overturemaps.org/attribution/"
FIELDS = {
    "external_id",
    "kind",
    "name",
    "source_url",
    "observed_at",
    "coordinates",
    "evidence",
    "address",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.snapshot.stat().st_size > 20_000_000:
        raise ValueError("SNAPSHOT_TOO_LARGE")
    snapshot = json.loads(args.snapshot.read_text())
    if (
        snapshot["release"] != RELEASE
        or snapshot["city"] not in CITIES.values()
        or len(snapshot["records"]) > 2000
    ):
        raise ValueError("SNAPSHOT_CONFIG_UNVERIFIED")
    cfg = snapshot["city"]
    observed = datetime.fromtimestamp(
        args.snapshot.stat().st_mtime, timezone.utc
    ).isoformat()
    engine = make_engine(load_settings(args.env_file))
    try:
        check_readiness(engine)
        sessions = sessionmaker(engine, expire_on_commit=False)
        with sessions() as db:
            city = db.scalar(
                select(CityAlias.city_id).where(
                    CityAlias.namespace == "wikidata",
                    CityAlias.external_id == cfg["qid"],
                )
            )
            if not city:
                raise ValueError("CITY_NOT_REGISTERED")
            existing = [
                {
                    "name": p.name,
                    "kind": p.kind,
                    "coordinates": {
                        "longitude": p.longitude,
                        "latitude": p.latitude,
                        "crs": p.coordinate_system,
                    }
                    if p.latitude is not None
                    else None,
                }
                for p in db.scalars(select(Place).where(Place.city_id == city))
            ]
            source = db.scalar(select(DataSource.id).where(DataSource.name == SOURCE))
        records = []
        rejected = Counter()
        for row in snapshot["records"]:
            try:
                records.append(
                    adapt_record(
                        row,
                        city_names=cfg["names"],
                        bounds=cfg["bounds"],
                        release=RELEASE,
                        observed_at=observed,
                    )
                )
            except (ValueError, KeyError, TypeError) as error:
                rejected[safe_error(error)] += 1
        accepted, review = separate_duplicates(records, existing)
        selected = []
        for kind in ("hotel", "restaurant"):
            selected.extend([r for r in accepted if r["kind"] == kind][:30])
        print(
            json.dumps(
                {
                    "accepted_before_dedup": len(records),
                    "held_for_duplicate_review": len(review),
                    "selected": dict(Counter(r["kind"] for r in selected)),
                    "rejected": dict(rejected),
                },
                ensure_ascii=False,
            )
        )
        if not args.apply or not selected:
            return
        if source is None:
            source = ingestion.register_policy(
                sessions,
                SOURCE,
                LICENSE,
                "Overture Places 2026-10-21.0; per-record CC0/CDLA-Permissive-2.0/Apache-2.0 evidence retained; no images or ratings; official attribution reviewed",
                FIELDS,
                computation_allowed=True,
            )
        with sessions() as db:
            ingestion.policy_for(db, source)
            permit = db.scalar(
                select(ImportPermit.id).where(ImportPermit.source_id == source)
            )
            cities = list(
                db.scalars(
                    select(CityAlias.city_id).where(
                        CityAlias.namespace == "wikidata",
                        CityAlias.external_id.in_([v["qid"] for v in CITIES.values()]),
                    )
                )
            )
        if permit is None:
            ingestion.grant_permit(
                sessions,
                source,
                cities,
                1000,
                "User approved free three-city hotel/restaurant pilot; 30 per kind per invocation",
            )
        print(
            json.dumps(
                {
                    "batches": import_snapshot(
                        sessions,
                        source,
                        city,
                        selected,
                        "Validated source license, locality, WGS84 point; nearby duplicates withheld; operating status may be unknown",
                    )
                },
                ensure_ascii=False,
            )
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"error": safe_error(error)}))
        raise SystemExit(1) from None
