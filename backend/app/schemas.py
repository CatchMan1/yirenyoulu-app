"""Typed public DTOs. Request and persistence objects are separate."""

from datetime import date as CalendarDate
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

UUIDText = Annotated[
    str,
    Field(pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"),
]
Money = Annotated[int, Field(strict=True, ge=0, le=100000000)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class Preferences(Input):
    tags: list[UUIDText] = Field(default_factory=list, max_length=20)
    pace: Literal["relaxed", "normal", "fast"] = "normal"

    @field_validator("tags")
    @classmethod
    def unique_tags(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("duplicate tags")
        return value


class Register(Input):
    username: Annotated[str, Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_]+$")]
    email: EmailStr
    password: Annotated[str, Field(min_length=12, max_length=128)]
    nickname: Annotated[str, Field(max_length=50)] = ""

    @field_validator("username", "email")
    @classmethod
    def normalized(cls, value):
        return str(value).strip().lower()


class Login(Input):
    identifier: Annotated[str, Field(min_length=3, max_length=320)]
    password: Annotated[str, Field(min_length=1, max_length=128)]


class Refresh(Input):
    refresh_token: Annotated[str, Field(min_length=1, max_length=4096)]


class PasswordChange(Input):
    current_password: Annotated[str, Field(min_length=1, max_length=128)]
    new_password: Annotated[str, Field(min_length=12, max_length=128)]


class RecoveryRequest(Input):
    email: EmailStr


class RecoveryConfirm(Input):
    token: Annotated[str, Field(min_length=1, max_length=4096)]
    new_password: Annotated[str, Field(min_length=12, max_length=128)]


class VerificationConfirm(Input):
    token: Annotated[str, Field(min_length=1, max_length=4096)]


class AccountDelete(Input):
    current_password: Annotated[str, Field(min_length=1, max_length=128)]


class ProfileUpdate(Input):
    nickname: Annotated[str, Field(max_length=50)] = ""
    signature: Annotated[str, Field(max_length=200)] = ""
    preferences: Preferences = Field(default_factory=Preferences)


class UserRead(BaseModel):
    id: str
    username: str
    email: str
    email_verified: bool
    nickname: str
    signature: str
    preferences: Preferences


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["Bearer"] = "Bearer"  # noqa: S105 -- HTTP scheme, not a credential
    expires_in: int = 900
    refresh_expires_at: str


class LoginResult(BaseModel):
    tokens: TokenPair
    user: UserRead


class PageQuery(Input):
    page: int = Field(default=1, ge=1, le=10000)
    page_size: int = Field(default=20, ge=1, le=50)


class DirectoryQuery(PageQuery):
    q: Annotated[str, Field(min_length=1, max_length=100)] | None = None


class PlaceQuery(DirectoryQuery):
    city_id: UUIDText | None = None
    kind: Literal["attraction", "hotel", "restaurant"] | None = None
    category_id: UUIDText | None = None
    explicit_tags: list[UUIDText] = Field(default_factory=list, max_length=20)
    price_max_minor: int | None = Field(default=None, ge=0, le=100000000)
    price_unit: Literal["entry", "night", "person"] | None = None


class FavoriteQuery(PageQuery):
    kind: Literal["attraction", "hotel", "restaurant"] | None = None


class TripCreate(Input):
    title: Annotated[str, Field(min_length=1, max_length=200)]
    city_id: UUIDText
    start_date: CalendarDate
    end_date: CalendarDate
    budget_minor: Money | None = None
    preferences: Preferences = Field(default_factory=Preferences)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("blank title")
        return value

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def calendar_date(cls, value):
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError("expected calendar date")
        return CalendarDate.fromisoformat(value)


class TripUpdate(Input):
    version: Annotated[int, Field(strict=True, ge=1)]
    title: Annotated[str, Field(min_length=1, max_length=200)] = ""
    start_date: CalendarDate | None = None
    end_date: CalendarDate | None = None
    budget_minor: Money | None = None
    preferences: Preferences = Field(default_factory=Preferences)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value):
        return TripCreate.clean_title(value)

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def calendar_date(cls, value):
        return TripCreate.calendar_date(value)


class ItemCreate(Input):
    version: Annotated[int, Field(strict=True, ge=1)]
    place_id: UUIDText
    date: CalendarDate
    start_minute: Annotated[int, Field(strict=True, ge=0, le=1439)] | None
    end_minute: Annotated[int, Field(strict=True, ge=1, le=1440)] | None
    note: Annotated[str, Field(max_length=1000)] = ""

    @field_validator("date", mode="before")
    @classmethod
    def calendar_date(cls, value):
        return TripCreate.calendar_date(value)


class ItemUpdate(Input):
    version: Annotated[int, Field(strict=True, ge=1)]
    place_id: UUIDText = ""
    date: CalendarDate | None = None
    start_minute: Annotated[int, Field(strict=True, ge=0, le=1439)] | None = None
    end_minute: Annotated[int, Field(strict=True, ge=1, le=1440)] | None = None
    note: Annotated[str, Field(max_length=1000)] = ""

    @field_validator("date", mode="before")
    @classmethod
    def calendar_date(cls, value):
        return TripCreate.calendar_date(value)


class TripQuery(DirectoryQuery):
    pass


class PlanningCreate(Input):
    city_id: UUIDText
    start_date: CalendarDate
    end_date: CalendarDate
    budget_minor: Money | None = None
    preferences: Preferences = Field(default_factory=Preferences)
    explicit_tags: list[UUIDText] = Field(default_factory=list, max_length=20)
    request_text: Annotated[str, Field(max_length=2000)] = ""

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def calendar_date(cls, value):
        return TripCreate.calendar_date(value)


class JobQuery(PageQuery):
    status: list[Literal["queued", "running", "succeeded", "failed", "timed_out", "cancelled"]] = (
        Field(default_factory=list, max_length=6)
    )


class ChatCreate(Input):
    title: Annotated[str, Field(min_length=1, max_length=100)] = "新对话"
    trip_id: UUIDText | None = None


class ChatUpdate(Input):
    title: Annotated[str, Field(min_length=1, max_length=100)]


class MessageCreate(Input):
    message_id: UUIDText
    content: Annotated[str, Field(min_length=1, max_length=4000)]

    @field_validator("content")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("blank message")
        return value


class MessageQuery(Input):
    before_sequence: int | None = Field(default=None, ge=1)
    limit: int = Field(default=20, ge=1, le=50)


class BehaviorCreate(Input):
    event_id: UUIDText
    place_id: UUIDText
    type: Literal["view"]
    occurred_at: datetime

    @field_validator("occurred_at", mode="before")
    @classmethod
    def utc_timestamp(cls, value):
        if not isinstance(value, str) or not value.endswith("Z"):
            raise ValueError("UTC timestamp required")
        return value


class RecommendationQuery(Input):
    city_id: UUIDText | None = None
    kind: Literal["attraction", "hotel", "restaurant"] | None = None
    limit: int = Field(default=10, ge=1, le=20)
    explicit_tags: list[UUIDText] = Field(default_factory=list, max_length=20)
    preferred_tags: list[UUIDText] = Field(default_factory=list, max_length=20)
    price_max_minor: int | None = Field(default=None, ge=0, le=100000000)
    price_unit: Literal["entry", "night", "person"] | None = None
