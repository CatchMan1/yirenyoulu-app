"""Transactional trips, snapshots, costs and durable creation idempotency."""

import json
import re
from datetime import date, timedelta
from hashlib import sha256
from typing import Annotated
from uuid import uuid4

from fastapi import Header, Query, Request, Response
from sqlalchemy import delete, select

from . import schemas as dto
from .auth import checked_session, digest, principal
from .catalog import emit_behavior, paginate, place_data, timestamp, valid_place
from .http import aware, fail, result, utcnow
from .models import ChatSession, City, IdempotencyRecord, Place, PlanningJob, Tag, Trip, TripItem
from .responses import RESPONSE_MODELS


def canonical_hash(body):
    payload = body.model_dump(mode="json")
    if "preferences" in payload:
        payload["preferences"]["tags"] = sorted(payload["preferences"].get("tags", []))
    if "explicit_tags" in payload:
        payload["explicit_tags"] = sorted(payload["explicit_tags"])
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def check_key(key):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}", key or ""):
        fail(422, "INVALID_INPUT", "缺少有效幂等键")
    return digest(key)


def owned_trip(db, actor, tid, version=None):
    row = db.scalar(
        select(Trip).where(Trip.id == tid, Trip.user_id == actor.user_id).with_for_update()
    )
    if not row:
        fail(404, "NOT_FOUND")
    if version is not None and row.version != version:
        fail(409, "VERSION_CONFLICT", "行程已更新，请刷新后重试")
    return row


def snapshot(db, place):
    data = place_data(db, place)
    return {
        "schema_version": 1,
        "name": data["name"],
        "kind": data["kind"],
        "address": data["address"],
        "coordinates": data["coordinates"],
        "price": data["price"],
        "provenance": data["provenance"],
        "captured_at": timestamp(utcnow()),
    }


def require_city_preferences(db, city_id, preferences):
    if db.get(City, city_id) is None:
        fail(404, "NOT_FOUND")
    if any(db.get(Tag, t) is None for t in preferences.get("tags", [])):
        fail(422, "INVALID_INPUT", "偏好标签不存在")


def items_for(db, trip):
    return db.scalars(select(TripItem).where(TripItem.trip_id == trip.id)).all()


def cost_summary(items):
    known = 0
    unknown = 0
    estimate = 0
    missing = False
    for item in items:
        price = item.snapshot.get("price")
        expected = {"hotel": "night", "restaurant": "person", "attraction": "entry"}[
            item.snapshot["kind"]
        ]
        if price is not None and price["unit"] == expected:
            known += price["amount_minor"]
        else:
            unknown += 1
            if item.estimated_cost_minor is None:
                missing = True
            else:
                estimate += item.estimated_cost_minor
    # No route provider means required inter-stop transportation facts are unknown.
    travel_unknown = len({item.place_id for item in items}) > 1
    complete = unknown == 0 and not travel_unknown
    total = None if not items or missing or travel_unknown else known + estimate
    return {
        "known_cost_minor": known,
        "estimated_cost_minor": total,
        "unknown_item_count": unknown,
        "currency": "CNY",
        "complete": complete,
    }


def validate_schedule(trip, items, enforce_budget=True):
    if not 1 <= (trip.end_date - trip.start_date).days + 1 <= 14 or len(items) > 100:
        fail(422, "PLAN_INVALID", "行程应为1至14天且不超过100个地点")
    seen = set()
    hotels = set()
    by_day: dict[date, list[tuple[int, int]]] = {}
    for item in items:
        key = (item.visit_date, item.place_id)
        if key in seen:
            fail(422, "PLAN_INVALID", "同一天不能重复地点")
        seen.add(key)
        if not trip.start_date <= item.visit_date <= trip.end_date:
            fail(422, "PLAN_INVALID", "地点日期超出行程")
        if item.snapshot["kind"] == "hotel":
            if (
                item.start_minute is not None
                or item.end_minute is not None
                or item.visit_date >= trip.end_date
                or item.visit_date in hotels
            ):
                fail(422, "PLAN_INVALID", "住宿按每晚一项，退房不能越界")
            hotels.add(item.visit_date)
        else:
            if (
                item.start_minute is None
                or item.end_minute is None
                or not 0 <= item.start_minute < item.end_minute <= 1440
            ):
                fail(422, "PLAN_INVALID", "活动需要有效的开始和结束分钟")
            by_day.setdefault(item.visit_date, []).append((item.start_minute, item.end_minute))
    for day in by_day.values():
        day.sort(key=lambda interval: interval[0])
        if any(a[1] > b[0] for a, b in zip(day, day[1:])):
            fail(422, "PLAN_INVALID", "活动时段重叠")
    costs = cost_summary(items)
    if (
        enforce_budget
        and trip.budget_minor is not None
        and costs["known_cost_minor"] > trip.budget_minor
    ):
        fail(422, "BUDGET_EXCEEDED", "已知费用超过预算")


def trip_summary(trip):
    return {
        "id": trip.id,
        "title": trip.title,
        "city_id": trip.city_id,
        "start_date": str(trip.start_date),
        "end_date": str(trip.end_date),
        "budget_minor": trip.budget_minor,
        "version": trip.version,
        "created_at": timestamp(trip.created_at),
        "updated_at": timestamp(trip.updated_at),
    }


def trip_data(db, trip):
    items = items_for(db, trip)
    cost = cost_summary(items)
    warnings = []
    payload = []
    items.sort(
        key=lambda i: (
            i.visit_date,
            i.snapshot["kind"] == "hotel",
            i.start_minute if i.start_minute is not None else 1440,
            i.id,
        )
    )
    for item in items:
        place = db.get(Place, item.place_id)
        if place.status != "active":
            warnings.append(
                {"code": "PLACE_INACTIVE", "message": "保存的地点已失效", "place_id": place.id}
            )
        payload.append(
            {
                "id": item.id,
                "place_id": item.place_id,
                "date": str(item.visit_date),
                "start_minute": item.start_minute,
                "end_minute": item.end_minute,
                "note": item.note,
                "snapshot": item.snapshot,
                "current_status": place.status,
                "estimated_cost_minor": item.estimated_cost_minor,
                "estimate_reason": item.estimate_reason,
            }
        )
    if not cost["complete"]:
        warnings.append(
            {
                "code": "COST_INCOMPLETE",
                "message": "存在未知地点或交通费用，不能确认总预算",
                "place_id": None,
            }
        )
    if len({item.place_id for item in items}) > 1:
        warnings.append(
            {"code": "TRAVEL_TIME_UNKNOWN", "message": "交通时间尚未核实", "place_id": None}
        )
    return {
        **trip_summary(trip),
        "preferences": trip.preferences,
        "items": payload,
        "cost_summary": cost,
        "warnings": warnings,
    }


def create_trip(db, actor, body, key):
    keyhash = check_key(key)
    requesthash = canonical_hash(body)
    previous = db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.user_id == actor.user_id,
            IdempotencyRecord.operation == "POST /trips",
            IdempotencyRecord.key_hash == keyhash,
        )
    )
    if previous:
        if previous.request_hash != requesthash:
            fail(409, "IDEMPOTENCY_CONFLICT")
        trip = db.get(Trip, previous.resource_id)
        if trip is None:
            fail(410, "RESOURCE_DELETED")
        if aware(previous.expires_at) <= utcnow():
            fail(409, "IDEMPOTENCY_KEY_EXPIRED")
        return trip
    data = body.model_dump()
    require_city_preferences(db, data["city_id"], data["preferences"])
    trip = Trip(**data, user_id=actor.user_id, id=str(uuid4()), version=1)
    validate_schedule(trip, [])
    db.add(trip)
    db.flush()
    db.add(
        IdempotencyRecord(
            user_id=actor.user_id,
            operation="POST /trips",
            key_hash=keyhash,
            request_hash=requesthash,
            resource_id=trip.id,
            expires_at=utcnow() + timedelta(hours=24),
        )
    )
    return trip


def install(app, sessions):
    prefix = "/api/v1/trips"

    @app.post(
        prefix,
        status_code=201,
        response_model=RESPONSE_MODELS["createTrip"],
        operation_id="createTrip",
    )
    def create(request: Request, body: dto.TripCreate, idempotency_key: Annotated[str, Header()]):
        actor = principal(request)
        with sessions.begin() as db:
            checked_session(db, actor, True)
            trip = create_trip(db, actor, body, idempotency_key)
            db.flush()
            data = trip_data(db, trip)
        return result(request, data)

    @app.get(prefix, response_model=RESPONSE_MODELS["listTrips"], operation_id="listTrips")
    def listing(request: Request, query: Annotated[dto.TripQuery, Query()]):
        actor = principal(request)
        with sessions() as db:
            checked_session(db, actor)
            stmt = select(Trip).where(Trip.user_id == actor.user_id)
            if query.q:
                stmt = stmt.where(Trip.title.contains(query.q.strip(), autoescape=True))
            data, meta = paginate(
                db, stmt.order_by(Trip.created_at.desc(), Trip.id.desc()), query, trip_summary
            )
        return result(request, data, meta)

    @app.get(
        prefix + "/{trip_id}", response_model=RESPONSE_MODELS["getTrip"], operation_id="getTrip"
    )
    def detail(request: Request, trip_id: dto.UUIDText):
        actor = principal(request)
        with sessions() as db:
            checked_session(db, actor)
            data = trip_data(db, owned_trip(db, actor, trip_id))
        return result(request, data)

    @app.patch(
        prefix + "/{trip_id}",
        response_model=RESPONSE_MODELS["updateTrip"],
        operation_id="updateTrip",
    )
    def patch(request: Request, trip_id: dto.UUIDText, body: dto.TripUpdate):
        actor = principal(request)
        changes = body.model_dump(exclude_unset=True)
        changes.pop("version")
        if "preferences" in changes:
            changes["preferences"] = body.preferences.model_dump()
        if not changes:
            fail(422, "INVALID_INPUT")
        with sessions.begin() as db:
            checked_session(db, actor, True)
            trip = owned_trip(db, actor, trip_id, body.version)
            if "preferences" in changes:
                require_city_preferences(db, trip.city_id, changes["preferences"])
            for key, value in changes.items():
                setattr(trip, key, value)
            validate_schedule(trip, items_for(db, trip), enforce_budget="budget_minor" in changes)
            trip.version += 1
            db.flush()
            data = trip_data(db, trip)
        return result(request, data)

    @app.delete(prefix + "/{trip_id}", status_code=204, operation_id="deleteTrip")
    def remove(request: Request, trip_id: dto.UUIDText, version: Annotated[int, Query(ge=1)]):
        actor = principal(request)
        with sessions.begin() as db:
            checked_session(db, actor, True)
            trip = owned_trip(db, actor, trip_id, version)
            if trip.generation_job_id:
                job = db.get(PlanningJob, trip.generation_job_id)
                job.result_deleted = True
            for chat in db.scalars(select(ChatSession).where(ChatSession.trip_id == trip.id)):
                chat.trip_id = None
            db.execute(delete(TripItem).where(TripItem.trip_id == trip.id))
            db.delete(trip)
        return Response(status_code=204)

    @app.post(
        prefix + "/{trip_id}/items",
        status_code=201,
        response_model=RESPONSE_MODELS["addTripItem"],
        operation_id="addTripItem",
    )
    def add_item(request: Request, trip_id: dto.UUIDText, body: dto.ItemCreate):
        actor = principal(request)
        with sessions.begin() as db:
            checked_session(db, actor, True)
            trip = owned_trip(db, actor, trip_id, body.version)
            place = valid_place(db, body.place_id)
            if place.city_id != trip.city_id:
                fail(422, "PLAN_INVALID", "地点不属于目的城市")
            item = TripItem(
                id=str(uuid4()),
                trip_id=trip.id,
                place_id=place.id,
                visit_date=body.date,
                start_minute=body.start_minute,
                end_minute=body.end_minute,
                note=body.note,
                snapshot=snapshot(db, place),
            )
            validate_schedule(trip, [*items_for(db, trip), item])
            db.add(item)
            trip.version += 1
            emit_behavior(
                db,
                actor.user_id,
                place.id,
                "trip_add",
                request.app.state.settings.app_env == "production",
            )
            db.flush()
            data = trip_data(db, trip)
        return result(request, data)

    @app.patch(
        prefix + "/{trip_id}/items/{item_id}",
        response_model=RESPONSE_MODELS["updateTripItem"],
        operation_id="updateTripItem",
    )
    def patch_item(
        request: Request, trip_id: dto.UUIDText, item_id: dto.UUIDText, body: dto.ItemUpdate
    ):
        actor = principal(request)
        changes = body.model_dump(exclude_unset=True)
        changes.pop("version")
        if not changes:
            fail(422, "INVALID_INPUT")
        with sessions.begin() as db:
            checked_session(db, actor, True)
            trip = owned_trip(db, actor, trip_id, body.version)
            item = db.scalar(
                select(TripItem).where(TripItem.id == item_id, TripItem.trip_id == trip.id)
            )
            if item is None:
                fail(404, "NOT_FOUND")
            items = items_for(db, trip)
            if "place_id" in changes and changes["place_id"] != item.place_id:
                place = valid_place(db, changes["place_id"])
                if place.city_id != trip.city_id:
                    fail(422, "PLAN_INVALID")
                item.snapshot = snapshot(db, place)
                item.estimated_cost_minor = None
                item.estimate_reason = None
            for key, value in changes.items():
                setattr(item, "visit_date" if key == "date" else key, value)
            validate_schedule(trip, items, enforce_budget="place_id" in changes)
            trip.version += 1
            db.flush()
            data = trip_data(db, trip)
        return result(request, data)

    @app.delete(
        prefix + "/{trip_id}/items/{item_id}",
        response_model=RESPONSE_MODELS["deleteTripItem"],
        operation_id="deleteTripItem",
    )
    def delete_item(
        request: Request,
        trip_id: dto.UUIDText,
        item_id: dto.UUIDText,
        version: Annotated[int, Query(ge=1)],
    ):
        actor = principal(request)
        with sessions.begin() as db:
            checked_session(db, actor, True)
            trip = owned_trip(db, actor, trip_id, version)
            item = db.scalar(
                select(TripItem).where(TripItem.id == item_id, TripItem.trip_id == trip.id)
            )
            if item is None:
                fail(404, "NOT_FOUND")
            db.delete(item)
            trip.version += 1
            db.flush()
            data = trip_data(db, trip)
        return result(request, data)
