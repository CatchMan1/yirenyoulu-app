"""Operator-owned, checkpointed city discovery and import. No network inside transactions."""

import copy
import re
import time
from datetime import timedelta
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from . import ingestion as imports
from .data_adapters import claims, entity_label, qid, wikidata_record
from .http import aware, utcnow
from .models import (
    City,
    CityAlias,
    CollectionPage,
    CollectionRun,
    DataSource,
    ImportPermit,
    ImportRow,
)
from .wikidata_discovery import discover_page
from .wikidata_source import fetch_entities

SOURCE_NAME = "Wikidata CC0 structured facts"
CC0 = "https://creativecommons.org/publicdomain/zero/1.0/"
LEASE_SECONDS = 180


class BulkConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    run_key: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$")
    cities: list[str] = Field(min_length=1, max_length=50)
    kinds: list[str] = Field(
        default_factory=lambda: ["attraction", "hotel", "restaurant"], min_length=1, max_length=3
    )
    per_city_kind_limit: int = Field(default=100, ge=1, le=10000, strict=True)
    page_size: int = Field(default=20, ge=1, le=20, strict=True)
    record_budget: int = Field(default=3000, ge=1, le=100000, strict=True)
    request_budget: int = Field(default=1000, ge=1, le=100000, strict=True)
    interval_seconds: float = Field(default=1.0, ge=1, le=60, allow_inf_nan=False)
    review_reference: str = Field(min_length=1, max_length=500)

    @field_validator("cities")
    @classmethod
    def city_ids(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("DUPLICATE_CITY")
        return [qid(value) for value in values]

    @field_validator("kinds")
    @classmethod
    def place_kinds(cls, values):
        if len(values) != len(set(values)) or not set(values) <= {
            "attraction",
            "hotel",
            "restaurant",
        }:
            raise ValueError("INVALID_KIND")
        return values


def _source_id(sessions, reference):
    with sessions() as db:
        source_id = db.scalar(select(DataSource.id).where(DataSource.name == SOURCE_NAME))
    if source_id:
        return source_id
    try:
        return imports.register_policy(
            sessions,
            SOURCE_NAME,
            CC0,
            "Wikidata structured namespaces CC0; no text/images. Official evidence: "
            "https://www.wikidata.org/wiki/Wikidata:Licensing; operator rule scope: " + reference,
            sorted(imports.RECORD_FIELDS),
            computation_allowed=True,
        )
    except IntegrityError:
        # Concurrent first runs may race only on the stable source name.
        with sessions() as db:
            source_id = db.scalar(select(DataSource.id).where(DataSource.name == SOURCE_NAME))
            if source_id:
                return source_id
        raise


def start_run(sessions, config: BulkConfig) -> str:
    source_id = _source_id(sessions, config.review_reference)
    payload = config.model_dump(mode="json")
    hashed = imports.fingerprint(payload)
    with sessions.begin() as db:
        policy = imports.policy_for(db, source_id, True)
        if policy.license_url != CC0 or not {
            "external_id",
            "kind",
            "name",
            "source_url",
            "observed_at",
            "status",
            "coordinates",
            "evidence",
        } <= set(policy.allowed_fields):
            raise ValueError("SOURCE_POLICY_REVIEW_REQUIRED")
        existing = db.scalar(
            select(CollectionRun).where(
                CollectionRun.source_id == source_id, CollectionRun.run_key == config.run_key
            )
        )
        if existing:
            if existing.config_hash != hashed:
                raise ValueError("CONFIG_CHANGED")
            return existing.id
        permit = db.scalar(select(ImportPermit).where(ImportPermit.source_id == source_id))
        if permit:
            if aware(permit.expires_at) <= utcnow():
                raise ValueError("PERMIT_EXPIRED_REVIEW_REQUIRED")
            if (
                permit.used_records > config.record_budget
                or permit.used_requests > config.request_budget
            ):
                raise ValueError("BUDGET_ALREADY_CONSUMED")
            permit.max_records = config.record_budget
            permit.max_requests = config.request_budget
        else:
            # Requests for configured city evidence may precede registration; no record city yet.
            permit = ImportPermit(
                source_id=source_id,
                city_ids=[],
                max_records=config.record_budget,
                max_requests=config.request_budget,
                reference=config.review_reference,
                expires_at=utcnow() + timedelta(days=7),
            )
            db.add(permit)
        progress = {
            city + ":" + kind: {"city_id": None, "cursor": None, "seen": 0, "state": "pending"}
            for city in config.cities
            for kind in config.kinds
        }
        run = CollectionRun(
            source_id=source_id,
            run_key=config.run_key,
            config_hash=hashed,
            policy_version=policy.version,
            config=payload,
            progress=progress,
        )
        db.add(run)
        db.flush()
        return run.id


def _locked(db, run_id, token=None, check_policy=True):
    source_id = db.scalar(select(CollectionRun.source_id).where(CollectionRun.id == run_id))
    if source_id is None:
        raise ValueError("RUN_NOT_FOUND")
    db.scalar(select(DataSource).where(DataSource.id == source_id).with_for_update())
    run = db.scalar(
        select(CollectionRun)
        .where(CollectionRun.id == run_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if token is not None and (
        run.lease_token != token or run.lease_until is None or aware(run.lease_until) <= utcnow()
    ):
        raise ValueError("LEASE_LOST")
    if check_policy:
        policy = imports.policy_for(db, source_id)
        if policy.version != run.policy_version:
            raise ValueError("POLICY_CHANGED")
        if policy.license_url != CC0:
            raise ValueError("SOURCE_POLICY_REVIEW_REQUIRED")
    return run


def _heartbeat(sessions, run_id, token):
    with sessions.begin() as db:
        run = _locked(db, run_id, token)
        run.lease_until = utcnow() + timedelta(seconds=LEASE_SECONDS)


def _guard(run_id, token):
    def check(db):
        run = _locked(db, run_id, token)
        run.lease_until = utcnow() + timedelta(seconds=LEASE_SECONDS)

    return check


def _request(sessions, run_id, token, config, call, *args, **kwargs):
    _heartbeat(sessions, run_id, token)
    time.sleep(config.interval_seconds)
    return call(*args, **kwargs)


def _is_city(sessions, run_id, token, config, source_id, entity, transport):
    # Direct city or big-city claims are common; resolve other classes through bounded P279.
    frontier: set[str] = {
        value
        for v in claims(entity, "P31")
        if isinstance(v, dict) and isinstance(value := v.get("id"), str)
    }
    seen: set[str] = set()
    for _ in range(7):
        if frontier & {"Q515", "Q1549591"}:
            return True
        missing = sorted(frontier - seen)
        if not missing or len(seen) + len(missing) > 64:
            return False
        seen.update(missing)
        fetched = {}
        for offset in range(0, len(missing), 25):
            fetched.update(
                _request(
                    sessions,
                    run_id,
                    token,
                    config,
                    fetch_entities,
                    sessions,
                    source_id,
                    missing[offset : offset + 25],
                    transport=transport,
                )
            )
        frontier = {
            value
            for item in fetched.values()
            for v in claims(item, "P279")
            if isinstance(v, dict) and isinstance(value := v.get("id"), str)
        }
    return False


def _prepare_cities(sessions, run_id, token, config, transport):
    with sessions() as db:
        run = db.get(CollectionRun, run_id)
        source_id = run.source_id
        missing = [
            city
            for city in config.cities
            if any(run.progress[city + ":" + kind]["city_id"] is None for kind in config.kinds)
        ]
    for offset in range(0, len(missing), 25):
        requested = missing[offset : offset + 25]
        entities = _request(
            sessions,
            run_id,
            token,
            config,
            fetch_entities,
            sessions,
            source_id,
            requested,
            transport=transport,
        )
        facts = {}
        for city_qid in requested:
            value = entities.get(city_qid, {})
            if not any(isinstance(v, dict) and v.get("id") == "Q148" for v in claims(value, "P17")):
                raise ValueError("CITY_COUNTRY_UNVERIFIED")
            if not _is_city(sessions, run_id, token, config, source_id, value, transport):
                raise ValueError("CITY_TYPE_UNVERIFIED")
            facts[city_qid] = entity_label(value)
        with sessions.begin() as db:
            run = _locked(db, run_id, token)
            progress = copy.deepcopy(run.progress)
            permit = db.scalar(select(ImportPermit).where(ImportPermit.source_id == source_id))
            city_ids = set(permit.city_ids)
            for city_qid, label in facts.items():
                alias = db.scalar(
                    select(CityAlias).where(
                        CityAlias.namespace == "wikidata", CityAlias.external_id == city_qid
                    )
                )
                if alias is None:
                    city = City(code="wikidata:" + city_qid, name=label, timezone="Asia/Shanghai")
                    db.add(city)
                    db.flush()
                    alias = CityAlias(
                        city_id=city.id, namespace="wikidata", external_id=city_qid, name=label
                    )
                    db.add(alias)
                else:
                    db.get(City, alias.city_id).name = label
                    alias.name = label
                city_ids.add(alias.city_id)
                for kind in config.kinds:
                    progress[city_qid + ":" + kind]["city_id"] = alias.city_id
            permit.city_ids = sorted(city_ids)
            run.progress = progress


def _discover(sessions, run_id, token, config, city, kind, state, transport):
    with sessions() as db:
        source_id = db.get(CollectionRun, run_id).source_id
    size = min(config.page_size, config.per_city_kind_limit - state["seen"])
    result = _request(
        sessions,
        run_id,
        token,
        config,
        discover_page,
        sessions,
        source_id,
        city,
        kind,
        cursor=state["cursor"],
        page_size=size,
        transport=transport,
    )
    ids = [qid(value) for value in result.ids]
    if (
        len(ids) > size
        or ids != sorted(set(ids))
        or any(state["cursor"] and v <= state["cursor"] for v in ids)
    ):
        raise ValueError("INVALID_DISCOVERY_PAGE")
    if result.next_cursor is not None and (not ids or result.next_cursor != ids[-1]):
        raise ValueError("INVALID_DISCOVERY_CURSOR")
    with sessions.begin() as db:
        _locked(db, run_id, token)
        page = CollectionPage(
            run_id=run_id,
            city_qid=city,
            kind=kind,
            cursor=state["cursor"] or "",
            next_cursor=result.next_cursor,
            ids=ids,
        )
        db.add(page)
        db.flush()
        return page.id


def _hydrate(sessions, run_id, token, config, page_id, transport):
    with sessions() as db:
        run = db.get(CollectionRun, run_id)
        page = db.get(CollectionPage, page_id)
        if page.records is not None:
            return
        source_id, city_qid, kind, ids = run.source_id, page.city_qid, page.kind, list(page.ids)
    if not ids:
        entities = {}
    else:
        entities = _request(
            sessions,
            run_id,
            token,
            config,
            fetch_entities,
            sessions,
            source_id,
            [city_qid, *ids],
            transport=transport,
        )
        for _ in range(8):
            parents = {
                v.get("id")
                for entity in entities.values()
                for v in claims(entity, "P131")
                if isinstance(v, dict)
            }
            missing = sorted(v for v in parents if isinstance(v, str) and v not in entities)
            if not missing or len(entities) + len(missing) > 200:
                break
            for offset in range(0, len(missing), 25):
                entities.update(
                    _request(
                        sessions,
                        run_id,
                        token,
                        config,
                        fetch_entities,
                        sessions,
                        source_id,
                        missing[offset : offset + 25],
                        transport=transport,
                    )
                )
    records, rejected = [], []
    observed = utcnow()
    for value in ids:
        try:
            record = wikidata_record(entities, value, city_qid, observed)
            if record["kind"] != kind:
                raise ValueError("KIND_MISMATCH")
            records.append(
                imports.PlaceRecord.model_validate(record).model_dump(
                    mode="json", exclude_unset=True
                )
            )
        except (ValueError, TypeError, KeyError):
            rejected.append({"external_id": value, "error": "FACTS_UNVERIFIED"})
    with sessions.begin() as db:
        _locked(db, run_id, token)
        page = db.get(CollectionPage, page_id)
        page.records, page.rejected = records, rejected


def _publish(sessions, run_id, token, page_id, reference):
    with sessions() as db:
        batch_id = db.get(CollectionPage, page_id).batch_id
    if batch_id:
        imports.approve_batch(
            sessions, batch_id, "Automated rule approval: " + reference, guard=_guard(run_id, token)
        )
        imports.apply_batch(sessions, batch_id, guard=_guard(run_id, token))


def _complete_page(sessions, run_id, token, config, page_id, apply):
    with sessions() as db:
        page = db.get(CollectionPage, page_id)
        run = db.get(CollectionRun, run_id)
        source_id, records = run.source_id, page.records
        state = run.progress[page.city_qid + ":" + page.kind]
        city_id, kind = state["city_id"], page.kind
        batch_id = page.batch_id
    if records and not batch_id:
        batch_id = imports.create_batch(
            sessions,
            source_id,
            city_id,
            kind,
            records,
            "bulk:" + page_id,
            guard=_guard(run_id, token),
        )
        with sessions.begin() as db:
            _locked(db, run_id, token)
            db.get(CollectionPage, page_id).batch_id = batch_id
    if apply:
        _publish(sessions, run_id, token, page_id, config.review_reference)
    with sessions.begin() as db:
        run = _locked(db, run_id, token)
        page = db.get(CollectionPage, page_id)
        if page.done:
            return
        progress = copy.deepcopy(run.progress)
        state = progress[page.city_qid + ":" + page.kind]
        state["seen"] += len(page.ids)
        state["cursor"] = page.next_cursor
        state["state"] = (
            "completed"
            if page.next_cursor is None
            else "limited"
            if state["seen"] >= config.per_city_kind_limit
            else "pending"
        )
        page.done = True
        run.progress = progress


def _release(sessions, run_id, token, status, error=None):
    with sessions.begin() as db:
        run = _locked(db, run_id, check_policy=False)
        if run.lease_token == token:
            run.status, run.last_error = status, error
            run.lease_token = None
            run.lease_until = None


def _safe_error(error):
    value = str(error)
    return value if re.fullmatch(r"[A-Z][A-Z0-9_]{0,98}", value) else "COLLECTION_FAILED"


def execute_run(
    sessions, run_id: str, apply: bool = False, transport=None, on_progress=None
) -> dict:
    token = str(uuid4())
    with sessions.begin() as db:
        run = _locked(db, run_id)
        if run.status == "completed" or (run.status == "staged" and not apply):
            return get_report(sessions, run_id)
        if run.lease_token and run.lease_until and aware(run.lease_until) > utcnow():
            raise ValueError("RUN_BUSY")
        run.lease_token, run.lease_until = token, utcnow() + timedelta(seconds=LEASE_SECONDS)
        run.status, run.last_error = "running", None
        config = BulkConfig.model_validate(run.config)
    try:
        _prepare_cities(sessions, run_id, token, config, transport)
        # Promote previously staged pages without repeating any discovery/fetch requests.
        if apply:
            with sessions() as db:
                staged = list(
                    db.scalars(
                        select(CollectionPage.id).where(
                            CollectionPage.run_id == run_id,
                            CollectionPage.done.is_(True),
                            CollectionPage.batch_id.is_not(None),
                        )
                    )
                )
            for page_id in staged:
                _publish(sessions, run_id, token, page_id, config.review_reference)
        for city in config.cities:
            for kind in config.kinds:
                while True:
                    with sessions() as db:
                        run = db.get(CollectionRun, run_id)
                        state = copy.deepcopy(run.progress[city + ":" + kind])
                        page_id = db.scalar(
                            select(CollectionPage.id).where(
                                CollectionPage.run_id == run_id,
                                CollectionPage.city_qid == city,
                                CollectionPage.kind == kind,
                                CollectionPage.cursor == (state["cursor"] or ""),
                                CollectionPage.done.is_(False),
                            )
                        )
                    if state["state"] in {"completed", "limited"}:
                        break
                    if page_id is None:
                        page_id = _discover(
                            sessions, run_id, token, config, city, kind, state, transport
                        )
                    _hydrate(sessions, run_id, token, config, page_id, transport)
                    _complete_page(sessions, run_id, token, config, page_id, apply)
                    if on_progress:
                        on_progress(get_report(sessions, run_id))
        _release(sessions, run_id, token, "completed" if apply else "staged")
    except BaseException as error:
        code = (
            "INTERRUPTED"
            if isinstance(error, KeyboardInterrupt)
            else "STORAGE_UNAVAILABLE"
            if isinstance(error, SQLAlchemyError)
            else _safe_error(error)
        )
        try:
            _release(
                sessions,
                run_id,
                token,
                "paused" if isinstance(error, KeyboardInterrupt) else "failed",
                code,
            )
        except SQLAlchemyError:
            pass
        if isinstance(error, KeyboardInterrupt):
            raise
        raise ValueError(code) from None
    return get_report(sessions, run_id)


def get_report(sessions, run_id: str) -> dict:
    with sessions() as db:
        run = db.get(CollectionRun, run_id)
        if run is None:
            raise ValueError("RUN_NOT_FOUND")
        pages = list(db.scalars(select(CollectionPage).where(CollectionPage.run_id == run_id)))
        batches = [p.batch_id for p in pages if p.batch_id]
        statuses = dict(
            db.execute(
                select(ImportRow.status, func.count())
                .where(ImportRow.batch_id.in_(batches))
                .group_by(ImportRow.status)
            ).all()
        )
        actions = dict(
            db.execute(
                select(ImportRow.result_action, func.count())
                .where(ImportRow.batch_id.in_(batches))
                .group_by(ImportRow.result_action)
            ).all()
        )
        permit = db.scalar(select(ImportPermit).where(ImportPermit.source_id == run.source_id))
        return {
            "run_id": run.id,
            "run_key": run.run_key,
            "status": run.status,
            "last_error": run.last_error,
            "progress": run.progress,
            "discovered": sum(len(p.ids) for p in pages),
            "accepted": sum(len(p.records or []) for p in pages),
            "rejected": sum(len(p.rejected) for p in pages) + statuses.get("rejected", 0),
            "staged": statuses.get("validated", 0),
            "applied": statuses.get("applied", 0),
            "inserted": actions.get("inserted", 0),
            "updated": actions.get("updated", 0),
            "duplicate": statuses.get("duplicate", 0),
            "skipped": statuses.get("skipped", 0),
            "remaining_records": permit.max_records - permit.used_records if permit else 0,
            "remaining_requests": permit.max_requests - permit.used_requests if permit else 0,
            "note": "Candidate limits are not guaranteed inserts or complete city coverage; facts may be unknown.",
        }
