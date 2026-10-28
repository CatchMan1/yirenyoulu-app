"""Real-event collaborative filtering; explicit catalog fallback when sparse."""

from datetime import timedelta
from typing import Annotated

from fastapi import Query, Request
from sqlalchemy import case, func, select

from . import schemas as dto
from .auth import checked_session, digest, principal
from .catalog import filtered_places, place_data, valid_place
from .http import aware, fail, result, utcnow
from .models import (
    BehaviorEvent,
    DataSource,
    IdempotencyRecord,
    Place,
    PlaceTag,
    RecommendationRun,
    RecommendationSimilarity,
    SourcePolicy,
    User,
)
from .recommendation_batch import vectors_for
from .responses import RESPONSE_MODELS
from .source_access import source_clause
from .trips import canonical_hash


def recommend(db, actor, query):
    params = dto.PlaceQuery(
        city_id=query.city_id,
        kind=query.kind,
        explicit_tags=query.explicit_tags,
        price_max_minor=query.price_max_minor,
        price_unit=query.price_unit,
    )
    eligible = filtered_places(params).where(source_clause("recommend")).order_by(None)
    candidates = []
    reason = "fallback_catalog"
    model = (
        db.scalar(
            select(RecommendationRun)
            .where(
                RecommendationRun.scope_key == "city:" + query.city_id,
                RecommendationRun.expires_at > utcnow(),
                RecommendationRun.user_count >= 20,
                RecommendationRun.interaction_count >= 100,
            )
            .order_by(RecommendationRun.created_at.desc(), RecommendationRun.id.desc())
            .limit(1)
        )
        if actor and query.city_id is not None
        else None
    )
    if model:
        try:
            vectors, _ = vectors_for(db, actor.user_id, max_events=10000, city_id=query.city_id)
        except ValueError:
            vectors = {}
        interests = {pid: users.get(actor.user_id, 0) for pid, users in vectors.items()}
        if len(interests) >= 3:
            # Aggregate similarity before applying the bounded result limit, with all hard
            # catalog filters still in SQL. Alphabetical catalog position cannot hide a match.
            ranked = (
                select(
                    RecommendationSimilarity.target_place_id.label("place_id"),
                    func.sum(
                        RecommendationSimilarity.score
                        * case(interests, value=RecommendationSimilarity.source_place_id, else_=0.0)
                    ).label("score"),
                )
                .where(
                    RecommendationSimilarity.run_id == model.id,
                    RecommendationSimilarity.source_place_id.in_(interests),
                )
                .group_by(RecommendationSimilarity.target_place_id)
                .subquery()
            )
            candidates = db.scalars(
                eligible.join(ranked, ranked.c.place_id == Place.id)
                .order_by(ranked.c.score.desc(), Place.name, Place.id)
                .limit(query.limit)
            ).all()
            if candidates:
                reason = "collaborative"
    if not candidates:
        preferred = query.preferred_tags
        if not preferred and actor:
            user = db.get(User, actor.user_id)
            preferred = user.preferences.get("tags", [])
        ordering = []
        if preferred:
            preference_score = (
                select(func.count())
                .select_from(PlaceTag)
                .where(PlaceTag.place_id == Place.id, PlaceTag.tag_id.in_(preferred))
                .correlate(Place)
                .scalar_subquery()
            )
            ordering.append(preference_score.desc())
            reason = "fallback_preferences"
        candidates = db.scalars(
            eligible.order_by(*ordering, Place.name, Place.id).limit(query.limit)
        ).all()
    # Keep these references alive for the serializer's identity-map lookups, avoiding
    # a separate source/policy query for every recommended place.
    source_ids = {place.source_id for place in candidates}
    _sources = db.scalars(select(DataSource).where(DataSource.id.in_(source_ids))).all()
    _policies = db.scalars(select(SourcePolicy).where(SourcePolicy.source_id.in_(source_ids))).all()
    return {
        "items": [place_data(db, p) for p in candidates],
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
