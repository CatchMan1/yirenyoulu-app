"""Serial hospitality collection with optional Chinese city discovery and grid paging."""

import argparse
import json
import math
import re
import subprocess
import sys
import time
from functools import partial
from pathlib import Path
from urllib.parse import urljoin

import httpx
from collect_overture import RELEASE, collect, validate_release
from overture_expansion import collect_region, discover_city_ids, expanded_bounds

STAC = f"https://stac.overturemaps.org/{RELEASE}/places/place/collection.json"


def overlaps(a, b):
    return a[0] <= b[2] and a[2] >= b[0] and a[1] <= b[3] and a[3] >= b[1]


def city_config(entity, radius_km=None):
    qid = entity["id"]
    if not re.fullmatch(r"Q[1-9][0-9]*", qid):
        raise ValueError("INVALID_CITY_ID")
    names = list(
        dict.fromkeys(
            entity.get("labels", {}).get(lang, {}).get("value")
            for lang in ("en", "zh", "zh-cn", "zh-hans")
            if entity.get("labels", {}).get(lang, {}).get("value")
        )
    )
    if not names:
        raise ValueError("CITY_LABEL_MISSING")
    claims = [c for c in entity.get("claims", {}).get("P625", []) if c.get("rank") != "deprecated"]
    preferred = [c for c in claims if c.get("rank") == "preferred"]
    claims = preferred or claims
    points = set()
    for claim in claims:
        v = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
        if v.get("globe") != "http://www.wikidata.org/entity/Q2":
            continue
        lon, lat = v.get("longitude"), v.get("latitude")
        if isinstance(lon, (int, float)) and isinstance(lat, (int, float)):
            if math.isfinite(lon) and math.isfinite(lat) and 73 <= lon <= 135 and 18 <= lat <= 54:
                points.add((lon, lat))
    if len(points) != 1:
        raise ValueError("CITY_COORDINATE_MISSING_OR_AMBIGUOUS")
    lon, lat = points.pop()
    return {
        "qid": qid,
        "names": names,
        "bounds": expanded_bounds(lon, lat, radius_km)
        if radius_km
        else [lon - 0.05, lat - 0.05, lon + 0.05, lat + 0.05],
    }


def completed(path, cfg, url, *, release=RELEASE):
    try:
        s = json.loads(path.read_text())
        return (
            s["release"] == release
            and s["city"] == cfg
            and s["source_url"] == url
            and isinstance(s["records"], list)
            and len(s["records"]) <= 2000
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def get_json(client, url):
    # Sequential metadata requests, with bounded retries and response size.
    for attempt in range(3):
        time.sleep(2 * (attempt + 1))
        try:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 5_000_000:
                        raise ValueError("METADATA_TOO_LARGE")
            return json.loads(body)
        except httpx.HTTPError:
            if attempt == 2:
                raise


def partitions(client, release=RELEASE):
    validate_release(release)
    stac = f"https://stac.overturemaps.org/{release}/places/place/collection.json"
    result = []
    for link in get_json(client, stac)["links"]:
        if link["rel"] != "item":
            continue
        item_url = urljoin(stac, link["href"])
        if not item_url.startswith(f"https://stac.overturemaps.org/{release}/"):
            raise ValueError("UNEXPECTED_CATALOG_URL")
        item = get_json(client, item_url)
        for asset in item["assets"].values():
            url = asset.get("href", "")
            prefix = f"https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/release/{release}/theme=places/type=place/"
            if url.startswith(prefix) and url.endswith(".parquet"):
                result.append({"bounds": item["bbox"], "url": url})
                break
    if not result:
        raise ValueError("NO_SOURCE_PARTITIONS")
    return result


def apply_file(path, catalog, args):
    command = [
        sys.executable,
        str(Path(__file__).with_name("import_overture.py")),
        "--snapshot",
        str(path),
        "--catalog",
        str(catalog),
        "--env-file",
        str(args.env_file),
        "--apply",
    ]
    if args.max_records is not None:
        command.extend(["--max-records", str(args.max_records)])
    if getattr(args, "refresh_existing", False):
        command.append("--refresh-existing")
    result = subprocess.run(command, check=False)  # noqa: S603 -- fixed Python/script; argv, no shell
    print(
        json.dumps(
            {"event": "snapshot_import", "path": str(path), "success": result.returncode == 0}
        ),
        flush=True,
    )
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release",
        type=validate_release,
        help="Explicit reviewed YYYY-MM-DD.N release; defaults to the pinned version",
    )
    parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help="Explicitly update existing same-source records; requires apply",
    )
    parser.add_argument("--cities", type=Path, default=Path(".local-data/wikidata-country.json"))
    parser.add_argument("--output-dir", type=Path, default=Path(".local-data/overture/country"))
    parser.add_argument(
        "--prepare-only", action="store_true", help="Generate list without collecting places"
    )
    parser.add_argument(
        "--apply", action="store_true", help="Validate and import each downloaded snapshot"
    )
    parser.add_argument(
        "--env-file", type=Path, help="Explicit database environment file, required for apply"
    )
    parser.add_argument(
        "--import-only", action="store_true", help="Import existing local snapshots without network"
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=None,
        help="Explicit cumulative source import budget; omitted preserves existing allowance",
    )
    parser.add_argument(
        "--discover-cities",
        action="store_true",
        help="Discover additional Chinese city candidates, including nested cities",
    )
    parser.add_argument(
        "--radius-km",
        type=float,
        help="Centre-to-edge km of search rectangle (1..100); enables grid paging",
    )
    parser.add_argument("--tile-km", type=float, default=20, help="Grid edge length in km (5..50)")
    parser.add_argument(
        "--max-pages-per-tile",
        type=int,
        default=10,
        help="Page ceiling per tile/partition; capped pages are reported incomplete",
    )
    parser.add_argument(
        "--max-new-pages",
        type=int,
        default=1000,
        help="New page attempts per invocation (1..100000); rerun to continue",
    )
    args = parser.parse_args()
    args.new_pages = 0
    if args.refresh_existing and not args.apply:
        parser.error("refresh-existing requires apply")
    if args.import_only:
        catalog_path = args.output_dir / "cities.json"
        if not catalog_path.exists():
            parser.error("Missing cities.json in output-dir")
        catalog_release = validate_release(json.loads(catalog_path.read_text())["release"])
        if args.release is not None and args.release != catalog_release:
            parser.error("Catalog release differs from explicit release")
        args.release = catalog_release
    else:
        args.release = args.release or RELEASE
    if not 1 <= args.max_new_pages <= 100000:
        parser.error("max-new-pages must be 1..100000")
    if (
        (args.radius_km is not None and not 1 <= args.radius_km <= 100)
        or not 5 <= args.tile_km <= 50
        or not 1 <= args.max_pages_per_tile <= 100
    ):
        parser.error("radius 1..100 km; tile 5..50 km; pages 1..100")
    if (
        (args.apply and not args.env_file)
        or (args.import_only and not args.apply)
        or (args.prepare_only and args.apply)
    ):
        parser.error(
            "apply requires env-file; import-only requires apply; prepare-only cannot apply"
        )
    if args.max_records is not None and not 1 <= args.max_records <= 100000:
        parser.error("max-records must be 1..100000")
    if args.apply:
        from app.bulk_collect import check_readiness, load_settings
        from app.db import make_engine

        engine = make_engine(load_settings(args.env_file))
        try:
            check_readiness(engine)
        finally:
            engine.dispose()
    if args.import_only:
        catalog = args.output_dir / "cities.json"
        if not catalog.exists():
            parser.error("Missing cities.json in output-dir")
        paths = sorted(args.output_dir.glob("Q*-*.json"))
        if not paths:
            parser.error("No downloaded city snapshots found")
        failed = [str(path) for path in paths if not apply_file(path, catalog, args)]
        print(
            json.dumps({"event": "import_finished", "files": len(paths), "failed": failed}),
            flush=True,
        )
        if failed:
            raise SystemExit(1)
        return
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.discover_cities:
        with httpx.Client(
            timeout=30,
            follow_redirects=False,
            headers={
                "User-Agent": "YirenYouLu/0.2 (https://github.com/CatchMan1/yirenyoulu-app)",
                "Accept": "application/sparql-results+json",
            },
        ) as client:
            discovered = discover_city_ids(
                client, get_json, args.output_dir / "city-discovery.json"
            )
    else:
        discovered = []
    previous = json.loads(args.cities.read_text())["cities"] if args.cities.exists() else []
    ids = (
        sorted(set(previous) | set(discovered))
        if args.discover_cities
        else list(dict.fromkeys(previous))
    )
    if not ids or len(ids) > 5000 or any(not re.fullmatch(r"Q[1-9][0-9]*", q) for q in ids):
        parser.error("Expected 1..5000 Wikidata city IDs")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = args.output_dir / "cities.json"
    if catalog_path.exists():
        catalog = json.loads(catalog_path.read_text())
        if (
            catalog["release"] != args.release
            or catalog["requested"] != ids
            or catalog.get("radius_km") != args.radius_km
            or catalog.get("tile_km", 20) != args.tile_km
        ):
            parser.error("City list/release changed; choose a new output directory")
    else:
        catalog = {
            "release": args.release,
            "requested": ids,
            "cities": {},
            "skipped": {},
            "radius_km": args.radius_km,
            "tile_km": args.tile_km,
        }
    with httpx.Client(
        timeout=30,
        follow_redirects=False,
        headers={"User-Agent": "YirenYouLu/0.2 (https://github.com/CatchMan1/yirenyoulu-app)"},
    ) as client:
        for qid in ids:
            if qid in catalog["cities"]:
                continue
            try:
                entity = get_json(
                    client,
                    f"https://www.wikidata.org/w/api.php?action=wbgetentities&ids={qid}&props=labels%7Cclaims&languages=en%7Czh%7Czh-cn%7Czh-hans&format=json&maxlag=5",
                )["entities"][qid]
                catalog["cities"][qid] = city_config(entity, args.radius_km)
                catalog["skipped"].pop(qid, None)
            except (ValueError, KeyError, httpx.HTTPError) as error:
                catalog["skipped"][qid] = (
                    str(error)
                    if re.fullmatch(r"[A-Z][A-Z0-9_]{0,98}", str(error))
                    else type(error).__name__
                )
            temporary = catalog_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(catalog, ensure_ascii=False, indent=2))
            temporary.replace(catalog_path)
            print(
                json.dumps(
                    {"event": "city_prepared", "city": qid, "ready": qid in catalog["cities"]}
                ),
                flush=True,
            )
        print(
            json.dumps(
                {
                    "event": "catalog",
                    "ready": len(catalog["cities"]),
                    "skipped": catalog["skipped"],
                    "path": str(catalog_path),
                }
            ),
            flush=True,
        )
        if args.prepare_only:
            return
        sources = partitions(client, args.release)
    failures = []
    limited = []
    for qid, cfg in catalog["cities"].items():
        if args.radius_km is not None:
            failed_pages, limited_tiles = collect_region(
                cfg,
                sources,
                args,
                catalog_path,
                partial(collect, release=args.release),
                partial(completed, release=args.release),
                apply_file,
            )
            failures.extend(failed_pages)
            limited.extend(limited_tiles)
            if any("download_limit" in value for value in limited_tiles):
                break
            continue
        matching = [p for p in sources if overlaps(cfg["bounds"], p["bounds"])]
        if not matching:
            failures.append(qid)
        for part in matching:
            path = args.output_dir / f"{qid}-{Path(part['url']).name.split('-')[1]}.json"
            if completed(path, cfg, part["url"], release=args.release):
                print(json.dumps({"event": "already_downloaded", "city": qid}), flush=True)
                if args.apply and not apply_file(path, catalog_path, args):
                    failures.append(qid)
                continue
            if args.new_pages >= args.max_new_pages:
                limited.append(f"{qid}:download_limit")
                break
            args.new_pages += 1
            print(
                json.dumps(
                    {"event": "collecting", "city": qid, "names": cfg["names"]}, ensure_ascii=False
                ),
                flush=True,
            )
            try:
                collect(cfg, path, part["url"], release=args.release)
                if args.apply and not apply_file(path, catalog_path, args):
                    failures.append(qid)
            except Exception as error:
                failures.append(qid)
                print(
                    json.dumps({"event": "failed", "city": qid, "error": type(error).__name__}),
                    flush=True,
                )
            time.sleep(10)
        if any("download_limit" in value for value in limited):
            break
    report = {
        "event": "batch_finished",
        "release": args.release,
        "refresh_existing": args.refresh_existing,
        "failed": sorted(set(failures)),
        "skipped": catalog["skipped"],
        "coverage": "grid-paged centre rectangle"
        if args.radius_km
        else "city-centre samples, at most 2000 per partition",
        "radius_km": args.radius_km,
        "limited_tiles": limited,
        "new_page_attempts": args.new_pages,
        "max_new_pages": args.max_new_pages,
    }
    (args.output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report), flush=True)
    if failures or limited or catalog["skipped"]:
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        from app.bulk_collect import safe_error

        print(json.dumps({"event": "error", "error": safe_error(error)}), flush=True)
        raise SystemExit(1) from None
