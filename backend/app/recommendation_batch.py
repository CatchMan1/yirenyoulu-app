"""Bounded offline item similarity publication; no user IDs in persisted models."""

import json
from datetime import timedelta
from math import sqrt
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from .db import make_engine
from .http import aware, utcnow
from .models import (
    BehaviorEvent,
    DataSource,
    Favorite,
    Place,
    RecommendationRun,
    RecommendationSimilarity,
    User,
)
from .settings import Settings


def similarity(left: dict[str, float], right: dict[str, float]) -> float:
    common = set(left) & set(right)
    if len(common) < 3:
        return 0.0
    norm = sqrt(sum(v * v for v in left.values()) * sum(v * v for v in right.values()))
    return min(1.0, sum(left[u] * right[u] for u in common) / norm) if norm else 0.0


def vectors_for(db, user_id=None, max_events=100000):
    now = utcnow()
    valid = (
        User.status == "active",
        Place.status == "active",
        Place.is_test.is_(False),
        DataSource.kind != "fixture",
    )
    query = (
        select(BehaviorEvent)
        .join(User, User.id == BehaviorEvent.user_id)
        .join(Place, Place.id == BehaviorEvent.place_id)
        .join(DataSource, DataSource.id == Place.source_id)
        .where(
            *valid,
            BehaviorEvent.origin == "real",
            BehaviorEvent.event_type.in_(["view", "trip_add"]),
            BehaviorEvent.occurred_at >= now - timedelta(days=90),
        )
    )
    if user_id:
        query = query.where(BehaviorEvent.user_id == user_id)
    events = db.scalars(
        query.order_by(BehaviorEvent.occurred_at.desc(), BehaviorEvent.id).limit(max_events + 1)
    ).all()
    if len(events) > max_events:
        raise ValueError("Interaction batch exceeds reviewed size limit")
    vectors: dict[str, dict[str, float]] = {}
    seen = set()
    for event in events:
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
        select(Favorite)
        .join(User, User.id == Favorite.user_id)
        .join(Place, Place.id == Favorite.place_id)
        .join(DataSource, DataSource.id == Place.source_id)
        .where(*valid)
    )
    if user_id:
        favorites = favorites.where(Favorite.user_id == user_id)
    rows = db.scalars(favorites.limit(max_events + 1)).all()
    if len(rows) > max_events:
        raise ValueError("Favorite batch exceeds reviewed size limit")
    for favorite in rows:
        users = vectors.setdefault(favorite.place_id, {})
        users[favorite.user_id] = users.get(favorite.user_id, 0) + 3
    return vectors, len(seen) + len(rows)


def rebuild(sessions):
    with sessions() as db:
        vectors, interactions = vectors_for(db)
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
        # Lock contributing active subjects in a stable order. Erasure cannot publish a stale model afterward.
        for user_id in sorted(users):
            user = db.scalar(select(User).where(User.id == user_id).with_for_update())
            if user is None or user.status != "active":
                raise ValueError("Dataset changed during batch; rebuild")
        run = RecommendationRun(
            id=run_id,
            algorithm_version="item-cosine-v1",
            user_count=len(users),
            interaction_count=interactions,
            expires_at=utcnow() + timedelta(hours=24),
        )
        db.add(run)
        db.flush()
        db.add_all(rows)
        db.flush()
        older = db.scalars(
            select(RecommendationRun.id)
            .where(RecommendationRun.id != run_id)
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
        "users": len(users),
        "interactions": interactions,
        "pairs": len(rows),
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
