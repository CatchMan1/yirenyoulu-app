"""Sequential, bounded Overture sample downloads; no credentials or database writes."""

import argparse
import json
import os
import tempfile
import threading
import time
from pathlib import Path

RELEASE = "2026-10-21.0"
URL = (
    "https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/release/"
    + RELEASE
    + "/theme=places/type=place/part-00015-eb1c1331-f519-5db6-8fef-74a77e5776ff-c000.zstd.parquet"
)
CITIES = {
    "beijing": {
        "qid": "Q956",
        "names": ["Beijing", "北京市", "北京"],
        "bounds": [116.35, 39.87, 116.45, 39.97],
    },
    "shanghai": {
        "qid": "Q8686",
        "names": ["Shanghai", "上海市", "上海"],
        "bounds": [121.43, 31.19, 121.53, 31.29],
    },
    "guangzhou": {
        "qid": "Q16572",
        "names": ["Guangzhou", "广州市", "广州"],
        "bounds": [113.23, 23.09, 113.33, 23.19],
    },
}
QUERY = """SELECT id,names,addresses,sources,operating_status,basic_category,taxonomy,bbox,version,confidence,hex(geometry) AS geometry_hex
FROM read_parquet(?) WHERE bbox.xmin BETWEEN ? AND ? AND bbox.ymin BETWEEN ? AND ?
AND (list_contains(taxonomy.hierarchy,'hotel') OR list_contains(taxonomy.hierarchy,'restaurant')) LIMIT 2000"""


def collect(cfg, output, url=URL):
    """Write one complete bounded snapshot; never overwrite an existing file."""
    import duckdb
    from overture_transport import paced_file

    if output.exists():
        raise ValueError("OUTPUT_ALREADY_EXISTS")
    c = duckdb.connect(config={"threads": 1, "memory_limit": "512MB"})
    timer = threading.Timer(900, c.interrupt)
    timer.daemon = True
    try:
        c.execute("LOAD httpfs")
        c.execute("SET http_timeout=30")
        c.execute("SET http_retries=1")
        time.sleep(10)
        timer.start()
        west, south, east, north = cfg["bounds"]
        with paced_file(url) as (local_url, budget):
            cur = c.execute(QUERY, [local_url, west, east, south, north])
            columns = [d[0] for d in cur.description]
            records = [dict(zip(columns, row)) for row in cur.fetchall()]
        print(json.dumps({"requests": budget.requests, "bytes": budget.bytes}))
        result = {
            "release": RELEASE,
            "city": cfg,
            "source_url": url,
            "records": records,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        temp = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=output.parent, delete=False) as f:
                temp = Path(f.name)
                json.dump(result, f, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.link(temp, output)
        finally:
            if temp:
                temp.unlink(missing_ok=True)
        print(
            json.dumps(
                {
                    "city": cfg["qid"],
                    "downloaded_candidates": len(records),
                    "path": str(output),
                }
            )
        )
    finally:
        timer.cancel()
        c.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--city", choices=list(CITIES), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    collect(CITIES[args.city], args.output)


if __name__ == "__main__":
    main()
