"""Persistent planning jobs and fenced worker. No process-local result cache."""

from datetime import date, timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import Header, Query, Request
from sqlalchemy import and_, or_, select, update

from . import schemas as dto
from .auth import checked_session, principal
from .catalog import emit_behavior, paginate, timestamp, valid_place
from .http import ApiError, aware, fail, result, utcnow
from .models import Place, PlaceTag, PlanningJob, Trip, TripItem, User
from .responses import RESPONSE_MODELS
from .trips import canonical_hash, check_key, require_city_preferences, snapshot, validate_schedule

TERMINAL = {"succeeded", "failed", "timed_out", "cancelled"}


def expire_jobs(db, user_id):
    db.execute(
        update(PlanningJob)
        .where(
            PlanningJob.user_id == user_id,
            PlanningJob.status.in_(["queued", "running"]),
            PlanningJob.deadline <= utcnow(),
        )
        .values(
            status="timed_out",
            error_code="JOB_TIMEOUT",
            lease_until=None,
            lease_generation=PlanningJob.lease_generation + 1,
        )
    )


def job_data(db, job, settings):
    trip = (
        db.scalar(select(Trip.id).where(Trip.generation_job_id == job.id))
        if job.status == "succeeded" and not job.result_deleted
        else None
    )
    return {
        "id": job.id,
        "status": job.status,
        "trip_id": trip,
        "result_deleted": job.result_deleted,
        "error_code": job.error_code,
        "warnings": job.warnings,
        "created_at": timestamp(job.created_at),
        "updated_at": timestamp(job.updated_at),
        "deadline": timestamp(job.deadline),
        "provider_mode": job.provider_mode,
    }


class CatalogTools:
    """Provider receives bounded functions, never a Session or arbitrary SQL API."""

    def __init__(self, sessions, city_id, explicit_tags):
        self._sessions, self._city_id, self._tags = sessions, city_id, explicit_tags
        self.calls = 0

    def search_places(self, kind, limit=50):
        if (
            kind not in {"attraction", "hotel", "restaurant"}
            or not 1 <= limit <= 50
            or self.calls >= 8
        ):
            fail(422, "PLAN_INVALID", "工具参数或调用次数超限")
        self.calls += 1
        stmt = select(Place).where(
            Place.city_id == self._city_id, Place.status == "active", Place.kind == kind
        )
        for tag in self._tags:
            stmt = stmt.where(Place.id.in_(select(PlaceTag.place_id).where(PlaceTag.tag_id == tag)))
        with self._sessions() as db:
            return [
                {"place_id": p.id, "kind": p.kind}
                for p in db.scalars(stmt.order_by(Place.id).limit(limit))
            ]


class FakePlanner:
    """Deterministic development provider. Output is always labelled mock."""

    def plan(self, payload, tools):
        sights = tools.search_places("attraction")
        hotels = tools.search_places("hotel")
        if not sights:
            fail(422, "NO_CANDIDATES")
        start = date.fromisoformat(payload["start_date"])
        end = date.fromisoformat(payload["end_date"])
        items = []
        for day in range((end - start).days + 1):
            visit = str(start + timedelta(days=day))
            items.append(
                {
                    "place_id": sights[day % len(sights)]["place_id"],
                    "date": visit,
                    "start_minute": 600,
                    "end_minute": 660,
                }
            )
            if hotels and day < (end - start).days:
                items.append(
                    {
                        "place_id": hotels[0]["place_id"],
                        "date": visit,
                        "start_minute": None,
                        "end_minute": None,
                    }
                )
        return items


def claim(sessions):
    now = utcnow()
    with sessions.begin() as db:
        expired = db.scalars(
            select(PlanningJob)
            .where(PlanningJob.status.in_(["queued", "running"]), PlanningJob.deadline <= now)
            .with_for_update(skip_locked=True)
        ).all()
        for row in expired:
            row.status = "timed_out"
            row.error_code = "JOB_TIMEOUT"
            row.lease_until = None
        query = (
            select(PlanningJob)
            .where(
                PlanningJob.deadline > now,
                or_(
                    PlanningJob.status == "queued",
                    and_(PlanningJob.status == "running", PlanningJob.lease_until < now),
                ),
            )
            .order_by(PlanningJob.created_at, PlanningJob.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        row = db.scalar(query)
        if row is None:
            return None
        if row.attempts >= 3:
            row.status = "failed"
            row.error_code = "INTERNAL_ERROR"
            return None
        row.status = "running"
        row.attempts += 1
        row.lease_generation += 1
        row.lease_until = min(aware(row.deadline), now + timedelta(seconds=30))
        return row.id, row.user_id, row.lease_generation, dict(row.request_payload)


def finish(sessions, claim_info, output=None, error=None):
    jid, uid, generation, payload = claim_info
    with sessions.begin() as db:
        user = db.scalar(select(User).where(User.id == uid).with_for_update())
        job = db.scalar(
            select(PlanningJob)
            .where(PlanningJob.id == jid, PlanningJob.user_id == uid)
            .with_for_update()
        )
        if (
            not user
            or user.status != "active"
            or not job
            or job.status != "running"
            or job.lease_generation != generation
        ):
            return False
        if aware(job.deadline) <= utcnow():
            job.status = "timed_out"
            job.error_code = "JOB_TIMEOUT"
            job.lease_until = None
            return False
        if job.lease_until is None or aware(job.lease_until) <= utcnow():
            return False
        if error:
            job.status = "failed"
            job.error_code = error
            job.lease_until = None
            return False
        trip = Trip(
            id=str(uuid4()),
            user_id=uid,
            generation_job_id=jid,
            title="【模拟】测试规划",
            city_id=payload["city_id"],
            start_date=date.fromisoformat(payload["start_date"]),
            end_date=date.fromisoformat(payload["end_date"]),
            budget_minor=payload.get("budget_minor"),
            preferences=payload["preferences"],
            version=1,
        )
        items = []
        for raw in output:
            value = dto.ItemCreate.model_validate({"version": 1, **raw})
            place = valid_place(db, value.place_id)
            if place.city_id != trip.city_id:
                fail(422, "PLAN_INVALID")
            for tag in payload.get("explicit_tags", []):
                if not db.get(PlaceTag, (place.id, tag)):
                    fail(422, "PLAN_INVALID")
            items.append(
                TripItem(
                    id=str(uuid4()),
                    trip_id=trip.id,
                    place_id=place.id,
                    visit_date=value.date,
                    start_minute=value.start_minute,
                    end_minute=value.end_minute,
                    note=value.note,
                    snapshot=snapshot(db, place),
                )
            )
        validate_schedule(trip, items)
        db.add(trip)
        db.flush()
        db.add_all(items)
        for item in items:
            emit_behavior(db, uid, item.place_id, "trip_add")
        job.status = "succeeded"
        job.error_code = None
        job.lease_until = None
        job.warnings = [
            {"code": "COST_INCOMPLETE", "message": "模拟规划：未知费用不保证预算", "place_id": None}
        ]
        db.flush()
    return True


def run_once(settings, sessions, planner=None):
    info = claim(sessions)
    if info is None:
        return False
    try:
        if settings.ai_provider != "mock" or settings.app_env == "production":
            finish(sessions, info, error="PROVIDER_UNAVAILABLE")
            return True
        output = (planner or FakePlanner()).plan(
            info[3], CatalogTools(sessions, info[3]["city_id"], info[3].get("explicit_tags", []))
        )
        finish(sessions, info, output=output)
    except ApiError as error:
        finish(
            sessions,
            info,
            error=error.code
            if error.code in {"NO_CANDIDATES", "BUDGET_EXCEEDED"}
            else "PLAN_INVALID",
        )
    except Exception:
        finish(sessions, info, error="INTERNAL_ERROR")
    return True


def install(app, sessions):
    prefix = "/api/v1/planning-jobs"
    settings = app.state.settings

    @app.post(
        prefix,
        status_code=202,
        response_model=RESPONSE_MODELS["createPlanningJob"],
        operation_id="createPlanningJob",
    )
    def create(
        request: Request, body: dto.PlanningCreate, idempotency_key: Annotated[str, Header()]
    ):
        actor = principal(request)
        check_key(idempotency_key)
        hashed = canonical_hash(body)
        with sessions.begin() as db:
            checked_session(db, actor, True)
            expire_jobs(db, actor.user_id)
            job = db.scalar(
                select(PlanningJob).where(
                    PlanningJob.user_id == actor.user_id,
                    PlanningJob.idempotency_key == idempotency_key,
                )
            )
            if job:
                if job.request_hash != hashed:
                    fail(409, "IDEMPOTENCY_CONFLICT")
            else:
                payload = body.model_dump(mode="json")
                require_city_preferences(db, body.city_id, payload["preferences"])
                require_city_preferences(db, body.city_id, {"tags": body.explicit_tags})
                if not 1 <= (body.end_date - body.start_date).days + 1 <= 14:
                    fail(422, "PLAN_INVALID")
                if settings.ai_provider != "mock":
                    fail(503, "PROVIDER_UNAVAILABLE", "模型服务尚未配置")
                job = PlanningJob(
                    user_id=actor.user_id,
                    idempotency_key=idempotency_key,
                    request_hash=hashed,
                    request_payload=payload,
                    deadline=utcnow() + timedelta(seconds=120),
                    status="queued",
                    result_deleted=False,
                    provider_mode=settings.ai_provider,
                )
                db.add(job)
                db.flush()
            data = job_data(db, job, settings)
        return result(request, data)

    @app.get(
        prefix, response_model=RESPONSE_MODELS["listPlanningJobs"], operation_id="listPlanningJobs"
    )
    def listing(request: Request, query: Annotated[dto.JobQuery, Query()]):
        actor = principal(request)
        with sessions.begin() as db:
            checked_session(db, actor, True)
            expire_jobs(db, actor.user_id)
            stmt = select(PlanningJob).where(PlanningJob.user_id == actor.user_id)
            if query.status:
                stmt = stmt.where(PlanningJob.status.in_(query.status))
            data, meta = paginate(
                db,
                stmt.order_by(PlanningJob.created_at.desc(), PlanningJob.id.desc()),
                query,
                lambda j: job_data(db, j, settings),
            )
        return result(request, data, meta)

    def owned(db, actor, jid):
        job = db.scalar(
            select(PlanningJob)
            .where(PlanningJob.id == jid, PlanningJob.user_id == actor.user_id)
            .with_for_update()
        )
        if job is None:
            fail(404, "NOT_FOUND")
        return job

    @app.get(
        prefix + "/{job_id}",
        response_model=RESPONSE_MODELS["getPlanningJob"],
        operation_id="getPlanningJob",
    )
    def detail(request: Request, job_id: dto.UUIDText):
        actor = principal(request)
        with sessions.begin() as db:
            checked_session(db, actor, True)
            expire_jobs(db, actor.user_id)
            data = job_data(db, owned(db, actor, job_id), settings)
        return result(request, data)

    @app.delete(
        prefix + "/{job_id}",
        response_model=RESPONSE_MODELS["cancelPlanningJob"],
        operation_id="cancelPlanningJob",
    )
    def cancel(request: Request, job_id: dto.UUIDText):
        actor = principal(request)
        with sessions.begin() as db:
            checked_session(db, actor, True)
            expire_jobs(db, actor.user_id)
            job = owned(db, actor, job_id)
            terminal = job.status in TERMINAL
            if not terminal:
                job.status = "cancelled"
                job.error_code = None
                job.lease_until = None
                job.lease_generation += 1
            db.flush()
            data = job_data(db, job, settings)
        if terminal:
            fail(409, "JOB_TERMINAL")
        return result(request, data)
