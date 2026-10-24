"""A single fail-closed rights rule for catalog, tools and recommendation."""

from sqlalchemy import and_, exists, or_, select

from .http import aware, utcnow
from .models import DataSource, Place, SourcePolicy


def source_clause(purpose="display"):
    policy = [
        SourcePolicy.source_id == DataSource.id,
        SourcePolicy.revoked_at.is_(None),
        SourcePolicy.expires_at > utcnow(),
    ]
    if purpose in {"recommend", "planning"}:
        policy.append(SourcePolicy.computation_allowed.is_(True))
    return exists(
        select(DataSource.id).where(
            DataSource.id == Place.source_id,
            or_(
                DataSource.kind == "fixture",
                and_(
                    DataSource.storage_allowed.is_(True),
                    DataSource.commercial_display_allowed.is_(True),
                    DataSource.reviewed_at.is_not(None),
                    exists(select(SourcePolicy.source_id).where(*policy)),
                ),
            ),
        )
    ).correlate(Place)


def allowed(db, source_id, purpose="display"):
    source = db.get(DataSource, source_id)
    if not source:
        return False
    if source.kind == "fixture":
        return True
    policy = db.get(SourcePolicy, source_id)
    return bool(
        source.storage_allowed
        and source.commercial_display_allowed
        and source.reviewed_at
        and policy
        and not policy.revoked_at
        and aware(policy.expires_at) > utcnow()
        and (purpose not in {"recommend", "planning"} or policy.computation_allowed)
    )


def redact_snapshot(snapshot, source_name):
    value = dict(snapshot)
    value.update(
        name="地点资料暂不可用",
        address=None,
        coordinates=None,
        price=None,
        provenance={"source_name": source_name, "source_url": None, "checked_at": None},
    )
    return value
