"""Public catalog and owner-scoped favorites use one place identity."""

from uuid import uuid4

from sqlalchemy import func, select

from .http import fail, utcnow
from .models import (
    BehaviorEvent,
    Category,
    City,
    DataSource,
    Place,
    PlaceImage,
    PlaceTag,
    Tag,
)


def timestamp(value):
    from .http import aware

    return aware(value).isoformat().replace("+00:00", "Z") if value else None


def named(row):
    return {"id": row.id, "code": row.code, "name": row.name}


def city_data(row):
    return {**named(row), "timezone": row.timezone}


def place_data(db, row, detail=False):
    source = db.get(DataSource, row.source_id)
    data = {
        "id": row.id,
        "kind": row.kind,
        "name": row.name,
        "city": city_data(db.get(City, row.city_id)),
        "category": named(db.get(Category, row.category_id)) if row.category_id else None,
        "tags": [
            named(t)
            for t in db.scalars(
                select(Tag).join(PlaceTag).where(PlaceTag.place_id == row.id).order_by(Tag.id)
            )
        ],
        "address": row.address,
        "coordinates": None,
        "price": None,
        "estimate": None,
        "status": row.status,
        "provenance": {
            "source_name": source.name,
            "source_url": source.source_url,
            "checked_at": timestamp(row.checked_at),
        },
        "is_test": row.is_test,
    }
    if row.longitude is not None:
        data["coordinates"] = {
            "longitude": row.longitude,
            "latitude": row.latitude,
            "crs": row.coordinate_system,
        }
    if row.price_minor is not None:
        data["price"] = {
            "amount_minor": row.price_minor,
            "currency": row.currency,
            "unit": row.price_unit,
            "observed_at": timestamp(row.price_observed_at),
        }
    if detail:
        data.update(
            description=row.description,
            opening_hours=row.opening_hours,
            rating={"value": row.rating_value, "scale": row.rating_scale}
            if row.rating_value is not None
            else None,
            images=[
                {"url": i.url, "source_name": db.get(DataSource, i.source_id).name}
                for i in db.scalars(
                    select(PlaceImage)
                    .where(PlaceImage.place_id == row.id, PlaceImage.display_allowed.is_(True))
                    .order_by(PlaceImage.id)
                )
            ],
            hotel_stars=row.hotel_stars,
            cuisine=row.cuisine,
        )
    return data


def filtered_places(query):
    if query.price_max_minor is not None and query.price_unit is None:
        fail(422, "INVALID_INPUT", "最高价格必须有计价单位")
    stmt = select(Place).where(Place.status == "active")
    if query.q:
        # SQL parameters prevent injection; escape LIKE wildcards for literal search.
        term = query.q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(Place.name.ilike("%" + term + "%", escape="\\"))
    for field in ("city_id", "kind", "category_id", "price_unit"):
        value = getattr(query, field, None)
        if value is not None:
            stmt = stmt.where(getattr(Place, field) == value)
    if query.price_max_minor is not None:
        stmt = stmt.where(Place.price_minor <= query.price_max_minor)
    for tag in set(query.explicit_tags):
        stmt = stmt.where(Place.id.in_(select(PlaceTag.place_id).where(PlaceTag.tag_id == tag)))
    return stmt.order_by(Place.name, Place.id)


def paginate(db, stmt, query, serialize):
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = db.scalars(stmt.offset((query.page - 1) * query.page_size).limit(query.page_size)).all()
    return [serialize(row) for row in rows], {
        "page": query.page,
        "page_size": query.page_size,
        "total": total,
        "has_more": query.page * query.page_size < total,
    }


def valid_place(db, place_id):
    row = db.get(Place, place_id)
    if not row or row.status != "active":
        fail(404, "PLACE_NOT_FOUND")
    return row


def emit_behavior(db, user_id, place_id, event_type, production=False):
    place = db.get(Place, place_id)
    db.add(
        BehaviorEvent(
            user_id=user_id,
            place_id=place_id,
            event_id=str(uuid4()),
            event_type=event_type,
            origin="real" if production and not place.is_test else "test",
            occurred_at=utcnow(),
        )
    )
