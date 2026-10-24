"""Operator commands exercise real storage; fixtures never represent real source facts."""

import json
import stat
import sys

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import URL

from app import data_operator
from app.http import utcnow
from app.models import ImportBatch, ImportPermit, Place, PlaceExternalId


def run(factory, *arguments):
    return data_operator.execute(data_operator.parser().parse_args(arguments), factory)


def write_config(tmp_path, name, value):
    path = tmp_path / name
    path.write_text(json.dumps(value), encoding="utf-8")
    return str(path)


def setup_scope(factory, tmp_path, *, permit=True, license_url=None, default_fields=True):
    source_file = write_config(
        tmp_path,
        "source.json",
        {
            "name": "TEST operator reviewed source",
            "license_url": license_url or "https://creativecommons.org/publicdomain/zero/1.0/",
            "evidence": "TEST synthetic rights record",
            "allowed_fields": [
                "external_id",
                "kind",
                "name",
                "source_url",
                "observed_at",
                "coordinates",
                "evidence",
            ]
            + (["status", "currency"] if default_fields else []),
            "computation_allowed": True,
        },
    )
    source = run(factory, "source", "--file", source_file)["source_id"]
    city_file = write_config(
        tmp_path,
        "city.json",
        {"namespace": "wikidata", "external_id": "Q12345", "name": "TEST synthetic city"},
    )
    city = run(factory, "city", "--file", city_file)["city_id"]
    if permit:
        run(
            factory,
            "permit",
            "--source",
            source,
            "--cities",
            city,
            "--limit",
            "2",
            "--reference",
            "TEST approved two-record scope",
        )
    return source, city


def record():
    return {
        "external_id": "TEST-operator-place",
        "kind": "attraction",
        "name": "TEST operator place",
        "source_url": "https://example.invalid/place",
        "observed_at": utcnow().isoformat(),
        "coordinates": {"latitude": 30.1, "longitude": 120.2, "crs": "WGS84"},
    }


def test_commands_require_review_then_publish_one_stable_place(api, tmp_path):
    client, factory = api
    source, city = setup_scope(factory, tmp_path)
    manifest_file = write_config(
        tmp_path,
        "manifest.json",
        {"source_id": source, "city_id": city, "kind": "attraction", "records": [record()]},
    )
    stage_arguments = (
        "stage",
        "--source",
        source,
        "--city",
        city,
        "--kind",
        "attraction",
        "--key",
        "TEST-operator-batch",
        "--file",
        manifest_file,
    )
    batch = run(factory, *stage_arguments)["batch_id"]
    staged = run(factory, "report", "--batch", batch)
    assert staged["status"] == "staged" and staged["validated"] == 1
    assert staged["rows"][0]["external_id"] == "TEST-operator-place"
    assert "payload" not in staged["rows"][0]
    assert client.get("/api/v1/places", params={"city_id": city}).json()["data"] == []
    with pytest.raises(ValueError, match="REVIEW_REQUIRED"):
        run(factory, "apply", "--batch", batch)
    run(factory, "approve", "--batch", batch, "--reference", "TEST row checked")
    completed = run(factory, "apply", "--batch", batch)
    assert completed["status"] == "completed" and completed["applied"] == 1
    assert run(factory, *stage_arguments)["batch_id"] == batch
    assert run(factory, "apply", "--batch", batch)["applied"] == 1
    with factory() as db:
        external = db.scalar(select(PlaceExternalId).where(PlaceExternalId.source_id == source))
        place = db.get(Place, external.place_id)
        assert place.name == "TEST operator place" and place.city_id == city
        assert db.scalar(select(func.count()).select_from(Place).where(Place.city_id == city)) == 1
        assert (
            db.scalar(select(ImportPermit).where(ImportPermit.source_id == source)).used_records
            == 1
        )
    visible = client.get("/api/v1/places", params={"city_id": city}).json()["data"]
    assert len(visible) == 1 and visible[0]["name"] == "TEST operator place"


@pytest.mark.parametrize("changed", ["source_id", "city_id", "kind"])
def test_manifest_scope_mismatch_does_not_consume_import_budget(api, tmp_path, changed):
    _, factory = api
    source, city = setup_scope(factory, tmp_path)
    manifest = {"source_id": source, "city_id": city, "kind": "attraction", "records": [record()]}
    manifest[changed] = "TEST wrong scope"
    path = write_config(tmp_path, "wrong-scope.json", manifest)
    with pytest.raises(ValueError, match="MANIFEST_SCOPE_MISMATCH"):
        run(
            factory,
            "stage",
            "--source",
            source,
            "--city",
            city,
            "--kind",
            "attraction",
            "--key",
            "TEST-rejected-scope",
            "--file",
            path,
        )
    with factory() as db:
        permit = db.scalar(select(ImportPermit).where(ImportPermit.source_id == source))
        assert permit.used_records == 0 and permit.used_requests == 0
        assert db.scalar(select(func.count()).select_from(ImportBatch)) == 0


@pytest.mark.parametrize(
    ("scenario", "expected_error"),
    [
        ("missing_permit", "CITY_PERMIT_REQUIRED"),
        ("different_city", "CITY_PERMIT_REQUIRED"),
        ("wrong_license", "WIKIDATA_CC0_POLICY_REQUIRED"),
        ("revoked_policy", "SOURCE_NOT_AUTHORIZED"),
    ],
)
def test_fetch_rejects_unapproved_scope_before_contacting_provider(
    api, tmp_path, monkeypatch, scenario, expected_error
):
    _, factory = api
    source, city = setup_scope(
        factory,
        tmp_path,
        permit=scenario != "missing_permit",
        license_url="https://example.invalid/license" if scenario == "wrong_license" else None,
    )
    if scenario == "revoked_policy":
        run(factory, "revoke", "--source", source)

    def network_forbidden(*args, **kwargs):
        pytest.fail("unapproved collection contacted the external provider")

    monkeypatch.setattr(data_operator, "fetch_entities", network_forbidden)
    output = tmp_path / "must-not-exist.json"
    with pytest.raises(ValueError, match=expected_error):
        run(
            factory,
            "fetch",
            "--source",
            source,
            "--city",
            city,
            "--city-qid",
            "Q12346" if scenario == "different_city" else "Q12345",
            "--kind",
            "attraction",
            "--ids",
            "Q12347",
            "--output",
            str(output),
        )
    assert not output.exists()
    with factory() as db:
        permit = db.scalar(select(ImportPermit).where(ImportPermit.source_id == source))
        assert permit is None or permit.used_requests == 0


def test_private_output_is_owner_only_and_never_overwrites_existing_file(tmp_path):
    output = tmp_path / "private" / "manifest.json"
    data_operator.private_json(output, {"facts": "TEST original"})
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        data_operator.private_json(output, {"facts": "TEST replacement"})
    assert json.loads(output.read_text()) == {"facts": "TEST original"}


def test_cli_database_failure_reports_safe_error_without_traceback(monkeypatch, capsys):
    # A refused loopback connection exercises real SQLAlchemy error handling without a DB mock.
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv(
        "DATABASE_URL",
        URL.create(
            "postgresql+psycopg",
            username="TEST_operator",
            password="TEST_DO_NOT_ECHO",
            host="127.0.0.1",
            port=1,
            database="yirenyoulu_test",
        ).render_as_string(hide_password=False),
    )
    monkeypatch.setattr(sys, "argv", ["data_operator", "coverage"])
    with pytest.raises(SystemExit, match="DATA_OPERATION_FAILED") as error:
        data_operator.main()
    captured = capsys.readouterr()
    output = captured.out + captured.err + str(error.value)
    assert "TEST_DO_NOT_ECHO" not in output and "Traceback" not in output


def test_implicit_defaults_do_not_make_reviewed_input_unlicensed(api, tmp_path):
    _, factory = api
    source, city = setup_scope(factory, tmp_path, default_fields=False)
    path = write_config(tmp_path, "raw-records.json", [record()])
    batch = run(
        factory,
        "stage",
        "--source",
        source,
        "--city",
        city,
        "--kind",
        "attraction",
        "--key",
        "TEST-implicit-defaults",
        "--file",
        path,
    )["batch_id"]
    assert run(factory, "report", "--batch", batch)["validated"] == 1
    run(factory, "approve", "--batch", batch, "--reference", "TEST input fields checked")
    assert run(factory, "apply", "--batch", batch)["applied"] == 1


def test_explicit_unlicensed_field_is_quarantined_without_echoing_raw_fact(api, tmp_path):
    _, factory = api
    source, city = setup_scope(factory, tmp_path)
    value = record()
    value["description"] = "TEST_SOURCE_FACT_MUST_NOT_BE_ECHOED"
    path = write_config(tmp_path, "unlicensed-record.json", [value])
    batch = run(
        factory,
        "stage",
        "--source",
        source,
        "--city",
        city,
        "--kind",
        "attraction",
        "--key",
        "TEST-unlicensed-field",
        "--file",
        path,
    )["batch_id"]
    report = run(factory, "report", "--batch", batch)
    assert report["rejected"] == 1 and report["validated"] == 0
    assert report["rows"][0]["error"] == "INVALID_RECORD"
    assert "TEST_SOURCE_FACT_MUST_NOT_BE_ECHOED" not in json.dumps(report)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Place).where(Place.city_id == city)) == 0
