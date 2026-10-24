"""Batch collection does not confuse labels, checkpoints or geographic coverage."""

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def module():
    return importlib.import_module("collect_overture_batch")


def test_city_requires_verified_earth_coordinate():
    m = module()
    entity = {"id": "Q956", "labels": {"en": {"value": "Beijing"}}, "claims": {}}
    with pytest.raises(ValueError):
        m.city_config(entity)
    entity["claims"]["P625"] = [
        {
            "rank": "normal",
            "mainsnak": {
                "datavalue": {
                    "value": {
                        "latitude": 39.9,
                        "longitude": 116.4,
                        "globe": "http://www.wikidata.org/entity/Q2",
                    }
                }
            },
        }
    ]
    cfg = m.city_config(entity)
    assert cfg["names"] == ["Beijing"]
    assert cfg["bounds"] == pytest.approx([116.35, 39.85, 116.45, 39.95])


def test_resume_checks_content_not_only_filename(tmp_path):
    m = module()
    p = tmp_path / "snapshot.json"
    cfg = {"qid": "Q956"}
    p.write_text("broken")
    assert not m.completed(p, cfg, "https://example.test/a")
    p.write_text(
        json.dumps(
            {
                "release": m.RELEASE,
                "city": cfg,
                "source_url": "https://example.test/a",
                "records": [],
            }
        )
    )
    assert m.completed(p, cfg, "https://example.test/a")
    assert not m.completed(p, {"qid": "Q8686"}, "https://example.test/a")


def test_partition_overlap_includes_border_and_western_china():
    m = module()
    assert m.overlaps([90, 30, 91, 31], [35, 18, 104, 82])
    assert not m.overlaps([90, 30, 91, 31], [104, 18, 180, 77])
    assert m.overlaps([103.9, 30, 104.1, 31], [104, 18, 180, 77])


def test_batch_continues_after_failure_and_resumes(tmp_path, monkeypatch):
    m = module()
    ids = ["Q100", "Q200"]
    manifest = tmp_path / "input.json"
    manifest.write_text(json.dumps({"cities": ids}))
    out = tmp_path / "out"
    out.mkdir()
    configs = {q: {"qid": q, "names": [q], "bounds": [90, 30, 91, 31]} for q in ids}
    (out / "cities.json").write_text(
        json.dumps({"release": m.RELEASE, "requested": ids, "cities": configs, "skipped": {}})
    )
    url = "https://example.test/part-00014-file.parquet"
    monkeypatch.setattr(m, "partitions", lambda client: [{"bounds": [35, 18, 104, 82], "url": url}])
    monkeypatch.setattr(m.time, "sleep", lambda seconds: None)
    calls = []

    def collect(cfg, path, source):
        calls.append(cfg["qid"])
        if calls == ["Q100"]:
            raise TimeoutError()
        path.write_text(
            json.dumps({"release": m.RELEASE, "city": cfg, "source_url": source, "records": []})
        )

    monkeypatch.setattr(m, "collect", collect)
    monkeypatch.setattr(sys, "argv", ["batch", "--cities", str(manifest), "--output-dir", str(out)])
    with pytest.raises(SystemExit) as error:
        m.main()
    assert error.value.code == 1
    assert calls == ids
    m.main()
    assert calls == ["Q100", "Q200", "Q100"]
    assert json.loads((out / "report.json").read_text())["failed"] == []


def test_import_only_uses_local_files_and_propagates_failure(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app import bulk_collect, db

    m = module()
    (tmp_path / "cities.json").write_text("{}")
    snapshot = tmp_path / "Q100-00015.json"
    snapshot.write_text("{}")
    monkeypatch.setattr(bulk_collect, "load_settings", lambda path: None)
    monkeypatch.setattr(bulk_collect, "check_readiness", lambda engine: None)
    monkeypatch.setattr(db, "make_engine", lambda settings: SimpleNamespace(dispose=lambda: None))
    monkeypatch.setattr(
        m.httpx, "Client", lambda **kw: pytest.fail("Offline import must not access network")
    )
    calls = []
    monkeypatch.setattr(m, "apply_file", lambda path, catalog, args: calls.append(path) or False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "batch",
            "--import-only",
            "--apply",
            "--env-file",
            "test.env",
            "--output-dir",
            str(tmp_path),
        ],
    )
    with pytest.raises(SystemExit) as error:
        m.main()
    assert error.value.code == 1
    assert calls == [snapshot]
