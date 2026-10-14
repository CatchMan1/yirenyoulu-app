"""Real-event collaborative filtering; explicit catalog fallback when sparse."""

from datetime import timedelta
from typing import Annotated

from fastapi import Query, Request
from sqlalchemy import select

from . import schemas as dto
from .auth import checked_session, digest, principal
from .catalog import filtered_places, place_data, valid_place
from .http import aware, fail, result, utcnow
from .models import (
    BehaviorEvent,
    IdempotencyRecord,
    RecommendationRun,
    RecommendationSimilarity,
    User,
)
from .recommendation_batch import vectors_for
from .responses import RESPONSE_MODELS
from .trips import canonical_hash


def recommend(db, actor, query):
    params = dto.PlaceQuery(
        city_id=query.city_id,
        kind=query.kind,
        explicit_tags=query.explicit_tags,
        price_max_minor=query.price_max_minor,
        price_unit=query.price_unit,
    )
    candidates = db.scalars(filtered_places(params).limit(1000)).all()
    scores: dict[str, float] = {}
    reason = "fallback_catalog"
    model = (
        db.scalar(
            select(RecommendationRun)
            .where(
                RecommendationRun.expires_at > utcnow(),
                RecommendationRun.user_count >= 20,
                RecommendationRun.interaction_count >= 100,
            )
            .order_by(RecommendationRun.created_at.desc(), RecommendationRun.id.desc())
            .limit(1)
        )
        if actor
        else None
    )
    if model:
        try:
            vectors, _ = vectors_for(db, actor.user_id, max_events=10000)
        except ValueError:
            vectors = {}
        interests = {pid: users.get(actor.user_id, 0) for pid, users in vectors.items()}
        if len(interests) >= 3:
            candidate_ids = {place.id for place in candidates}
            rows = db.scalars(
                select(RecommendationSimilarity).where(
                    RecommendationSimilarity.run_id == model.id,
                    RecommendationSimilarity.source_place_id.in_(interests),
                )
            ).all()
            for pair in rows:
                if pair.target_place_id in candidate_ids:
                    scores[pair.target_place_id] = (
                        scores.get(pair.target_place_id, 0)
                        + interests[pair.source_place_id] * pair.score
                    )
            if scores:
                reason = "collaborative"
    preferred = query.preferred_tags
    if not preferred and actor:
        user = db.get(User, actor.user_id)
        preferred = user.preferences.get("tags", [])
    if not scores and preferred:
        from .models import PlaceTag

        for candidate in candidates:
            score = db.scalars(
                select(PlaceTag.tag_id).where(
                    PlaceTag.place_id == candidate.id, PlaceTag.tag_id.in_(preferred)
                )
            ).all()
            if score:
                scores[candidate.id] = len(score)
        reason = "fallback_preferences"
    candidates.sort(key=lambda p: (-scores.get(p.id, 0), p.name, p.id))
    return {
        "items": [place_data(db, p) for p in candidates[: query.limit]],
        "reason": reason,
        "algorithm_version": "item-cosine-v1"
        if reason == "collaborative"
        else "catalog-preferences-v1",
    }


def install(app, sessions):
    @app.post(
        "/api/v1/behavior-events",
        status_code=202,
        response_model=RESPONSE_MODELS["recordBehavior"],
        operation_id="recordBehavior",
    )
    def behavior(request: Request, body: dto.BehaviorCreate):
        actor = principal(request)
        hashed = canonical_hash(body)
        with sessions.begin() as db:
            checked_session(db, actor, True)
            existing = db.scalar(
                select(BehaviorEvent).where(
                    BehaviorEvent.user_id == actor.user_id, BehaviorEvent.event_id == body.event_id
                )
            )
            marker = db.scalar(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.user_id == actor.user_id,
                    IdempotencyRecord.operation == "POST /behavior-events",
                    IdempotencyRecord.key_hash == digest(body.event_id),
                )
            )
            if existing:
                if not marker or marker.request_hash != hashed:
                    fail(409, "IDEMPOTENCY_CONFLICT")
                status = "duplicate"
            else:
                if abs((utcnow() - aware(body.occurred_at)).total_seconds()) > 300:
                    fail(422, "INVALID_INPUT", "浏览事件时间超出窗口")
                place = valid_place(db, body.place_id)
                db.add(
                    BehaviorEvent(
                        user_id=actor.user_id,
                        place_id=place.id,
                        event_id=body.event_id,
                        event_type="view",
                        origin="test"
                        if request.app.state.settings.app_env != "production" or place.is_test
                        else "real",
                        occurred_at=utcnow(),
                    )
                )
                db.add(
                    IdempotencyRecord(
                        user_id=actor.user_id,
                        operation="POST /behavior-events",
                        key_hash=digest(body.event_id),
                        request_hash=hashed,
                        resource_id=body.event_id,
                        expires_at=utcnow() + timedelta(days=90),
                    )
                )
                status = "accepted"
        return result(request, {"event_id": body.event_id, "status": status})

    @app.get(
        "/api/v1/recommendations",
        response_model=RESPONSE_MODELS["getRecommendations"],
        operation_id="getRecommendations",
    )
    def recommendations(request: Request, query: Annotated[dto.RecommendationQuery, Query()]):
        actor = principal(request, optional=True)
        with sessions() as db:
            if actor:
                checked_session(db, actor)
            data = recommend(db, actor, query)
        return result(request, data)
