"""Isolated regression fixtures and HTTP helpers; never used by runtime code."""

from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.orm import Session

from app.models import City, DataSource, Place, PlaceExternalId
from app.settings import Settings


def fixture_id(name: str) -> str:
    return str(uuid5(NAMESPACE_URL, "https://example.invalid/yirenyoulu/fixture/" + name))


def seed_fixtures(db: Session, settings: Settings) -> None:
    if settings.app_env != "test":
        raise ValueError("fixtures require the isolated test environment")
    source_id, city_id = fixture_id("source"), fixture_id("city")
    with db.begin():
        if db.get(DataSource, source_id) is None:
            db.add(
                DataSource(
                    id=source_id,
                    name="FIXTURE ONLY — 不是正式地点数据",
                    kind="fixture",
                    source_url="https://example.invalid/fixture",
                    license_notes="Synthetic test data only",
                )
            )
        if db.get(City, city_id) is None:
            db.add(City(id=city_id, name="【测试】虚拟城市", code="fixture-city"))
        db.flush()
        for kind, label in [("attraction", "景点"), ("hotel", "酒店"), ("restaurant", "餐厅")]:
            for n in range(1, 4):
                external_id = f"fixture-{kind}-{n}"
                place_id = fixture_id(external_id)
                if db.get(Place, place_id) is not None:
                    continue
                db.add(
                    Place(
                        id=place_id,
                        kind=kind,
                        name=f"【测试】虚拟{label}{n}",
                        description="仅供开发联调，不是真实地点，不可据此出行。",
                        city_id=city_id,
                        source_id=source_id,
                        is_test=True,
                    )
                )
                db.flush()
                db.add(
                    PlaceExternalId(place_id=place_id, source_id=source_id, external_id=external_id)
                )


def register(client, name="alice"):
    response = client.post(
        "/api/v1/auth/register",
        json={"username": name, "email": name + "@example.com", "password": "TestOnly!Password12"},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def login(client, name="alice"):
    response = client.post(
        "/api/v1/auth/login", json={"identifier": name, "password": "TestOnly!Password12"}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["tokens"]


def auth(tokens):
    return {"Authorization": "Bearer " + tokens["access_token"]}
