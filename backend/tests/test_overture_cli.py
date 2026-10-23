"""Operator CLI previews cannot register sources or insert places."""

import importlib
import json
import sys
from pathlib import Path

from sqlalchemy import func, select
from test_overture import sample

from app.models import CityAlias, DataSource, Place
from app.seed import fixture_id


def test_preview_then_apply_and_replay(api, tmp_path, monkeypatch):
    _, sessions = api
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    cli = importlib.import_module("import_overture")
    engine = sessions.kw["bind"]
    monkeypatch.setattr(engine, "dispose", lambda: None)
    monkeypatch.setattr(cli, "make_engine", lambda settings: engine)
    monkeypatch.setattr(cli, "load_settings", lambda path: None)
    monkeypatch.setattr(cli, "check_readiness", lambda engine: None)
    with sessions.begin() as db:
        db.add(
            CityAlias(
                city_id=fixture_id("city"),
                namespace="wikidata",
                external_id="Q956",
                name="TEST city",
            )
        )
    path = tmp_path / "snapshot.json"
    path.write_text(
        json.dumps({"release": cli.RELEASE, "city": cli.CITIES["beijing"], "records": [sample()]})
    )
    argv = ["import_overture", "--snapshot", str(path), "--env-file", "unused-test.env"]
    monkeypatch.setattr(sys, "argv", argv)
    cli.main()
    with sessions() as db:
        assert db.scalar(select(DataSource.id).where(DataSource.name == cli.SOURCE)) is None
    monkeypatch.setattr(sys, "argv", argv + ["--apply"])
    cli.main()
    cli.main()
    with sessions() as db:
        sid = db.scalar(select(DataSource.id).where(DataSource.name == cli.SOURCE))
        assert db.scalar(select(func.count()).select_from(Place).where(Place.source_id == sid)) == 1
