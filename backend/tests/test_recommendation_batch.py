"""Synthetic math inputs verify formulas, never assert personalized efficacy."""

import pytest
from sqlalchemy import select

from app.models import BehaviorEvent
from app.seed import fixture_id
from test_api_accounts_catalog import auth, login, register


def test_similarity_requires_common_support_and_uses_full_vector_norm():
    from app.recommendation_batch import similarity

    assert similarity({"a": 1, "b": 1}, {"a": 1, "b": 1}) == 0
    assert similarity({"a": 1, "b": 1, "c": 1}, {"a": 1, "b": 1, "c": 1}) == pytest.approx(1)
    assert similarity({"a": 1, "b": 1, "c": 1, "d": 3}, {"a": 1, "b": 1, "c": 1}) == pytest.approx(
        0.5
    )


def test_test_events_and_sparse_model_fall_back_without_effect_claims(api):
    from app.recommendation_batch import rebuild

    client, factory = api
    register(client)
    tokens = login(client)
    assert (
        client.put(
            "/api/v1/favorites/" + fixture_id("fixture-attraction-1"), headers=auth(tokens)
        ).status_code
        == 204
    )
    with factory() as db:
        assert db.scalar(select(BehaviorEvent)).origin == "test"
    report = rebuild(factory)
    assert report["users"] == 0 and report["interactions"] == 0
    response = client.get("/api/v1/recommendations", headers=auth(tokens))
    assert response.json()["data"]["reason"] == "fallback_catalog"
