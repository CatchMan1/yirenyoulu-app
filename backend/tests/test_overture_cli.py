"""Release boundaries and offline refresh wiring; no remote requests or database writes."""

import json
from types import SimpleNamespace

import pytest


def test_release_calendar_and_partition_allowlist(monkeypatch):
    import collect_overture_batch as batch
    from collect_overture import validate_release

    assert validate_release("2026-10-21.0") == "2026-10-21.0"
    for invalid in ("2026-02-30.0", "2026-1-01.0", "../latest", "2026-10-21.0/evil"):
        with pytest.raises(ValueError, match="INVALID_RELEASE"):
            validate_release(invalid)
    release = "2026-09-23.0"
    stac = f"https://stac.overturemaps.org/{release}/places/place/collection.json"
    data_url = f"https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/release/{release}/theme=places/type=place/part-00001-test.parquet"
    requested = []

    def fetch(client, url):
        requested.append(url)
        if url == stac:
            return {"links": [{"rel": "item", "href": "./part-00001.json"}]}
        return {"bbox": [73, 17, 136, 55], "assets": {"data": {"href": data_url}}}

    monkeypatch.setattr(batch, "get_json", fetch)
    assert batch.partitions(None, release) == [{"bounds": [73, 17, 136, 55], "url": data_url}]
    assert requested == [stac, stac.rsplit("/", 1)[0] + "/part-00001.json"]
    monkeypatch.setattr(
        batch,
        "get_json",
        lambda *a: {"links": [{"rel": "item", "href": "https://example.invalid/escape.json"}]},
    )
    with pytest.raises(ValueError, match="UNEXPECTED_CATALOG_URL"):
        batch.partitions(None, release)


def test_offline_refresh_uses_catalog_release_and_rejects_mismatch(tmp_path, monkeypatch):
    import sys

    import collect_overture_batch as batch

    import app.bulk_collect as bulk
    import app.db as db

    release = "2026-09-23.0"
    (tmp_path / "cities.json").write_text(json.dumps({"release": release}))
    (tmp_path / "Q956-00001.json").write_text("{}")
    monkeypatch.setattr(bulk, "load_settings", lambda path: None)
    monkeypatch.setattr(bulk, "check_readiness", lambda engine: None)
    monkeypatch.setattr(db, "make_engine", lambda settings: SimpleNamespace(dispose=lambda: None))
    monkeypatch.setattr(
        batch.httpx, "Client", lambda *a, **k: pytest.fail("Offline import opened network")
    )
    commands = []
    monkeypatch.setattr(
        batch.subprocess,
        "run",
        lambda argv, **kw: commands.append(argv) or SimpleNamespace(returncode=0),
    )
    argv = [
        "collect_overture_batch.py",
        "--import-only",
        "--apply",
        "--refresh-existing",
        "--env-file",
        str(tmp_path / ".env"),
        "--output-dir",
        str(tmp_path),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    batch.main()
    assert len(commands) == 1 and "--refresh-existing" in commands[0]
    assert "--max-records" not in commands[0]
    monkeypatch.setattr(sys, "argv", argv + ["--max-records", "77"])
    batch.main()
    assert len(commands) == 2
    assert commands[1][commands[1].index("--max-records") + 1] == "77"
    monkeypatch.setattr(sys, "argv", argv + ["--release", "2026-10-21.0"])
    with pytest.raises(SystemExit) as error:
        batch.main()
    assert error.value.code == 2 and len(commands) == 2


def test_snapshot_download_has_fixed_observation_and_release(tmp_path, monkeypatch):
    import sys
    from contextlib import contextmanager
    from datetime import datetime

    import collect_overture as collector
    import overture_transport

    class Connection:
        description = [("id",)]

        def execute(self, *args):
            return self

        def fetchall(self):
            return [("test-only",)]

        def interrupt(self):
            pass

        def close(self):
            pass

    monkeypatch.setitem(sys.modules, "duckdb", SimpleNamespace(connect=lambda **kw: Connection()))

    @contextmanager
    def relay(url):
        yield "http://127.0.0.1/places.parquet", SimpleNamespace(requests=1, bytes=1)

    monkeypatch.setattr(overture_transport, "paced_file", relay)
    monkeypatch.setattr(collector.time, "sleep", lambda duration: None)
    release = "2026-09-23.0"
    path = tmp_path / "snapshot.json"
    collector.collect(
        collector.CITIES["beijing"], path, "https://example.invalid/test.parquet", release=release
    )
    snapshot = json.loads(path.read_text())
    assert snapshot["release"] == release
    assert datetime.fromisoformat(snapshot["downloaded_at"]).utcoffset().total_seconds() == 0
    before = path.read_bytes()
    with pytest.raises(ValueError, match="OUTPUT_ALREADY_EXISTS"):
        collector.collect(collector.CITIES["beijing"], path, release=release)
    assert path.read_bytes() == before
