"""Serial city-centre hospitality samples from a local Wikidata city manifest."""

import argparse
import json
import math
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import httpx
from collect_overture import RELEASE, collect

STAC = f"https://stac.overturemaps.org/{RELEASE}/places/place/collection.json"


def overlaps(a, b):
    return a[0] <= b[2] and a[2] >= b[0] and a[1] <= b[3] and a[3] >= b[1]


def city_config(entity):
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
    return {"qid": qid, "names": names, "bounds": [lon - 0.05, lat - 0.05, lon + 0.05, lat + 0.05]}


def completed(path, cfg, url):
    try:
        s = json.loads(path.read_text())
        return (
            s["release"] == RELEASE
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


def partitions(client):
    result = []
    for link in get_json(client, STAC)["links"]:
        if link["rel"] != "item":
            continue
        item_url = urljoin(STAC, link["href"])
        if not item_url.startswith(f"https://stac.overturemaps.org/{RELEASE}/"):
            raise ValueError("UNEXPECTED_CATALOG_URL")
        item = get_json(client, item_url)
        for asset in item["assets"].values():
            url = asset.get("href", "")
            prefix = f"https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/release/{RELEASE}/theme=places/type=place/"
            if url.startswith(prefix) and url.endswith(".parquet"):
                result.append({"bounds": item["bbox"], "url": url})
                break
    if not result:
        raise ValueError("NO_SOURCE_PARTITIONS")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cities", type=Path, default=Path(".local-data/wikidata-country.json"))
    parser.add_argument("--output-dir", type=Path, default=Path(".local-data/overture/country"))
    parser.add_argument(
        "--prepare-only", action="store_true", help="Generate list without collecting places"
    )
    args = parser.parse_args()
    ids = list(dict.fromkeys(json.loads(args.cities.read_text())["cities"]))
    if not ids or len(ids) > 5000 or any(not re.fullmatch(r"Q[1-9][0-9]*", q) for q in ids):
        parser.error("Expected 1..5000 Wikidata city IDs")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = args.output_dir / "cities.json"
    if catalog_path.exists():
        catalog = json.loads(catalog_path.read_text())
        if catalog["release"] != RELEASE or catalog["requested"] != ids:
            parser.error("City list/release changed; choose a new output directory")
    else:
        catalog = {"release": RELEASE, "requested": ids, "cities": {}, "skipped": {}}
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
                catalog["cities"][qid] = city_config(entity)
                catalog["skipped"].pop(qid, None)
            except (ValueError, KeyError, httpx.HTTPError) as error:
                catalog["skipped"][qid] = type(error).__name__
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
        sources = partitions(client)
    failures = []
    for qid, cfg in catalog["cities"].items():
        matching = [p for p in sources if overlaps(cfg["bounds"], p["bounds"])]
        if not matching:
            failures.append(qid)
        for part in matching:
            path = args.output_dir / f"{qid}-{Path(part['url']).name.split('-')[1]}.json"
            if completed(path, cfg, part["url"]):
                print(json.dumps({"event": "already_downloaded", "city": qid}), flush=True)
                continue
            print(
                json.dumps(
                    {"event": "collecting", "city": qid, "names": cfg["names"]}, ensure_ascii=False
                ),
                flush=True,
            )
            try:
                collect(cfg, path, part["url"])
            except Exception as error:
                failures.append(qid)
                print(
                    json.dumps({"event": "failed", "city": qid, "error": type(error).__name__}),
                    flush=True,
                )
            time.sleep(10)
    report = {
        "event": "batch_finished",
        "failed": sorted(set(failures)),
        "skipped": catalog["skipped"],
        "coverage": "city-centre samples, at most 2000 per partition",
    }
    (args.output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report), flush=True)
    if failures or catalog["skipped"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
