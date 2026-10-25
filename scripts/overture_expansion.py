"""Bounded city discovery, geographic grids and exclusive-ID page checkpoints."""

import json
import math
import re
import time
from urllib.parse import urlencode


def expanded_bounds(lon, lat, radius_km):
    if not 1 <= radius_km <= 100:
        raise ValueError("INVALID_RADIUS")
    dy = radius_km / 111.32
    dx = dy / math.cos(math.radians(lat))
    return [max(73, lon - dx), max(17, lat - dy), min(136, lon + dx), min(55, lat + dy)]


def tiles(bounds, tile_km):
    if not 5 <= tile_km <= 50:
        raise ValueError("INVALID_TILE_SIZE")
    w, s, e, n = bounds
    nx = max(1, math.ceil((e - w) * 111.32 * math.cos(math.radians((s + n) / 2)) / tile_km - 1e-9))
    ny = max(1, math.ceil((n - s) * 111.32 / tile_km - 1e-9))
    return [
        [
            w + (e - w) * x / nx,
            s + (n - s) * y / ny,
            e if x == nx - 1 else w + (e - w) * (x + 1) / nx,
            n if y == ny - 1 else s + (n - s) * (y + 1) / ny,
        ]
        for y in range(ny)
        for x in range(nx)
    ]


def discover_city_ids(client, fetch, checkpoint):
    """Include nested city candidates omitted by the previous parent-only manifest."""
    state = (
        json.loads(checkpoint.read_text())
        if checkpoint.exists()
        else {"ids": [], "cursor": None, "done": False}
    )
    while not state["done"]:
        cursor = state["cursor"]
        if cursor and not re.fullmatch(r"Q[1-9][0-9]*", cursor):
            raise ValueError("INVALID_DISCOVERY_CURSOR")
        after = f'FILTER(STR(?item) > "http://www.wikidata.org/entity/{cursor}")' if cursor else ""
        query = (
            """PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
SELECT DISTINCT ?item WHERE {
 ?item wdt:P17 wd:Q148 ; wdt:P31/wdt:P279* wd:Q515 .
 FILTER(?item NOT IN (wd:Q8646, wd:Q14773))
 FILTER NOT EXISTS { ?item wdt:P576 ?dissolved }
 """
            + after
            + "} ORDER BY STR(?item) LIMIT 100"
        )
        url = "https://query.wikidata.org/sparql?" + urlencode({"query": query, "format": "json"})
        rows = fetch(client, url)["results"]["bindings"]
        if len(rows) > 100:
            raise ValueError("INVALID_DISCOVERY_PAGE")
        ids = []
        for row in rows:
            value = row["item"]
            prefix = "http://www.wikidata.org/entity/"
            uri = value["value"]
            qid = uri.removeprefix(prefix)
            if (
                value["type"] != "uri"
                or not uri.startswith(prefix)
                or not re.fullmatch(r"Q[1-9][0-9]*", qid)
                or (cursor and qid <= cursor)
            ):
                raise ValueError("INVALID_DISCOVERY_PAGE")
            ids.append(qid)
            cursor = qid
        if len(state["ids"]) + len(ids) > 5000:
            raise ValueError("CITY_DISCOVERY_LIMIT")
        state["ids"].extend(ids)
        state["cursor"] = cursor
        state["done"] = len(ids) < 100
        temporary = checkpoint.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2))
        temporary.replace(checkpoint)
        print(
            json.dumps(
                {"event": "city_discovery", "candidates": len(state["ids"]), "done": state["done"]}
            ),
            flush=True,
        )
    return state["ids"]


def next_cursor(snapshot, after, page_size=2000):
    records = snapshot["records"]
    ids = [r["id"] for r in records]
    if (
        len(ids) > page_size
        or any(not isinstance(i, str) or not i for i in ids)
        or any(a >= b for a, b in zip(ids, ids[1:]))
        or (ids and after and ids[0] <= after)
    ):
        raise ValueError("INVALID_PAGE_ORDER")
    return ids[-1] if len(ids) == page_size else None


def collect_region(cfg, sources, args, catalog_path, collect, completed, apply_file):
    """Resume every tile/partition page; return failures and unfinished bounded work."""
    failures, limited = [], []
    for tile_no, bounds in enumerate(tiles(cfg["bounds"], args.tile_km)):
        matching = [
            p
            for p in sources
            if bounds[0] <= p["bounds"][2]
            and bounds[2] >= p["bounds"][0]
            and bounds[1] <= p["bounds"][3]
            and bounds[3] >= p["bounds"][1]
        ]
        if not matching:
            failures.append(f"{cfg['qid']}:tile{tile_no}:no_partition")
        for part in matching:
            partition = part["url"].rsplit("/", 1)[-1].split("-")[1]
            after = None
            for page in range(args.max_pages_per_tile):
                path = args.output_dir / f"{cfg['qid']}-{partition}-t{tile_no:04d}-p{page:04d}.json"
                try:
                    cached = completed(path, cfg, part["url"])
                    if cached:
                        snapshot = json.loads(path.read_text())
                        if snapshot.get("query_bounds") != bounds or snapshot.get("after") != after:
                            raise ValueError("PAGE_CONFIG_CHANGED")
                    else:
                        if getattr(args, "new_pages", 0) >= getattr(args, "max_new_pages", 1000):
                            return failures, limited + [
                                f"{cfg['qid']}:{partition}:tile{tile_no}:download_limit"
                            ]
                        args.new_pages = getattr(args, "new_pages", 0) + 1
                        print(
                            json.dumps(
                                {
                                    "event": "collecting_page",
                                    "city": cfg["qid"],
                                    "tile": tile_no,
                                    "page": page,
                                }
                            ),
                            flush=True,
                        )
                        collect(cfg, path, part["url"], query_bounds=bounds, after=after)
                        snapshot = json.loads(path.read_text())
                    cursor = next_cursor(snapshot, after)
                    if args.apply and not apply_file(path, catalog_path, args):
                        raise ValueError("SNAPSHOT_IMPORT_FAILED")
                    if not cached:
                        time.sleep(10)
                    if cursor is None:
                        break
                    after = cursor
                except Exception as error:
                    failures.append(str(path))
                    print(
                        json.dumps(
                            {
                                "event": "page_failed",
                                "path": str(path),
                                "error": type(error).__name__,
                            }
                        ),
                        flush=True,
                    )
                    break
            else:
                limited.append(f"{cfg['qid']}:{partition}:tile{tile_no}")
    return failures, limited
