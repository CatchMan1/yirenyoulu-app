"""Bounded city-scoped similarity publication; no user IDs in persisted models."""

import json
from datetime import datetime, timedelta
from math import sqrt
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from .db import make_engine
from .http import aware, utcnow
from .models import (
    BehaviorEvent,
    City,
    DataSource,
    Favorite,
    Place,
    RecommendationRun,
    RecommendationSimilarity,
    SourcePolicy,
    User,
)
from .settings import Settings
from .source_access import allowed, source_clause


def similarity(left: dict[str, float], right: dict[str, float]) -> float:
    common = set(left) & set(right)
    if len(common) < 3:
        return 0.0
    norm = sqrt(sum(v * v for v in left.values()) * sum(v * v for v in right.values()))
    return min(1.0, sum(left[u] * right[u] for u in common) / norm) if norm else 0.0


def _vectors_and_policies(db, user_id=None, max_events=100000, city_id=None):
    now = utcnow()
    valid = [
        User.status == "active",
        Place.status == "active",
        Place.is_test.is_(False),
        DataSource.kind != "fixture",
        source_clause("recommend"),
    ]
    if city_id is not None:
        valid.append(Place.city_id == city_id)
    policy_columns = (Place.source_id, SourcePolicy.version, SourcePolicy.expires_at)
    query = (
        select(BehaviorEvent, *policy_columns)
        .join(User, User.id == BehaviorEvent.user_id)
        .join(Place, Place.id == BehaviorEvent.place_id)
        .join(DataSource, DataSource.id == Place.source_id)
        .join(SourcePolicy, SourcePolicy.source_id == Place.source_id)
        .where(
            *valid,
            BehaviorEvent.origin == "real",
            BehaviorEvent.event_type.in_(["view", "trip_add"]),
            BehaviorEvent.occurred_at >= now - timedelta(days=90),
        )
    )
    if user_id:
        query = query.where(BehaviorEvent.user_id == user_id)
    events = db.execute(
        query.order_by(BehaviorEvent.occurred_at.desc(), BehaviorEvent.id).limit(max_events + 1)
    ).all()
    if len(events) > max_events:
        raise ValueError("Interaction batch exceeds reviewed size limit")
    vectors: dict[str, dict[str, float]] = {}
    policies: dict[str, tuple[int, datetime]] = {}

    def remember_policy(source_id, version, expires_at):
        snapshot = (version, aware(expires_at))
        if source_id in policies and policies[source_id] != snapshot:
            raise ValueError("POLICY_CHANGED during batch; rebuild")
        policies[source_id] = snapshot

    seen = set()
    for event, source_id, version, expires_at in events:
        remember_policy(source_id, version, expires_at)
        key = (
            event.user_id,
            event.place_id,
            event.event_type,
            aware(event.occurred_at).date() if event.event_type == "view" else None,
        )
        if key in seen:
            continue
        seen.add(key)
        weight = (1 if event.event_type == "view" else 4) * 2 ** (
            -max(0, (now - aware(event.occurred_at)).total_seconds()) / (30 * 86400)
        )
        users = vectors.setdefault(event.place_id, {})
        users[event.user_id] = users.get(event.user_id, 0) + weight
    favorites = (
        select(Favorite, *policy_columns)
        .join(User, User.id == Favorite.user_id)
        .join(Place, Place.id == Favorite.place_id)
        .join(DataSource, DataSource.id == Place.source_id)
        .join(SourcePolicy, SourcePolicy.source_id == Place.source_id)
        .where(*valid)
    )
    if user_id:
        favorites = favorites.where(Favorite.user_id == user_id)
    rows = db.execute(favorites.order_by(Favorite.id).limit(max_events + 1)).all()
    if len(rows) > max_events:
        raise ValueError("Favorite batch exceeds reviewed size limit")
    for favorite, source_id, version, expires_at in rows:
        remember_policy(source_id, version, expires_at)
        users = vectors.setdefault(favorite.place_id, {})
        users[favorite.user_id] = users.get(favorite.user_id, 0) + 3
    return vectors, len(seen) + len(rows), policies


def vectors_for(db, user_id=None, max_events=100000, city_id=None):
    vectors, interactions, _ = _vectors_and_policies(db, user_id, max_events, city_id)
    return vectors, interactions


def _rebuild_city(sessions, city_id):
    scope_key = "city:" + city_id
    with sessions() as db:
        if db.get(City, city_id) is None:
            raise ValueError("CITY_NOT_FOUND")
        vectors, interactions, policies = _vectors_and_policies(db, city_id=city_id)
    if len(vectors) > 2000:
        raise ValueError("Item batch exceeds reviewed size limit")
    users = {user for vector in vectors.values() for user in vector}
    rows = []
    run_id = str(uuid4())
    if len(users) >= 20 and interactions >= 100:
        for source, left in vectors.items():
            scores = [
                (target, similarity(left, right))
                for target, right in vectors.items()
                if source != target
            ]
            for target, score in sorted(scores, key=lambda pair: (-pair[1], pair[0]))[:20]:
                if score > 0:
                    rows.append(
                        RecommendationSimilarity(
                            run_id=run_id,
                            source_place_id=source,
                            target_place_id=target,
                            score=score,
                        )
                    )
    with sessions.begin() as db:
        # Match import/revocation order: sorted sources, policies, then contributing subjects.
        sources = db.scalars(
            select(DataSource)
            .where(DataSource.id.in_(policies))
            .order_by(DataSource.id)
            .with_for_update()
        ).all()
        current_policies = db.scalars(
            select(SourcePolicy)
            .where(SourcePolicy.source_id.in_(policies))
            .order_by(SourcePolicy.source_id)
            .with_for_update()
        ).all()
        current = {policy.source_id: policy for policy in current_policies}
        if len(sources) != len(policies) or len(current) != len(policies):
            raise ValueError("POLICY_CHANGED during batch; rebuild")
        for source in sources:
            policy = current[source.id]
            if (
                source.kind == "fixture"
                or (policy.version, aware(policy.expires_at)) != policies[source.id]
                or not allowed(db, source.id, "recommend")
            ):
                raise ValueError("POLICY_CHANGED during batch; rebuild")
        active_users = db.scalars(
            select(User).where(User.id.in_(users)).order_by(User.id).with_for_update()
        ).all()
        if len(active_users) != len(users) or any(user.status != "active" for user in active_users):
            raise ValueError("Dataset changed during batch; rebuild")
        # Serialize retention even for empty cities, which have no contributing source locks.
        city = db.scalar(select(City).where(City.id == city_id).with_for_update())
        if city is None:
            raise ValueError("CITY_NOT_FOUND")
        now = utcnow()
        expires_at = min([now + timedelta(hours=24), *(expiry for _, expiry in policies.values())])
        run = RecommendationRun(
            id=run_id,
            scope_key=scope_key,
            algorithm_version="item-cosine-v1",
            user_count=len(users),
            interaction_count=interactions,
            created_at=now,
            expires_at=expires_at,
        )
        db.add(run)
        db.flush()
        db.add_all(rows)
        db.flush()
        older = db.scalars(
            select(RecommendationRun.id)
            .where(RecommendationRun.scope_key == scope_key, RecommendationRun.id != run_id)
            .order_by(RecommendationRun.created_at.desc(), RecommendationRun.id.desc())
            .offset(1)
        ).all()
        if older:
            db.execute(
                delete(RecommendationSimilarity).where(RecommendationSimilarity.run_id.in_(older))
            )
            db.execute(delete(RecommendationRun).where(RecommendationRun.id.in_(older)))
    return {
        "model_id": run_id,
        "scope_key": scope_key,
        "users": len(users),
        "interactions": interactions,
        "pairs": len(rows),
        "algorithm_version": "item-cosine-v1",
    }


def rebuild(sessions, city_id=None):
    if city_id is not None:
        return _rebuild_city(sessions, str(city_id))
    reports = []
    after = None
    while True:
        with sessions() as db:
            query = select(City.id).order_by(City.id).limit(1)
            if after is not None:
                query = query.where(City.id > after)
            next_city = db.scalar(query)
        if next_city is None:
            break
        reports.append(_rebuild_city(sessions, next_city))
        after = next_city
    return {
        "cities": reports,
        "users": sum(report["users"] for report in reports),
        "interactions": sum(report["interactions"] for report in reports),
        "pairs": sum(report["pairs"] for report in reports),
        "algorithm_version": "item-cosine-v1",
    }


def main():
    engine = make_engine(Settings())
    try:
        print(json.dumps(rebuild(sessionmaker(engine, expire_on_commit=False))))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
