"""Operator-only, checkpointed imports. No network calls inside transactions."""

import hashlib
import ipaddress
import json
from datetime import timedelta
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError

from .http import aware, utcnow
from .models import (
    City,
    CityAlias,
    DataSource,
    ImportBatch,
    ImportPermit,
    ImportRow,
    Place,
    PlaceExternalId,
    PlaceFieldProvenance,
    RecommendationRun,
    SourcePolicy,
    TripItem,
    normalize_place_name,
)
from .source_access import allowed


class Coordinates(BaseModel):
    model_config = ConfigDict(extra="forbid")
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False, strict=True)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False, strict=True)
    crs: str = Field(pattern=r"^(WGS84|GCJ-02|BD09)$")


def public_url(value):
    parts = urlsplit(value)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.fragment
        or parts.query
    ):
        raise ValueError("INVALID_PUBLIC_URL")
    host = parts.hostname.lower()
    if host in {"localhost", "metadata.google.internal"} or host.endswith((".local", ".localhost")):
        raise ValueError("INVALID_PUBLIC_URL")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return value
    if not address.is_global:
        raise ValueError("INVALID_PUBLIC_URL")
    return value


class PlaceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    external_id: str = Field(min_length=1, max_length=200)
    kind: str = Field(pattern=r"^(attraction|hotel|restaurant)$")
    name: str = Field(min_length=1, max_length=200)
    source_url: str = Field(max_length=2000)
    observed_at: AwareDatetime
    status: str = Field(default="active", pattern=r"^(active|inactive)$")
    description: str | None = Field(default=None, max_length=5000)
    address: str | None = Field(default=None, max_length=500)
    coordinates: Coordinates | None = None
    price_minor: int | None = Field(default=None, ge=0, le=100000000, strict=True)
    price_unit: str | None = Field(default=None, pattern=r"^(entry|night|person)$")
    price_conditions: str | None = Field(default=None, min_length=1, max_length=1000)
    currency: str = Field(default="CNY", pattern=r"^CNY$")
    hotel_stars: int | None = Field(default=None, ge=1, le=5, strict=True)
    cuisine: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=20)
    opening_hours: dict | None = None
    evidence: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def facts(self):
        public_url(self.source_url)
        if len(json.dumps(self.evidence, ensure_ascii=False)) > 4000:
            raise ValueError("EVIDENCE_TOO_LARGE")
        if self.observed_at > utcnow() + timedelta(minutes=5):
            raise ValueError("FUTURE_OBSERVATION")
        if self.price_minor is not None:
            expected = {"attraction": "entry", "hotel": "night", "restaurant": "person"}[self.kind]
            if self.price_unit != expected or not self.price_conditions:
                raise ValueError("PRICE_CONDITIONS_REQUIRED")
        elif self.price_unit is not None or self.price_conditions is not None:
            raise ValueError("PRICE_INCOMPLETE")
        if self.hotel_stars is not None and self.kind != "hotel":
            raise ValueError("HOTEL_STARS_KIND")
        if self.cuisine is not None and self.kind != "restaurant":
            raise ValueError("CUISINE_KIND")
        if self.opening_hours is not None:
            from .responses import OpeningHours

            OpeningHours.model_validate(self.opening_hours)
        if any(not t.strip() or len(t) > 100 for t in self.tags):
            raise ValueError("INVALID_TAG")
        return self


RECORD_FIELDS = set(PlaceRecord.model_fields)
OPTIONAL_FACTS = {
    "address",
    "coordinates",
    "price_minor",
    "hotel_stars",
    "cuisine",
    "opening_hours",
    "description",
}


def fingerprint(records):
    return hashlib.sha256(
        json.dumps(records, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def policy_for(db, source_id, lock=False):
    stmt = select(DataSource).where(DataSource.id == source_id)
    if lock:
        stmt = stmt.with_for_update()
    source = db.scalar(stmt)
    if not source or not allowed(db, source_id):
        raise ValueError("SOURCE_NOT_AUTHORIZED")
    policy = db.get(SourcePolicy, source_id)
    if source.kind == "fixture" or policy is None:
        raise ValueError("REAL_SOURCE_POLICY_REQUIRED")
    return policy


def grant_permit(sessions, source_id, city_ids, max_records, reference, days=7):
    if (
        not reference.strip()
        or not 1 <= max_records <= 100000
        or not city_ids
        or not 1 <= days <= 30
    ):
        raise ValueError("INVALID_PERMIT")
    with sessions.begin() as db:
        policy_for(db, source_id, True)
        if any(db.get(City, cid) is None for cid in city_ids):
            raise ValueError("CITY_NOT_FOUND")
        row = db.scalar(select(ImportPermit).where(ImportPermit.source_id == source_id))
        if row:
            if max_records < row.used_records:
                raise ValueError("BUDGET_ALREADY_CONSUMED")
            row.max_records = max_records
            row.city_ids = list(set(city_ids))
            row.reference = reference
            row.expires_at = utcnow() + timedelta(days=days)
        else:
            db.add(
                ImportPermit(
                    source_id=source_id,
                    city_ids=list(set(city_ids)),
                    max_records=max_records,
                    reference=reference,
                    expires_at=utcnow() + timedelta(days=days),
                )
            )


def register_policy(
    sessions, name, license_url, evidence, allowed_fields, computation_allowed=False, days=30
):
    public_url(license_url)
    if not name.strip() or len(name) > 200 or not evidence.strip() or not 1 <= days <= 365:
        raise ValueError("INVALID_POLICY")
    if not set(allowed_fields) <= RECORD_FIELDS:
        raise ValueError("UNKNOWN_POLICY_FIELD")
    with sessions.begin() as db:
        source = db.scalar(select(DataSource).where(DataSource.name == name).with_for_update())
        if source is None:
            source = DataSource(name=name, kind="provider", source_url=license_url)
            db.add(source)
            db.flush()
        elif source.kind == "fixture":
            raise ValueError("FIXTURE_POLICY_FORBIDDEN")
        policy = db.get(SourcePolicy, source.id)
        if policy is None:
            policy = SourcePolicy(
                source_id=source.id,
                version=1,
                license_url=license_url,
                evidence=evidence,
                allowed_fields=sorted(allowed_fields),
                expires_at=utcnow() + timedelta(days=days),
            )
            db.add(policy)
        else:
            if set(policy.allowed_fields) - set(allowed_fields):
                # Conservative reconciliation: clear old facts before enabling narrower rights.
                _purge_source_facts(db, source)
            policy.version += 1
            policy.license_url = license_url
            policy.evidence = evidence
            policy.allowed_fields = sorted(allowed_fields)
            policy.expires_at = utcnow() + timedelta(days=days)
            policy.revoked_at = None
        policy.computation_allowed = computation_allowed
        source.storage_allowed = True
        source.commercial_display_allowed = True
        source.reviewed_at = utcnow()
        db.execute(update(RecommendationRun).values(expires_at=utcnow()))
        db.flush()
        return source.id


def register_city(sessions, namespace, external_id, name, parent_code=None):
    if not all(isinstance(v, str) and 0 < len(v) <= 100 for v in [namespace, external_id, name]):
        raise ValueError("INVALID_CITY")
    with sessions.begin() as db:
        alias = db.scalar(
            select(CityAlias).where(
                CityAlias.namespace == namespace, CityAlias.external_id == external_id
            )
        )
        if alias:
            alias.name = name
            db.get(City, alias.city_id).name = name
            alias.parent_code = parent_code
            return alias.city_id
        city = City(code=namespace + ":" + external_id, name=name, timezone="Asia/Shanghai")
        db.add(city)
        db.flush()
        db.add(
            CityAlias(
                city_id=city.id,
                namespace=namespace,
                external_id=external_id,
                name=name,
                parent_code=parent_code,
            )
        )
        return city.id


def create_batch(sessions, source_id, city_id, kind, records, key):
    if (
        kind not in {"attraction", "hotel", "restaurant"}
        or not key
        or len(key) > 100
        or not 1 <= len(records) <= 500
    ):
        raise ValueError("INVALID_BATCH")
    digest = fingerprint(records)
    with sessions.begin() as db:
        policy = policy_for(db, source_id, True)
        existing = db.scalar(
            select(ImportBatch).where(ImportBatch.source_id == source_id, ImportBatch.key == key)
        )
        if existing:
            if (
                existing.input_hash != digest
                or existing.city_id != city_id
                or existing.kind != kind
            ):
                raise ValueError("IDEMPOTENCY_CONFLICT")
            return existing.id
        permit = db.scalar(select(ImportPermit).where(ImportPermit.source_id == source_id))
        if not permit or aware(permit.expires_at) <= utcnow() or city_id not in permit.city_ids:
            raise ValueError("PERMIT_REQUIRED")
        if permit.used_records + len(records) > permit.max_records:
            raise ValueError("PERMIT_EXHAUSTED")
        permit.used_records += len(records)
        batch = ImportBatch(
            source_id=source_id,
            city_id=city_id,
            kind=kind,
            key=key,
            input_hash=digest,
            policy_version=policy.version,
            total=len(records),
        )
        db.add(batch)
        db.flush()
        seen = set()
        for i, raw in enumerate(records):
            row = ImportRow(batch_id=batch.id, sequence=i, status="rejected")
            try:
                if not set(raw) <= set(policy.allowed_fields):
                    raise ValueError("UNLICENSED_FIELD")
                record = PlaceRecord.model_validate(raw)
                if record.kind != kind:
                    raise ValueError("KIND_MISMATCH")
                if record.external_id in seen:
                    raise ValueError("DUPLICATE_EXTERNAL_ID")
                seen.add(record.external_id)
                row.external_id = record.external_id
                row.payload = record.model_dump(mode="json", exclude_unset=True)
                row.status = "validated"
            except (ValidationError, ValueError, TypeError):
                row.error_code = "INVALID_RECORD"
                row.payload = None
            db.add(row)
        return batch.id


def approve_batch(sessions, batch_id, reference):
    if not reference.strip():
        raise ValueError("REVIEW_REFERENCE_REQUIRED")
    with sessions.begin() as db:
        batch = db.get(ImportBatch, batch_id)
        if batch is None:
            raise ValueError("BATCH_NOT_FOUND")
        policy = policy_for(db, batch.source_id, True)
        if batch.policy_version != policy.version:
            raise ValueError("POLICY_CHANGED_RESTAGE")
        if batch.status == "completed":
            return
        batch.review_reference = reference
        batch.status = "approved"


def _apply_row(db, batch, row, policy):
    if row.status != "validated":
        return
    value = PlaceRecord.model_validate(row.payload)
    supplied = {
        k: v
        for k, v in value.model_dump(mode="json", exclude_unset=True).items()
        if v is not None and v != []
    }
    if not set(supplied) <= set(policy.allowed_fields):
        raise ValueError("UNLICENSED_FIELD")
    external = db.scalar(
        select(PlaceExternalId).where(
            PlaceExternalId.source_id == batch.source_id,
            PlaceExternalId.external_id == value.external_id,
        )
    )
    if external:
        place = db.get(Place, external.place_id)
        if place.city_id != batch.city_id or place.kind != batch.kind:
            raise ValueError("IDENTITY_CONFLICT")
        if external.fetched_at and aware(external.fetched_at) > value.observed_at:
            row.status = "skipped"
            row.error_code = "OLDER_OBSERVATION"
            row.place_id = place.id
            return
        if place.source_id != batch.source_id:
            # A reviewed cross-source alias never overwrites the primary source facts.
            external.fetched_at = value.observed_at
            row.status = "skipped"
            row.place_id = place.id
            return
    else:
        # A city lock serializes duplicate checks across different source locks.
        db.scalar(select(City.id).where(City.id == batch.city_id).with_for_update())
        duplicate = db.scalar(
            select(Place.id)
            .where(
                Place.city_id == batch.city_id,
                Place.kind == batch.kind,
                Place.source_id != batch.source_id,
                Place.normalized_name == normalize_place_name(value.name),
            )
            .limit(1)
        )
        if duplicate:
            row.status = "duplicate"
            row.error_code = "CROSS_SOURCE_REVIEW_REQUIRED"
            return
        place = Place(
            id=str(uuid4()),
            name=value.name,
            kind=value.kind,
            city_id=batch.city_id,
            source_id=batch.source_id,
        )
        db.add(place)
        db.flush()
        external = PlaceExternalId(
            place_id=place.id, source_id=batch.source_id, external_id=value.external_id
        )
        db.add(external)
    # Every import is a full permitted snapshot, so removal becomes unknown instead of stale facts.
    place.name = value.name
    place.normalized_name = normalize_place_name(value.name)
    place.address = value.address
    place.description = value.description
    place.status = value.status
    place.checked_at = value.observed_at
    place.currency = value.currency
    place.longitude = value.coordinates.longitude if value.coordinates else None
    place.latitude = value.coordinates.latitude if value.coordinates else None
    place.coordinate_system = value.coordinates.crs if value.coordinates else None
    place.price_minor = value.price_minor
    place.price_unit = value.price_unit
    place.price_conditions = value.price_conditions
    place.price_observed_at = value.observed_at if value.price_minor is not None else None
    place.hotel_stars = value.hotel_stars
    place.cuisine = value.cuisine
    place.opening_hours = value.opening_hours
    from .models import Category, PlaceTag, Tag

    place.category_id = None
    if value.category:
        category = db.scalar(select(Category).where(Category.code == value.category))
        if not category:
            raise ValueError("CATEGORY_NOT_REGISTERED")
        place.category_id = category.id
    db.execute(delete(PlaceTag).where(PlaceTag.place_id == place.id))
    for code in set(value.tags):
        tag = db.scalar(select(Tag).where(Tag.code == code))
        if not tag:
            raise ValueError("TAG_NOT_REGISTERED")
        db.add(PlaceTag(place_id=place.id, tag_id=tag.id))
    external.source_url = value.source_url
    external.fetched_at = value.observed_at
    db.execute(delete(PlaceFieldProvenance).where(PlaceFieldProvenance.place_id == place.id))
    for field in set(policy.allowed_fields) - {"external_id", "observed_at", "source_url"}:
        db.add(
            PlaceFieldProvenance(
                place_id=place.id,
                field=field,
                source_id=batch.source_id,
                external_id=value.external_id,
                observed_at=value.observed_at,
                missing_reason="NOT_PROVIDED" if getattr(value, field, None) is None else None,
                context={"conditions": value.price_conditions}
                if field == "price_minor"
                else {"evidence": value.evidence}
                if field in {"coordinates", "kind", "name"}
                else {},
            )
        )
    # Conditions are retained in the reviewed row; price consumers need the bounded display caveat.
    row.status = "applied"
    row.place_id = place.id
    row.error_code = None


def apply_batch(sessions, batch_id, max_rows=None):
    if max_rows is not None and max_rows < 1:
        raise ValueError("INVALID_ROW_LIMIT")
    processed = 0
    while max_rows is None or processed < max_rows:
        source_id = None
        cursor = None
        try:
            with sessions.begin() as db:
                batch = db.get(ImportBatch, batch_id)
                if batch is None:
                    raise ValueError("BATCH_NOT_FOUND")
                source_id = batch.source_id
                policy = policy_for(db, source_id, True)
                batch = db.scalar(
                    select(ImportBatch)
                    .where(ImportBatch.id == batch_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                if batch.status == "completed":
                    break
                cursor = batch.cursor
                if batch.status not in {"approved", "failed"} or not batch.review_reference:
                    raise ValueError("REVIEW_REQUIRED")
                if batch.policy_version != policy.version:
                    raise ValueError("POLICY_CHANGED_RESTAGE")
                permit = db.scalar(select(ImportPermit).where(ImportPermit.source_id == source_id))
                if (
                    not permit
                    or aware(permit.expires_at) <= utcnow()
                    or batch.city_id not in permit.city_ids
                ):
                    raise ValueError("PERMIT_REQUIRED")
                if batch.cursor >= batch.total:
                    batch.status = "completed"
                    batch.last_error = None
                    break
                row = db.scalar(
                    select(ImportRow).where(
                        ImportRow.batch_id == batch.id, ImportRow.sequence == batch.cursor
                    )
                )
                _apply_row(db, batch, row, policy)
                batch.cursor += 1
                processed += 1
                batch.last_error = None
                batch.status = "completed" if batch.cursor == batch.total else "approved"
        except (ValueError, SQLAlchemyError) as error:
            # The failed row and its cursor rolled back together. Record only stable error codes.
            codes = {
                "CATEGORY_NOT_REGISTERED",
                "TAG_NOT_REGISTERED",
                "IDENTITY_CONFLICT",
                "UNLICENSED_FIELD",
                "POLICY_CHANGED_RESTAGE",
                "PERMIT_REQUIRED",
            }
            code = (
                str(error)
                if isinstance(error, ValueError) and str(error) in codes
                else "IMPORT_FAILED"
            )
            if isinstance(error, SQLAlchemyError):
                code = "STORAGE_UNAVAILABLE"
            if source_id is not None and cursor is not None:
                try:
                    with sessions.begin() as db:
                        db.scalar(
                            select(DataSource).where(DataSource.id == source_id).with_for_update()
                        )
                        failed = db.scalar(
                            select(ImportBatch).where(ImportBatch.id == batch_id).with_for_update()
                        )
                        if (
                            failed
                            and failed.cursor == cursor
                            and failed.status in {"approved", "failed"}
                        ):
                            failed.status = "failed"
                            failed.last_error = code
                except SQLAlchemyError:
                    pass  # An unavailable database cannot persist its own outage.
            raise
    return report(sessions, batch_id)


def resolve_duplicate(sessions, row_id, place_id, reference):
    if not reference.strip():
        raise ValueError("REVIEW_REFERENCE_REQUIRED")
    with sessions.begin() as db:
        row = db.get(ImportRow, row_id)
        if not row or row.status != "duplicate":
            raise ValueError("DUPLICATE_ROW_REQUIRED")
        batch = db.get(ImportBatch, row.batch_id)
        policy_for(db, batch.source_id, True)
        place = db.get(Place, place_id)
        if not place or place.city_id != batch.city_id or place.kind != batch.kind:
            raise ValueError("IDENTITY_CONFLICT")
        db.add(
            PlaceExternalId(
                source_id=batch.source_id,
                external_id=row.external_id,
                place_id=place_id,
                source_url=row.payload["source_url"],
                fetched_at=aware(PlaceRecord.model_validate(row.payload).observed_at),
            )
        )
        row.place_id = place.id
        row.status = "skipped"
        row.error_code = "REVIEWED_ALIAS_ONLY"
        row.review_reference = reference


def report(sessions, batch_id):
    with sessions() as db:
        batch = db.get(ImportBatch, batch_id)
        if not batch:
            raise ValueError("BATCH_NOT_FOUND")
        counts = dict(
            db.execute(
                select(ImportRow.status, func.count())
                .where(ImportRow.batch_id == batch_id)
                .group_by(ImportRow.status)
            ).all()
        )
        return {
            "batch_id": batch.id,
            "status": batch.status,
            "total": batch.total,
            "cursor": batch.cursor,
            "last_error": batch.last_error,
            **{
                k: counts.get(k, 0)
                for k in ["validated", "rejected", "duplicate", "applied", "skipped"]
            },
        }


def _purge_source_facts(db, source):
    source_id = source.id
    source.storage_allowed = False
    ids = list(db.scalars(select(Place.id).where(Place.source_id == source_id)))
    for place in db.scalars(select(Place).where(Place.id.in_(ids))):
        place.name = "地点资料暂不可用"
        place.normalized_name = None
        place.status = "inactive"
        place.address = None
        place.description = None
        place.longitude = None
        place.latitude = None
        place.coordinate_system = None
        place.price_minor = None
        place.price_unit = None
        place.price_observed_at = None
        place.price_conditions = None
        place.rating_value = None
        place.rating_scale = None
        place.opening_hours = None
        place.hotel_stars = None
        place.cuisine = None
        place.category_id = None
    from .models import PlaceImage, PlaceTag

    db.execute(delete(PlaceImage).where(PlaceImage.source_id == source_id))
    db.execute(delete(PlaceTag).where(PlaceTag.place_id.in_(ids)))
    db.execute(delete(PlaceFieldProvenance).where(PlaceFieldProvenance.source_id == source_id))
    for item in db.scalars(select(TripItem).where(TripItem.place_id.in_(ids))):
        snapshot = dict(item.snapshot)
        snapshot.update(
            name="地点资料暂不可用",
            address=None,
            coordinates=None,
            price=None,
            provenance={"source_name": source.name, "source_url": None, "checked_at": None},
        )
        item.snapshot = snapshot
    batches = select(ImportBatch.id).where(ImportBatch.source_id == source_id)
    db.execute(update(ImportRow).where(ImportRow.batch_id.in_(batches)).values(payload=None))


def revoke_source(sessions, source_id, purge=False, only_if_expired=False):
    with sessions.begin() as db:
        source = db.scalar(select(DataSource).where(DataSource.id == source_id).with_for_update())
        policy = db.scalar(
            select(SourcePolicy).where(SourcePolicy.source_id == source_id).with_for_update()
        )
        if not policy or not source:
            raise ValueError("SOURCE_NOT_FOUND")
        if only_if_expired and aware(policy.expires_at) > utcnow():
            return False
        policy.revoked_at = utcnow()
        source.commercial_display_allowed = False
        db.execute(update(RecommendationRun).values(expires_at=utcnow()))
        if purge:
            _purge_source_facts(db, source)
        return True


def expire_sources(sessions):
    with sessions() as db:
        ids = list(
            db.scalars(select(SourcePolicy.source_id).where(SourcePolicy.expires_at <= utcnow()))
        )
    changed = sum(
        revoke_source(sessions, source_id, purge=True, only_if_expired=True) for source_id in ids
    )
    return {"expired_sources": changed}
