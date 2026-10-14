"""New-release schema. No imports or database access to the legacy project."""

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class Record:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(Record, Base):
    __tablename__ = "users"
    username: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    nickname: Mapped[str] = mapped_column(String(50), default="")
    signature: Mapped[str] = mapped_column(String(200), default="")
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="active")
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        CheckConstraint("status IN ('active','disabled','deleted')", name="valid_status"),
    )


class AuthSession(Record, Base):
    __tablename__ = "auth_sessions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    refresh_hash: Mapped[str] = mapped_column(String(64), unique=True)
    previous_refresh_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generation: Mapped[int] = mapped_column(Integer, default=0)


class City(Record, Base):
    __tablename__ = "cities"
    code: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Shanghai")


class Category(Record, Base):
    __tablename__ = "categories"
    code: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(100))


class Tag(Record, Base):
    __tablename__ = "tags"
    code: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(100))


class DataSource(Record, Base):
    __tablename__ = "data_sources"
    name: Mapped[str] = mapped_column(String(200), unique=True)
    kind: Mapped[str] = mapped_column(String(20))
    source_url: Mapped[str | None] = mapped_column(Text)
    license_notes: Mapped[str | None] = mapped_column(Text)
    commercial_display_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    storage_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("kind IN ('fixture','provider','manual')", name="valid_kind"),
    )


class Place(Record, Base):
    __tablename__ = "places"
    kind: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    city_id: Mapped[str] = mapped_column(ForeignKey("cities.id"), index=True)
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"))
    source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"))
    address: Mapped[str | None] = mapped_column(String(500))
    # Preserve source coordinate system; do not relabel coordinates as conversion.
    longitude: Mapped[float | None] = mapped_column()
    latitude: Mapped[float | None] = mapped_column()
    coordinate_system: Mapped[str | None] = mapped_column(String(10))
    price_minor: Mapped[int | None] = mapped_column(Integer)
    price_unit: Mapped[str | None] = mapped_column(String(20))
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    price_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rating_value: Mapped[float | None] = mapped_column()
    rating_scale: Mapped[float | None] = mapped_column()
    opening_hours: Mapped[dict | None] = mapped_column(JSON)
    hotel_stars: Mapped[int | None] = mapped_column(Integer)
    cuisine: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    is_test: Mapped[bool] = mapped_column(Boolean, default=False)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("kind IN ('attraction','hotel','restaurant')", name="valid_kind"),
        CheckConstraint("status IN ('active','inactive')", name="valid_status"),
        CheckConstraint(
            "(latitude IS NULL AND longitude IS NULL AND coordinate_system IS NULL) OR (latitude IS NOT NULL AND longitude IS NOT NULL AND coordinate_system IS NOT NULL AND latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180)",
            name="coordinates_complete",
        ),
        CheckConstraint(
            "coordinate_system IS NULL OR coordinate_system IN ('GCJ-02','WGS84','BD09')",
            name="known_crs",
        ),
        CheckConstraint("price_minor IS NULL OR price_minor >= 0", name="nonnegative_price"),
        CheckConstraint(
            "price_minor IS NULL OR (price_unit IS NOT NULL AND price_unit IN ('person','night','entry'))",
            name="price_unit",
        ),
        CheckConstraint(
            "(rating_value IS NULL AND rating_scale IS NULL) OR (rating_value IS NOT NULL AND rating_scale IS NOT NULL AND rating_scale > 0 AND rating_value >= 0 AND rating_value <= rating_scale)",
            name="rating_scale",
        ),
        CheckConstraint(
            "hotel_stars IS NULL OR (kind='hotel' AND hotel_stars BETWEEN 1 AND 5)",
            name="hotel_stars",
        ),
        CheckConstraint("cuisine IS NULL OR kind='restaurant'", name="cuisine_kind"),
        Index("ix_places_city_kind_status", "city_id", "kind", "status"),
    )


class PlaceTag(Base):
    __tablename__ = "place_tags"
    place_id: Mapped[str] = mapped_column(
        ForeignKey("places.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[str] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)


class PlaceExternalId(Record, Base):
    __tablename__ = "place_external_ids"
    place_id: Mapped[str] = mapped_column(ForeignKey("places.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"))
    external_id: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("source_id", "external_id"),)


class PlaceImage(Record, Base):
    __tablename__ = "place_images"
    place_id: Mapped[str] = mapped_column(ForeignKey("places.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"))
    url: Mapped[str] = mapped_column(Text)
    license_notes: Mapped[str | None] = mapped_column(Text)
    display_allowed: Mapped[bool] = mapped_column(Boolean, default=False)


class Favorite(Record, Base):
    __tablename__ = "favorites"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    place_id: Mapped[str] = mapped_column(ForeignKey("places.id"))
    __table_args__ = (UniqueConstraint("user_id", "place_id"),)


class PlanningJob(Record, Base):
    __tablename__ = "planning_jobs"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    request_hash: Mapped[str] = mapped_column(String(64))
    request_payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_generation: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(100))
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    result_deleted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    provider_mode: Mapped[str] = mapped_column(
        String(10), default="disabled", server_default="disabled"
    )
    __table_args__ = (
        CheckConstraint("provider_mode IN ('disabled','mock','real')", name="provider_mode"),
        UniqueConstraint("user_id", "idempotency_key"),
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','timed_out','cancelled')",
            name="valid_status",
        ),
    )


class Trip(Record, Base):
    __tablename__ = "trips"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    generation_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("planning_jobs.id", ondelete="SET NULL"), unique=True
    )
    title: Mapped[str] = mapped_column(String(200))
    city_id: Mapped[str] = mapped_column(ForeignKey("cities.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    budget_minor: Mapped[int | None] = mapped_column(Integer)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="date_order"),
        CheckConstraint("budget_minor IS NULL OR budget_minor >= 0", name="budget_nonnegative"),
        CheckConstraint("version >= 1", name="positive_version"),
    )


class TripItem(Record, Base):
    __tablename__ = "trip_items"
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    place_id: Mapped[str] = mapped_column(ForeignKey("places.id"))
    visit_date: Mapped[date] = mapped_column(Date)
    start_minute: Mapped[int | None] = mapped_column(Integer)
    end_minute: Mapped[int | None] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    estimated_cost_minor: Mapped[int | None] = mapped_column(Integer)
    estimate_reason: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str] = mapped_column(String(1000), default="")
    __table_args__ = (
        UniqueConstraint("trip_id", "visit_date", "place_id"),
        CheckConstraint(
            "(start_minute IS NULL AND end_minute IS NULL) OR (start_minute IS NOT NULL AND end_minute IS NOT NULL AND start_minute >= 0 AND start_minute < end_minute AND end_minute <= 1440)",
            name="time_order",
        ),
        CheckConstraint(
            "estimated_cost_minor IS NULL OR estimated_cost_minor >= 0", name="estimate_nonnegative"
        ),
        Index("ix_trip_items_schedule", "trip_id", "visit_date", "start_minute"),
    )


class ChatSession(Record, Base):
    __tablename__ = "chat_sessions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    trip_id: Mapped[str | None] = mapped_column(ForeignKey("trips.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(100), default="新对话")
    next_sequence: Mapped[int] = mapped_column(Integer, default=1)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_generation: Mapped[int] = mapped_column(Integer, default=0)


class ChatMessage(Record, Base):
    __tablename__ = "chat_messages"
    session_id: Mapped[str] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True
    )
    client_message_id: Mapped[str] = mapped_column(String(36))
    content_hash: Mapped[str] = mapped_column(String(64))
    sequence: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error_code: Mapped[str | None] = mapped_column(String(100))
    provider_mode: Mapped[str] = mapped_column(
        String(10), default="disabled", server_default="disabled"
    )
    __table_args__ = (
        CheckConstraint("provider_mode IN ('disabled','mock','real')", name="provider_mode"),
        UniqueConstraint("session_id", "sequence", name="uq_chat_message_sequence"),
        UniqueConstraint(
            "session_id", "client_message_id", "role", name="uq_chat_message_client_role"
        ),
        CheckConstraint("role IN ('user','assistant')", name="valid_role"),
        CheckConstraint(
            "status IN ('pending','running','succeeded','failed')", name="valid_status"
        ),
    )


class BehaviorEvent(Record, Base):
    __tablename__ = "behavior_events"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    place_id: Mapped[str] = mapped_column(ForeignKey("places.id"))
    event_id: Mapped[str] = mapped_column(String(36))
    event_type: Mapped[str] = mapped_column(String(20))
    origin: Mapped[str] = mapped_column(String(10))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    __table_args__ = (
        UniqueConstraint("user_id", "event_id"),
        CheckConstraint(
            "event_type IN ('view','favorite','unfavorite','trip_add')", name="valid_type"
        ),
        CheckConstraint("origin IN ('real','test')", name="valid_origin"),
    )


class IdempotencyRecord(Record, Base):
    __tablename__ = "idempotency_records"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    operation: Mapped[str] = mapped_column(String(100))
    key_hash: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str] = mapped_column(String(36))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("user_id", "operation", "key_hash", name="uq_idempotency_scope"),
    )


class RecoveryToken(Record, Base):
    __tablename__ = "recovery_tokens"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("purpose IN ('reset','verify')", name="valid_purpose"),)


class DeletionAudit(Record, Base):
    __tablename__ = "deletion_audits"
    subject_id: Mapped[str] = mapped_column(String(36), unique=True)
    # Minimal tombstone only. No email, username, conversation or profile content.


class ApiThrottle(Base):
    __tablename__ = "api_throttles"
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[int] = mapped_column(Integer)
    count: Mapped[int] = mapped_column(Integer)
    __table_args__ = (CheckConstraint("count >= 1", name="positive_count"),)


class RecommendationRun(Record, Base):
    __tablename__ = "recommendation_runs"
    algorithm_version: Mapped[str] = mapped_column(String(100))
    user_count: Mapped[int] = mapped_column(Integer)
    interaction_count: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    __table_args__ = (
        CheckConstraint("user_count >= 0 AND interaction_count >= 0", name="nonnegative_sample"),
    )


class RecommendationSimilarity(Base):
    __tablename__ = "recommendation_similarities"
    run_id: Mapped[str] = mapped_column(
        ForeignKey("recommendation_runs.id", ondelete="CASCADE"), primary_key=True
    )
    source_place_id: Mapped[str] = mapped_column(ForeignKey("places.id"), primary_key=True)
    target_place_id: Mapped[str] = mapped_column(ForeignKey("places.id"), primary_key=True)
    score: Mapped[float] = mapped_column()
    __table_args__ = (CheckConstraint("score > 0 AND score <= 1", name="score_range"),)
