"""Synthetic isolated DB inputs test correctness, never personalized efficacy."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.http import aware, utcnow
from app.models import (
    BehaviorEvent,
    City,
    DataSource,
    Favorite,
    Place,
    PlaceTag,
    RecommendationRun,
    RecommendationSimilarity,
    SourcePolicy,
    Tag,
    User,
)
from app.seed import fixture_id
from test_api_accounts_catalog import auth, login, register


def synthetic_source(db, computation=True):
    source = DataSource(
        name="TEST synthetic source " + uuid4().hex,
        kind="provider",
        storage_allowed=True,
        commercial_display_allowed=True,
        reviewed_at=utcnow(),
    )
    db.add(source)
    db.flush()
    db.add(
        SourcePolicy(
            source_id=source.id,
            version=1,
            license_url="https://example.invalid/license",
            evidence="TEST synthetic authorization",
            allowed_fields=[],
            computation_allowed=computation,
            expires_at=utcnow() + timedelta(hours=2),
        )
    )
    db.flush()
    return source


def synthetic_place(db, source_id, city_id, name="TEST synthetic place", **fields):
    place = Place(
        id=str(uuid4()),
        name=name,
        city_id=city_id,
        source_id=source_id,
        kind=fields.pop("kind", "attraction"),
        is_test=False,
        **fields,
    )
    db.add(place)
    db.flush()
    return place


def synthetic_city(db):
    city = City(code="TEST-" + uuid4().hex, name="TEST synthetic second city")
    db.add(city)
    db.flush()
    return city


def synthetic_population(db, places, count=20):
    """Explicit synthetic real flags exercise math gates only in this isolated test DB."""
    users = [
        User(
            username="test-" + uuid4().hex,
            email=uuid4().hex + "@example.invalid",
            password_hash="TEST unused password hash",
        )
        for _ in range(count)
    ]
    db.add_all(users)
    db.flush()
    for user in users:
        for place in places:
            db.add(
                BehaviorEvent(
                    user_id=user.id,
                    place_id=place.id,
                    event_id=str(uuid4()),
                    event_type="view",
                    origin="real",
                    occurred_at=utcnow(),
                )
            )
    db.flush()
    return users


def test_city_vectors_filter_before_event_and_favorite_limits(api):
    from app.recommendation_batch import vectors_for

    _, factory = api
    with factory.begin() as db:
        source = synthetic_source(db)
        other = synthetic_city(db)
        local = synthetic_place(db, source.id, fixture_id("city"))
        remote = synthetic_place(db, source.id, other.id)
        user = synthetic_population(db, [local], count=1)[0]
        db.add(
            BehaviorEvent(
                user_id=user.id,
                place_id=remote.id,
                event_id=str(uuid4()),
                event_type="view",
                origin="real",
                occurred_at=utcnow(),
            )
        )
        db.add_all([Favorite(user_id=user.id, place_id=p.id) for p in [local, remote]])
        local_id = local.id
    with factory() as db:
        vectors, interactions = vectors_for(db, max_events=1, city_id=fixture_id("city"))
    assert set(vectors) == {local_id}
    assert interactions == 2


def test_default_rebuild_scopes_runs_and_retains_two_per_city(api):
    from app.recommendation_batch import rebuild

    _, factory = api
    with factory.begin() as db:
        other_id = synthetic_city(db).id
    rebuild(factory)
    rebuild(factory)
    report = rebuild(factory)
    with factory() as db:
        scopes = [run.scope_key for run in db.scalars(select(RecommendationRun))]
    assert sorted(scopes) == [
        "city:" + cid for cid in sorted([fixture_id("city"), other_id]) for _ in range(2)
    ]
    assert report["users"] == report["interactions"] == 0
    assert len(report["cities"]) == 2
    with pytest.raises(ValueError, match="CITY_NOT_FOUND"):
        rebuild(factory, city_id=str(uuid4()))


def test_batch_excludes_sources_without_computation_permission(api):
    from app.recommendation_batch import vectors_for

    _, factory = api
    with factory.begin() as db:
        denied, allowed = synthetic_source(db, False), synthetic_source(db)
        unavailable = synthetic_place(db, denied.id, fixture_id("city"))
        eligible = synthetic_place(db, allowed.id, fixture_id("city"))
        synthetic_population(db, [unavailable, eligible], count=1)
        eligible_id = eligible.id
    with factory() as db:
        vectors, interactions = vectors_for(db)
    assert set(vectors) == {eligible_id}
    assert interactions == 1


def test_model_expiry_is_bounded_by_contributing_source_policy(api):
    from app.recommendation_batch import rebuild

    _, factory = api
    with factory.begin() as db:
        source = synthetic_source(db)
        places = [synthetic_place(db, source.id, fixture_id("city")) for _ in range(6)]
        synthetic_population(db, places)
        expiry = aware(db.get(SourcePolicy, source.id).expires_at)
    report = rebuild(factory, city_id=fixture_id("city"))
    with factory() as db:
        run = db.get(RecommendationRun, report["model_id"])
        assert run.scope_key == "city:" + fixture_id("city")
        assert aware(run.expires_at) <= expiry
    assert report["users"] == 20 and report["interactions"] == 120
    assert report["pairs"] == 30


def test_policy_revoke_restore_during_compute_prevents_stale_publication(api, monkeypatch):
    from app import recommendation_batch as batch

    _, factory = api
    with factory.begin() as db:
        source = synthetic_source(db)
        source_id = source.id
        places = [synthetic_place(db, source.id, fixture_id("city")) for _ in range(6)]
        synthetic_population(db, places)
    original, changed = batch.similarity, False

    def compute_after_policy_changes(left, right):
        nonlocal changed
        if not changed:
            changed = True
            with factory.begin() as db:
                # Even a restore after revocation changes the authorization version.
                db.get(SourcePolicy, source_id).version += 2
        return original(left, right)

    monkeypatch.setattr(batch, "similarity", compute_after_policy_changes)
    with pytest.raises(ValueError, match="POLICY_CHANGED"):
        batch.rebuild(factory, city_id=fixture_id("city"))
    with factory() as db:
        assert db.scalar(select(RecommendationRun.id)) is None


def test_preferences_rank_eligible_places_before_catalog_limit(api):
    client, factory = api
    with factory.begin() as db:
        source, other = synthetic_source(db), synthetic_city(db)
        tag = Tag(code="TEST-" + uuid4().hex, name="TEST preferred")
        db.add(tag)
        db.flush()
        db.add_all(
            [
                Place(
                    name=f"AAA TEST filler {i:04}",
                    kind="attraction",
                    city_id=fixture_id("city"),
                    source_id=source.id,
                    price_minor=100,
                    price_unit="entry",
                )
                for i in range(1001)
            ]
        )
        eligible = synthetic_place(
            db,
            source.id,
            fixture_id("city"),
            "ZZZ TEST eligible",
            price_minor=100,
            price_unit="entry",
        )
        remote = synthetic_place(
            db, source.id, other.id, "AAA TEST wrong city", price_minor=100, price_unit="entry"
        )
        expensive = synthetic_place(
            db,
            source.id,
            fixture_id("city"),
            "AAA TEST too expensive",
            price_minor=300,
            price_unit="entry",
        )
        db.add_all([PlaceTag(place_id=p.id, tag_id=tag.id) for p in [eligible, remote, expensive]])
        tag_id, eligible_id = tag.id, eligible.id
    response = client.get(
        "/api/v1/recommendations",
        params={
            "city_id": fixture_id("city"),
            "preferred_tags": tag_id,
            "limit": 1,
            "kind": "attraction",
            "price_max_minor": 200,
            "price_unit": "entry",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["items"][0]["id"] == eligible_id
    assert response.json()["data"]["reason"] == "fallback_preferences"


def test_collaborative_ranking_uses_same_city_and_relevant_places_beyond_limit(api):
    client, factory = api
    user, tokens = register(client), login(client)
    city_id = fixture_id("city")
    with factory.begin() as db:
        source, other = synthetic_source(db), synthetic_city(db)
        interests = [
            synthetic_place(db, source.id, city_id, f"AAA TEST interest {i}") for i in range(3)
        ]
        db.add_all([Favorite(user_id=user["id"], place_id=p.id) for p in interests])
        db.add_all(
            [
                Place(
                    name=f"BBB TEST filler {i:04}",
                    kind="attraction",
                    city_id=city_id,
                    source_id=source.id,
                )
                for i in range(1001)
            ]
        )
        target = synthetic_place(db, source.id, city_id, "ZZZ TEST relevant target")
        target_id = target.id
        local = RecommendationRun(
            scope_key="city:" + city_id,
            algorithm_version="item-cosine-v1",
            user_count=20,
            interaction_count=100,
            expires_at=utcnow() + timedelta(hours=1),
            created_at=utcnow() - timedelta(minutes=1),
        )
        wrong = RecommendationRun(
            scope_key="city:" + other.id,
            algorithm_version="item-cosine-v1",
            user_count=20,
            interaction_count=100,
            expires_at=utcnow() + timedelta(hours=1),
            created_at=utcnow(),
        )
        db.add_all([local, wrong])
        db.flush()
        db.add(
            RecommendationSimilarity(
                run_id=local.id, source_place_id=interests[0].id, target_place_id=target.id, score=1
            )
        )
    response = client.get(
        "/api/v1/recommendations", headers=auth(tokens), params={"city_id": city_id, "limit": 1}
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["reason"] == "collaborative"
    assert response.json()["data"]["items"][0]["id"] == target_id
    no_city = client.get("/api/v1/recommendations", headers=auth(tokens)).json()["data"]
    assert no_city["reason"] == "fallback_catalog"


@pytest.mark.parametrize(
    "permission", ["computation", "expired", "revoked", "unreviewed", "missing"]
)
def test_recommendations_and_vectors_fail_closed_for_source_permission(api, permission):
    from app.recommendation_batch import vectors_for

    client, factory = api
    with factory.begin() as db:
        source = synthetic_source(db)
        denied = synthetic_place(db, source.id, fixture_id("city"), "AAA TEST denied")
        user = synthetic_population(db, [denied], count=1)[0]
        db.add(Favorite(user_id=user.id, place_id=denied.id))
        policy = db.get(SourcePolicy, source.id)
        if permission == "computation":
            policy.computation_allowed = False
        elif permission == "expired":
            policy.expires_at = utcnow() - timedelta(seconds=1)
        elif permission == "revoked":
            policy.revoked_at = utcnow()
        elif permission == "unreviewed":
            source.reviewed_at = None
        else:
            db.delete(policy)
        denied_id = denied.id
    with factory() as db:
        assert vectors_for(db) == ({}, 0)
    response = client.get("/api/v1/recommendations", params={"city_id": fixture_id("city")})
    assert response.status_code == 200, response.text
    assert denied_id not in {place["id"] for place in response.json()["data"]["items"]}


def test_collaborative_scores_cannot_override_hard_filters(api):
    client, factory = api
    user, tokens = register(client), login(client)
    city_id = fixture_id("city")
    with factory.begin() as db:
        source, other = synthetic_source(db), synthetic_city(db)
        tag = Tag(code="TEST-" + uuid4().hex, name="TEST required")
        db.add(tag)
        db.flush()
        interests = [synthetic_place(db, source.id, city_id) for _ in range(3)]
        db.add_all([Favorite(user_id=user["id"], place_id=p.id) for p in interests])
        good = synthetic_place(
            db, source.id, city_id, "ZZZ TEST eligible", price_minor=100, price_unit="entry"
        )
        bad = [
            synthetic_place(db, source.id, other.id, price_minor=100, price_unit="entry"),
            synthetic_place(
                db, source.id, city_id, kind="hotel", price_minor=100, price_unit="entry"
            ),
            synthetic_place(db, source.id, city_id, price_minor=300, price_unit="entry"),
            synthetic_place(db, source.id, city_id, price_minor=100, price_unit="night"),
            synthetic_place(db, source.id, city_id, price_minor=100, price_unit="entry"),
        ]
        db.add_all([PlaceTag(place_id=p.id, tag_id=tag.id) for p in [good, *bad[:-1]]])
        run = RecommendationRun(
            scope_key="city:" + city_id,
            algorithm_version="item-cosine-v1",
            user_count=20,
            interaction_count=100,
            expires_at=utcnow() + timedelta(hours=1),
        )
        db.add(run)
        db.flush()
        db.add_all(
            [
                RecommendationSimilarity(
                    run_id=run.id, source_place_id=interests[0].id, target_place_id=p.id, score=1
                )
                for p in bad
            ]
        )
        db.add(
            RecommendationSimilarity(
                run_id=run.id, source_place_id=interests[0].id, target_place_id=good.id, score=0.1
            )
        )
        good_id, tag_id = good.id, tag.id
    response = client.get(
        "/api/v1/recommendations",
        headers=auth(tokens),
        params={
            "city_id": city_id,
            "kind": "attraction",
            "explicit_tags": tag_id,
            "price_unit": "entry",
            "price_max_minor": 200,
            "limit": 20,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["reason"] == "collaborative"
    assert [place["id"] for place in data["items"]] == [good_id]
