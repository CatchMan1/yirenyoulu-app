"""Read-only city inventory and usable-fact quality counts, never coverage estimates."""

from datetime import timedelta
from uuid import UUID

from sqlalchemy import Text, and_, case, cast, exists, func, or_, select
from sqlalchemy.orm import aliased

from .http import utcnow
from .models import City, DataSource, ImportBatch, ImportRow, Place, PlaceImage, SourcePolicy
from .source_access import source_clause

KINDS = ("attraction", "hotel", "restaurant")
MISSING_FIELDS = ("coordinates", "address", "price", "opening_hours", "rating", "displayable_image")


def quality_report(sessions, *, city_id=None, stale_days=30):
    if (
        isinstance(stale_days, bool)
        or not isinstance(stale_days, int)
        or not 1 <= stale_days <= 3650
    ):
        raise ValueError("INVALID_STALE_DAYS")
    if city_id is not None:
        city_id = str(UUID(city_id))
    now = utcnow()
    cutoff = now - timedelta(days=stale_days)
    real_active = and_(Place.is_test.is_(False), Place.status == "active")
    displayable = and_(real_active, source_clause())
    computable = and_(real_active, source_clause("recommend"))
    image_source = aliased(DataSource)
    image_policy = aliased(SourcePolicy)
    has_image = exists(
        select(PlaceImage.id)
        .join(image_source, image_source.id == PlaceImage.source_id)
        .outerjoin(image_policy, image_policy.source_id == image_source.id)
        .where(
            PlaceImage.place_id == Place.id,
            PlaceImage.display_allowed.is_(True),
            or_(
                image_source.kind == "fixture",
                and_(
                    image_source.storage_allowed.is_(True),
                    image_source.commercial_display_allowed.is_(True),
                    image_source.reviewed_at.is_not(None),
                    image_policy.revoked_at.is_(None),
                    image_policy.expires_at > now,
                ),
            ),
        )
    ).correlate(Place)
    missing = {
        "coordinates": Place.longitude.is_(None),
        "address": or_(Place.address.is_(None), func.trim(Place.address) == ""),
        "price": Place.price_minor.is_(None),
        # SQLAlchemy JSON may store None as JSON null rather than SQL NULL.
        "opening_hours": or_(
            Place.opening_hours.is_(None),
            cast(Place.opening_hours, Text).in_(["null", "{}", "[]", '""']),
        ),
        "rating": Place.rating_value.is_(None),
        "displayable_image": ~has_image,
    }
    conditions = {
        "active": Place.status == "active",
        "inactive": Place.status == "inactive",
        "test_places": Place.is_test.is_(True),
        "display_eligible": displayable,
        "computation_eligible": computable,
        **{
            f"missing_{field}": and_(displayable, condition) for field, condition in missing.items()
        },
        "recent": and_(displayable, Place.checked_at >= cutoff, Place.checked_at <= now),
        "stale": and_(displayable, Place.checked_at < cutoff),
        "unknown": and_(displayable, Place.checked_at.is_(None)),
        "future": and_(displayable, Place.checked_at > now),
    }
    with sessions() as db:
        cities_query = select(City.id, City.name).order_by(City.name, City.id)
        if city_id is not None:
            cities_query = cities_query.where(City.id == city_id)
        cities = db.execute(cities_query).all()
        if city_id is not None and not cities:
            raise ValueError("CITY_NOT_FOUND")
        query = select(
            Place.city_id,
            Place.kind,
            func.count().label("total"),
            *[
                func.sum(case((condition, 1), else_=0)).label(name)
                for name, condition in conditions.items()
            ],
        ).group_by(Place.city_id, Place.kind)
        duplicates = (
            select(ImportBatch.city_id, ImportBatch.kind, func.count())
            .join(ImportRow, ImportRow.batch_id == ImportBatch.id)
            .where(ImportRow.status == "duplicate")
            .group_by(ImportBatch.city_id, ImportBatch.kind)
        )
        if city_id is not None:
            query = query.where(Place.city_id == city_id)
            duplicates = duplicates.where(ImportBatch.city_id == city_id)
        counts = {(row.city_id, row.kind): row for row in db.execute(query).mappings()}
        pending = {(city, kind): count for city, kind, count in db.execute(duplicates)}
    result = []
    for city, name in cities:
        groups: dict[str, dict[str, object]] = {}
        for kind in KINDS:
            row = counts.get((city, kind), {})
            groups[kind] = {
                key: int(row.get(key, 0))
                for key in (
                    "total",
                    "active",
                    "inactive",
                    "test_places",
                    "display_eligible",
                    "computation_eligible",
                )
            }
            groups[kind]["missing"] = {
                field: int(row.get(f"missing_{field}", 0)) for field in MISSING_FIELDS
            }
            groups[kind]["freshness"] = {
                key: int(row.get(key, 0)) for key in ("recent", "stale", "unknown", "future")
            }
            groups[kind]["pending_duplicate_rows"] = pending.get((city, kind), 0)
        result.append({"city_id": city, "city_name": name, "groups": groups})
    return {
        "generated_at": now.isoformat(),
        "stale_days": stale_days,
        "definitions": {
            "inventory": "total/active/inactive include test and unauthorized records; test_places is separate",
            "eligible": "active non-test records with current display or computation rights",
            "missing_and_freshness_denominator": "display_eligible",
            "freshness": "source checked_at age, not proof of current operation or field-level freshness",
            "pending_duplicate_rows": "unresolved import rows; not a count of unique duplicate places",
            "coverage": "counts and field availability only; no city or national coverage percentage",
        },
        "cities": result,
    }
