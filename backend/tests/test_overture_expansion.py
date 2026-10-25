"""Geographic expansion and stable pagination, using synthetic places only."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def test_expansion_covers_30km_and_tiles_without_gaps():
    from overture_expansion import expanded_bounds, tiles

    b = expanded_bounds(116.4, 39.9, 30)
    assert b[0] < 116.1 and b[2] > 116.7
    assert b[1] < 39.65 and b[3] > 40.15
    grid = tiles(b, 20)
    assert len(grid) == 9
    assert min(t[0] for t in grid) == b[0]
    assert max(t[2] for t in grid) == b[2]
    assert sum((t[2] - t[0]) * (t[3] - t[1]) for t in grid) == pytest.approx(
        (b[2] - b[0]) * (b[3] - b[1])
    )


def test_city_discovery_merges_nested_city_candidates_and_resumes(tmp_path):
    from overture_expansion import discover_city_ids

    calls = []

    def fetch(client, url):
        calls.append(url)
        return {
            "results": {
                "bindings": [
                    {"item": {"type": "uri", "value": "http://www.wikidata.org/entity/Q200"}}
                ]
            }
        }

    assert discover_city_ids(None, fetch, tmp_path / "discovery.json") == ["Q200"]
    assert discover_city_ids(
        None,
        lambda *args: pytest.fail("Completed discovery must be cached"),
        tmp_path / "discovery.json",
    ) == ["Q200"]
    assert "P31" in calls[0] and "P17" in calls[0]


def test_page_cursor_requires_strictly_increasing_ids():
    from overture_expansion import next_cursor

    assert next_cursor({"records": [{"id": "a"}, {"id": "b"}]}, None, page_size=2) == "b"
    assert next_cursor({"records": [{"id": "c"}]}, "b", page_size=2) is None
    with pytest.raises(ValueError):
        next_cursor({"records": [{"id": "a"}, {"id": "b"}]}, "b", page_size=2)


def test_query_pages_do_not_repeat_boundary_id():
    duckdb = pytest.importorskip("duckdb")
    from collect_overture import PAGE_QUERY

    with duckdb.connect() as c:
        c.execute(
            "CREATE TABLE records AS SELECT * FROM (VALUES ('a', {'xmin': 116.4, 'ymin':39.9}, {'hierarchy':['hotel']}), ('b', {'xmin':116.4,'ymin':39.9}, {'hierarchy':['hotel']})) t(id,bbox,taxonomy)"
        )
        q = "SELECT id " + PAGE_QUERY[PAGE_QUERY.index("FROM ") :]
        q = q.replace("read_parquet(?)", "records")
        rows = c.execute(q, [116.0, 117.0, 39.0, 40.0, "a"]).fetchall()
        assert rows == [("b",)]


def test_saturated_tile_reports_incomplete_then_resumes_next_page(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace

    import overture_expansion as expansion
    from collect_overture import RELEASE
    from collect_overture_batch import completed

    cfg = {"qid": "Q100", "names": ["TEST City"], "bounds": [116.4, 39.9, 116.41, 39.91]}
    sources = [
        {"url": "https://example.test/part-00015-test.parquet", "bounds": [104, 18, 180, 77]}
    ]
    args = SimpleNamespace(tile_km=20, max_pages_per_tile=1, output_dir=tmp_path, apply=True)
    calls = []
    imports = []
    monkeypatch.setattr(expansion.time, "sleep", lambda seconds: None)

    def download(cfg, path, url, *, query_bounds, after):
        calls.append(after)
        ids = [f"{i:05}" for i in range(2000)] if after is None else ["02000"]
        path.write_text(
            json.dumps(
                {
                    "release": RELEASE,
                    "city": cfg,
                    "source_url": url,
                    "query_bounds": query_bounds,
                    "after": after,
                    "records": [{"id": i} for i in ids],
                }
            )
        )

    def apply(path, catalog, args):
        imports.append(path.name)
        return True

    failed, limited = expansion.collect_region(
        cfg, sources, args, tmp_path / "cities.json", download, completed, apply
    )
    assert failed == [] and limited
    args.max_pages_per_tile = 2
    assert expansion.collect_region(
        cfg, sources, args, tmp_path / "cities.json", download, completed, apply
    ) == ([], [])
    assert calls == [None, "01999"]
    assert len(imports) == 3  # Cached pages still receive idempotent import.


def test_run_download_guard_stops_before_network(tmp_path):
    from types import SimpleNamespace

    from overture_expansion import collect_region

    cfg = {"qid": "Q100", "names": ["TEST City"], "bounds": [116.4, 39.9, 116.41, 39.91]}
    sources = [
        {"url": "https://example.test/part-00015-test.parquet", "bounds": [104, 18, 180, 77]}
    ]
    args = SimpleNamespace(
        tile_km=20,
        max_pages_per_tile=10,
        output_dir=tmp_path,
        apply=False,
        new_pages=1,
        max_new_pages=1,
    )
    failed, limited = collect_region(
        cfg,
        sources,
        args,
        tmp_path / "cities.json",
        lambda *a, **kw: pytest.fail("Download guard must run before collection"),
        lambda *a: False,
        lambda *a: True,
    )
    assert failed == [] and limited
