"""Generated response DTOs; regenerate with scripts/generate_response_models.py."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Output(BaseModel):
    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True)


class Preferences(Output):
    tags: Annotated[list[UUID], Field(max_length=20, json_schema_extra={"uniqueItems": True})]
    pace: Literal["relaxed", "normal", "fast"]


class User(Output):
    id: UUID
    username: Annotated[str, Field(min_length=3, max_length=50, pattern="^[a-z0-9_]{3,50}$")]
    email: Annotated[
        str, Field(min_length=3, max_length=320, json_schema_extra={"format": "email"})
    ]
    email_verified: bool
    nickname: Annotated[str, Field(min_length=0, max_length=50)]
    signature: Annotated[str, Field(min_length=0, max_length=200)]
    preferences: Preferences


class UserResponse(Output):
    data: User
    meta: None
    request_id: UUID


class TokenPair(Output):
    access_token: Annotated[str, Field(min_length=1, max_length=4096)]
    refresh_token: Annotated[str, Field(min_length=1, max_length=4096)]
    token_type: Literal["Bearer"]
    expires_in: Annotated[int, Field(ge=900, le=900)]
    refresh_expires_at: Annotated[
        str, Field(pattern="Z$", json_schema_extra={"format": "date-time"})
    ]


class LoginResult(Output):
    tokens: TokenPair
    user: User


class LoginResultResponse(Output):
    data: LoginResult
    meta: None
    request_id: UUID


class TokenPairResponse(Output):
    data: TokenPair
    meta: None
    request_id: UUID


class DeliveryReceipt(Output):
    status: Literal["accepted"]


class DeliveryReceiptResponse(Output):
    data: DeliveryReceipt
    meta: None
    request_id: UUID


class City(Output):
    id: UUID
    code: Annotated[str, Field(min_length=1, max_length=100)]
    name: Annotated[str, Field(min_length=1, max_length=100)]
    timezone: Literal["Asia/Shanghai"]


class PageMeta(Output):
    page: Annotated[int, Field(ge=1, le=10000)]
    page_size: Annotated[int, Field(ge=1, le=50)]
    total: Annotated[int, Field(ge=0, le=2147483647)]
    has_more: bool


class CityPageResponse(Output):
    data: Annotated[list[City], Field(max_length=50)]
    meta: PageMeta
    request_id: UUID


class NamedEntry(Output):
    id: UUID
    code: Annotated[str, Field(min_length=1, max_length=100)]
    name: Annotated[str, Field(min_length=1, max_length=100)]


class NamedEntryPageResponse(Output):
    data: Annotated[list[NamedEntry], Field(max_length=50)]
    meta: PageMeta
    request_id: UUID


class Coordinates(Output):
    longitude: Annotated[float, Field(ge=-180, le=180)]
    latitude: Annotated[float, Field(ge=-90, le=90)]
    crs: Literal["GCJ-02", "WGS84", "BD09"]


class PriceFact(Output):
    amount_minor: Annotated[int, Field(ge=0, le=100000000)]
    currency: Literal["CNY"]
    unit: Literal["entry", "night", "person"]
    observed_at: (
        Annotated[str, Field(pattern="Z$", json_schema_extra={"format": "date-time"})] | None
    )
    conditions: Annotated[str, Field(min_length=1, max_length=1000)] | None = None


class Estimate(Output):
    amount_minor: Annotated[int, Field(ge=0, le=100000000)]
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    source: Annotated[str, Field(min_length=1, max_length=200)] | None


class Provenance(Output):
    source_name: Annotated[str, Field(min_length=1, max_length=200)]
    source_url: (
        Annotated[str, Field(min_length=1, max_length=2000, json_schema_extra={"format": "uri"})]
        | None
    )
    checked_at: (
        Annotated[str, Field(pattern="Z$", json_schema_extra={"format": "date-time"})] | None
    )


class Place(Output):
    id: UUID
    kind: Literal["attraction", "hotel", "restaurant"]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    city: City
    category: NamedEntry | None
    tags: Annotated[list[NamedEntry], Field(max_length=20)]
    address: Annotated[str, Field(min_length=1, max_length=500)] | None
    coordinates: Coordinates | None
    price: PriceFact | None
    estimate: Estimate | None
    status: Literal["active", "inactive"]
    provenance: Provenance
    is_test: bool


class PlacePageResponse(Output):
    data: Annotated[list[Place], Field(max_length=50)]
    meta: PageMeta
    request_id: UUID


class OpeningInterval(Output):
    weekday: Annotated[int, Field(ge=1, le=7)]
    opens_minute: Annotated[int, Field(ge=0, le=1439)]
    closes_minute: Annotated[int, Field(ge=1, le=1440)]


class OpeningHours(Output):
    model_config = ConfigDict(
        extra="ignore",
        hide_input_in_errors=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {"properties": {"parse_status": {"const": "unparsed"}}},
                    "then": {"properties": {"weekly": {"maxItems": 0}}},
                },
                {
                    "if": {"properties": {"parse_status": {"const": "parsed"}}},
                    "then": {"properties": {"weekly": {"minItems": 1}}},
                },
            ]
        },
    )
    raw_text: Annotated[str, Field(min_length=1, max_length=2000)]
    timezone: Literal["Asia/Shanghai"]
    parse_status: Literal["unparsed", "parsed"]
    weekly: Annotated[list[OpeningInterval], Field(max_length=56)]
    observed_at: (
        Annotated[str, Field(pattern="Z$", json_schema_extra={"format": "date-time"})] | None
    )


class Rating(Output):
    value: Annotated[float, Field(ge=0)]
    scale: Annotated[float, Field(gt=0)]


class PlaceImage(Output):
    url: Annotated[str, Field(min_length=1, max_length=2000, json_schema_extra={"format": "uri"})]
    source_name: Annotated[str, Field(min_length=1, max_length=200)]


class PlaceDetail(Output):
    id: UUID
    kind: Literal["attraction", "hotel", "restaurant"]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    city: City
    category: NamedEntry | None
    tags: Annotated[list[NamedEntry], Field(max_length=20)]
    address: Annotated[str, Field(min_length=1, max_length=500)] | None
    coordinates: Coordinates | None
    price: PriceFact | None
    estimate: Estimate | None
    status: Literal["active", "inactive"]
    provenance: Provenance
    is_test: bool
    description: Annotated[str, Field(min_length=1, max_length=10000)] | None
    opening_hours: OpeningHours | None
    rating: Rating | None
    images: Annotated[list[PlaceImage], Field(max_length=20)]
    hotel_stars: Annotated[int, Field(ge=1, le=5)] | None
    cuisine: Annotated[str, Field(min_length=1, max_length=100)] | None


class PlaceDetailResponse(Output):
    data: PlaceDetail
    meta: None
    request_id: UUID


class NavigationDestination(Output):
    place_id: UUID
    name: Annotated[str, Field(min_length=1, max_length=200)]
    address: Annotated[str, Field(min_length=1, max_length=500)] | None
    coordinates: Coordinates | None


class NavigationResult(Output):
    model_config = ConfigDict(
        extra="ignore",
        hide_input_in_errors=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {"properties": {"status": {"const": "available"}}},
                    "then": {
                        "properties": {
                            "provider": {"enum": ["amap", "google"]},
                            "url": {"type": "string"},
                            "reason": {"type": "null"},
                            "destination": {"properties": {"coordinates": {"type": "object"}}},
                        }
                    },
                },
                {
                    "if": {"properties": {"status": {"const": "unavailable"}}},
                    "then": {"properties": {"url": {"type": "null"}, "reason": {"type": "string"}}},
                },
            ]
        },
    )
    status: Literal["available", "unavailable"]
    provider: Literal["amap", "google", "none"]
    mode: Literal["walking", "driving", "transit", "cycling"]
    destination: NavigationDestination
    url: (
        Annotated[str, Field(min_length=1, max_length=2000, json_schema_extra={"format": "uri"})]
        | None
    )
    reason: (
        Literal["NO_COORDINATES", "UNSUPPORTED_CRS", "PROVIDER_DISABLED", "PROVIDER_ERROR"] | None
    )


class NavigationResultResponse(Output):
    data: NavigationResult
    meta: None
    request_id: UUID


class FavoriteStatus(Output):
    place_id: UUID
    is_favorited: bool


class FavoriteStatusResponse(Output):
    data: FavoriteStatus
    meta: None
    request_id: UUID


class TripSummary(Output):
    id: UUID
    title: Annotated[str, Field(min_length=1, max_length=200)]
    city_id: UUID
    start_date: Annotated[str, Field(json_schema_extra={"format": "date"})]
    end_date: Annotated[str, Field(json_schema_extra={"format": "date"})]
    budget_minor: Annotated[int, Field(ge=0, le=100000000)] | None
    version: Annotated[int, Field(ge=1, le=2147483647)]
    created_at: Annotated[str, Field(pattern="Z$", json_schema_extra={"format": "date-time"})]
    updated_at: Annotated[str, Field(pattern="Z$", json_schema_extra={"format": "date-time"})]


class TripSummaryPageResponse(Output):
    data: Annotated[list[TripSummary], Field(max_length=50)]
    meta: PageMeta
    request_id: UUID


class Snapshot(Output):
    schema_version: Annotated[int, Field(ge=1, le=1)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    kind: Literal["attraction", "hotel", "restaurant"]
    address: Annotated[str, Field(min_length=1, max_length=500)] | None
    coordinates: Coordinates | None
    price: PriceFact | None
    provenance: Provenance
    captured_at: Annotated[str, Field(pattern="Z$", json_schema_extra={"format": "date-time"})]


class TripItem(Output):
    model_config = ConfigDict(
        extra="ignore",
        hide_input_in_errors=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {"snapshot": {"properties": {"kind": {"const": "hotel"}}}}
                    },
                    "then": {
                        "properties": {
                            "start_minute": {"type": "null"},
                            "end_minute": {"type": "null"},
                        }
                    },
                    "else": {
                        "properties": {
                            "start_minute": {"type": "integer"},
                            "end_minute": {"type": "integer"},
                        }
                    },
                }
            ]
        },
    )
    id: UUID
    place_id: UUID
    date: Annotated[str, Field(json_schema_extra={"format": "date"})]
    start_minute: Annotated[int, Field(ge=0, le=1439)] | None
    end_minute: Annotated[int, Field(ge=1, le=1440)] | None
    note: Annotated[str, Field(min_length=0, max_length=1000)]
    snapshot: Snapshot
    current_status: Literal["active", "inactive"]
    estimated_cost_minor: Annotated[int, Field(ge=0, le=100000000)] | None
    estimate_reason: Annotated[str, Field(min_length=1, max_length=500)] | None


class CostSummary(Output):
    model_config = ConfigDict(
        extra="ignore",
        hide_input_in_errors=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {"properties": {"complete": {"const": True}}},
                    "then": {"properties": {"unknown_item_count": {"const": 0}}},
                },
                {
                    "if": {"properties": {"unknown_item_count": {"minimum": 1}}},
                    "then": {"properties": {"complete": {"const": False}}},
                },
            ]
        },
    )
    known_cost_minor: Annotated[int, Field(ge=0, le=9007199254740991)]
    estimated_cost_minor: Annotated[int, Field(ge=0, le=9007199254740991)] | None
    unknown_item_count: Annotated[int, Field(ge=0, le=100)]
    currency: Literal["CNY"]
    complete: bool


class Warning(Output):
    code: Literal[
        "PRICE_UNKNOWN",
        "OPENING_HOURS_UNKNOWN",
        "TRAVEL_TIME_UNKNOWN",
        "COST_INCOMPLETE",
        "ESTIMATE_OVER_BUDGET",
        "PLACE_INACTIVE",
        "SNAPSHOT_MAY_BE_OUTDATED",
        "PREFERENCE_UNSATISFIED",
    ]
    message: Annotated[str, Field(min_length=1, max_length=300)]
    place_id: UUID | None


class Trip(Output):
    id: UUID
    title: Annotated[str, Field(min_length=1, max_length=200)]
    city_id: UUID
    start_date: Annotated[str, Field(json_schema_extra={"format": "date"})]
    end_date: Annotated[str, Field(json_schema_extra={"format": "date"})]
    budget_minor: Annotated[int, Field(ge=0, le=100000000)] | None
    version: Annotated[int, Field(ge=1, le=2147483647)]
    created_at: Annotated[str, Field(pattern="Z$", json_schema_extra={"format": "date-time"})]
    updated_at: Annotated[str, Field(pattern="Z$", json_schema_extra={"format": "date-time"})]
    preferences: Preferences
    items: Annotated[list[TripItem], Field(max_length=100)]
    cost_summary: CostSummary
    warnings: Annotated[list[Warning], Field(max_length=100)]


class TripResponse(Output):
    data: Trip
    meta: None
    request_id: UUID


class Job(Output):
    model_config = ConfigDict(
        extra="ignore",
        hide_input_in_errors=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {"properties": {"status": {"const": "succeeded"}}},
                    "then": {
                        "properties": {"error_code": {"type": "null"}},
                        "oneOf": [
                            {
                                "properties": {
                                    "result_deleted": {"const": False},
                                    "trip_id": {"type": "string", "format": "uuid"},
                                }
                            },
                            {
                                "properties": {
                                    "result_deleted": {"const": True},
                                    "trip_id": {"type": "null"},
                                }
                            },
                        ],
                    },
                },
                {
                    "if": {
                        "properties": {
                            "status": {
                                "enum": ["queued", "running", "failed", "timed_out", "cancelled"]
                            }
                        }
                    },
                    "then": {
                        "properties": {
                            "trip_id": {"type": "null"},
                            "result_deleted": {"const": False},
                        }
                    },
                },
                {
                    "if": {"properties": {"status": {"enum": ["failed", "timed_out"]}}},
                    "then": {"properties": {"error_code": {"type": "string"}}},
                },
                {
                    "if": {"properties": {"status": {"enum": ["queued", "running", "cancelled"]}}},
                    "then": {"properties": {"error_code": {"type": "null"}}},
                },
            ]
        },
    )
    id: UUID
    status: Literal["queued", "running", "succeeded", "failed", "timed_out", "cancelled"]
    trip_id: UUID | None
    result_deleted: bool
    error_code: (
        Literal[
            "JOB_TIMEOUT",
            "NO_CANDIDATES",
            "PLAN_INVALID",
            "BUDGET_EXCEEDED",
            "PROVIDER_UNAVAILABLE",
            "PROVIDER_TIMEOUT",
            "INTERNAL_ERROR",
        ]
        | None
    )
    warnings: Annotated[list[Warning], Field(max_length=100)]
    created_at: Annotated[str, Field(pattern="Z$", json_schema_extra={"format": "date-time"})]
    updated_at: Annotated[str, Field(pattern="Z$", json_schema_extra={"format": "date-time"})]
    deadline: Annotated[str, Field(pattern="Z$", json_schema_extra={"format": "date-time"})]
    provider_mode: Literal["disabled", "mock", "real"]


class JobResponse(Output):
    data: Job
    meta: None
    request_id: UUID


class JobPageResponse(Output):
    data: Annotated[list[Job], Field(max_length=50)]
    meta: PageMeta
    request_id: UUID


class ChatSession(Output):
    id: UUID
    title: Annotated[str, Field(min_length=1, max_length=100)]
    trip_id: UUID | None
    created_at: Annotated[str, Field(pattern="Z$", json_schema_extra={"format": "date-time"})]
    updated_at: Annotated[str, Field(pattern="Z$", json_schema_extra={"format": "date-time"})]


class ChatSessionResponse(Output):
    data: ChatSession
    meta: None
    request_id: UUID


class ChatSessionPageResponse(Output):
    data: Annotated[list[ChatSession], Field(max_length=50)]
    meta: PageMeta
    request_id: UUID


class Message(Output):
    model_config = ConfigDict(
        extra="ignore",
        hide_input_in_errors=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {
                            "role": {"const": "assistant"},
                            "status": {"const": "succeeded"},
                        }
                    },
                    "then": {
                        "properties": {"content": {"minLength": 1}, "error_code": {"type": "null"}}
                    },
                },
                {
                    "if": {"properties": {"role": {"const": "user"}}},
                    "then": {"properties": {"content": {"maxLength": 4000}}},
                },
                {
                    "if": {
                        "properties": {
                            "role": {"const": "assistant"},
                            "status": {"const": "failed"},
                        }
                    },
                    "then": {
                        "properties": {"content": {"const": ""}, "error_code": {"type": "string"}}
                    },
                },
            ]
        },
    )
    id: UUID
    message_id: UUID
    sequence: Annotated[int, Field(ge=1, le=2147483647)]
    role: Literal["user", "assistant"]
    content: Annotated[str, Field(min_length=0, max_length=8000)]
    status: Literal["pending", "running", "succeeded", "failed"]
    error_code: (
        Literal["PROVIDER_UNAVAILABLE", "PROVIDER_TIMEOUT", "INTERNAL_ERROR", "SESSION_BUSY"] | None
    )
    created_at: Annotated[str, Field(pattern="Z$", json_schema_extra={"format": "date-time"})]


class CursorMeta(Output):
    next_before_sequence: Annotated[int, Field(ge=1, le=2147483647)] | None
    has_more: bool


class MessageHistoryResponse(Output):
    data: Annotated[list[Message], Field(max_length=50)]
    meta: CursorMeta
    request_id: UUID


class MessageTurn(Output):
    user_message: Message
    assistant_message: Message
    provider_mode: Literal["disabled", "mock", "real"]


class MessageTurnResponse(Output):
    data: MessageTurn
    meta: None
    request_id: UUID


class BehaviorReceipt(Output):
    event_id: UUID
    status: Literal["accepted", "duplicate"]


class BehaviorReceiptResponse(Output):
    data: BehaviorReceipt
    meta: None
    request_id: UUID


class RecommendationResult(Output):
    items: Annotated[list[Place], Field(max_length=20)]
    reason: Literal["collaborative", "fallback_preferences", "fallback_catalog"]
    algorithm_version: Annotated[str, Field(min_length=1, max_length=100)]


class RecommendationResultResponse(Output):
    data: RecommendationResult
    meta: None
    request_id: UUID


class Health(Output):
    status: Literal["ok", "not_ready"]


class HealthResponse(Output):
    data: Health
    meta: None
    request_id: UUID


class FieldError(Output):
    path: Annotated[str, Field(min_length=1, max_length=200)]
    code: Literal[
        "REQUIRED",
        "UNKNOWN_FIELD",
        "INVALID_TYPE",
        "INVALID_FORMAT",
        "OUT_OF_RANGE",
        "INVALID_ENUM",
        "INVALID_COMBINATION",
    ]


class ErrorBody(Output):
    code: Annotated[str, Field(min_length=1, max_length=100, pattern="^[A-Z][A-Z0-9_]*$")]
    message: Annotated[str, Field(min_length=1, max_length=300)]
    details: Annotated[list[FieldError], Field(max_length=20)]


class ErrorResponse(Output):
    error: ErrorBody
    request_id: UUID


RESPONSE_MODELS = {
    "register": UserResponse,
    "login": LoginResultResponse,
    "refresh": TokenPairResponse,
    "requestPasswordReset": DeliveryReceiptResponse,
    "requestVerification": DeliveryReceiptResponse,
    "getMe": UserResponse,
    "updateMe": UserResponse,
    "listCities": CityPageResponse,
    "listCategories": NamedEntryPageResponse,
    "listTags": NamedEntryPageResponse,
    "listPlaces": PlacePageResponse,
    "getPlace": PlaceDetailResponse,
    "getNavigation": NavigationResultResponse,
    "listFavorites": PlacePageResponse,
    "getFavoriteStatus": FavoriteStatusResponse,
    "listTrips": TripSummaryPageResponse,
    "createTrip": TripResponse,
    "getTrip": TripResponse,
    "updateTrip": TripResponse,
    "addTripItem": TripResponse,
    "updateTripItem": TripResponse,
    "deleteTripItem": TripResponse,
    "createPlanningJob": JobResponse,
    "listPlanningJobs": JobPageResponse,
    "getPlanningJob": JobResponse,
    "cancelPlanningJob": JobResponse,
    "createChatSession": ChatSessionResponse,
    "listChatSessions": ChatSessionPageResponse,
    "getChatSession": ChatSessionResponse,
    "updateChatSession": ChatSessionResponse,
    "listMessages": MessageHistoryResponse,
    "sendMessage": MessageTurnResponse,
    "recordBehavior": BehaviorReceiptResponse,
    "getRecommendations": RecommendationResultResponse,
    "liveness": HealthResponse,
    "readiness": HealthResponse,
}


ERROR_CODES = {
    "register": [400, 409, 413, 415, 422, 429, 500, 503],
    "login": [400, 401, 403, 413, 415, 422, 429, 500, 503],
    "refresh": [400, 401, 403, 413, 415, 422, 429, 500, 503],
    "logout": [401, 403, 422, 429, 500, 400, 413, 415, 503],
    "requestPasswordReset": [400, 413, 415, 422, 429, 500, 503],
    "confirmPasswordReset": [400, 413, 415, 422, 429, 500, 503],
    "requestVerification": [401, 403, 422, 429, 500, 503, 400, 413, 415],
    "confirmVerification": [400, 401, 403, 413, 415, 422, 429, 500, 503],
    "getMe": [401, 403, 422, 429, 500, 400, 413, 415, 503],
    "updateMe": [400, 401, 403, 413, 415, 422, 429, 500, 503],
    "deleteAccount": [400, 401, 403, 413, 415, 422, 429, 500, 503],
    "changePassword": [400, 401, 403, 413, 415, 422, 429, 500, 503],
    "listCities": [422, 429, 500, 400, 413, 415, 503],
    "listCategories": [422, 429, 500, 400, 413, 415, 503],
    "listTags": [422, 429, 500, 400, 413, 415, 503],
    "listPlaces": [422, 429, 500, 400, 413, 415, 503],
    "getPlace": [404, 422, 429, 500, 400, 413, 415, 503],
    "getNavigation": [404, 422, 429, 500, 400, 413, 415, 503],
    "listFavorites": [401, 403, 422, 429, 500, 400, 413, 415, 503],
    "getFavoriteStatus": [401, 403, 422, 429, 500, 400, 413, 415, 503],
    "addFavorite": [401, 403, 404, 422, 429, 500, 400, 413, 415, 503],
    "removeFavorite": [401, 403, 422, 429, 500, 400, 413, 415, 503],
    "listTrips": [401, 403, 422, 429, 500, 400, 413, 415, 503],
    "createTrip": [400, 401, 403, 404, 409, 410, 413, 415, 422, 429, 500, 503],
    "getTrip": [401, 403, 404, 422, 429, 500, 400, 413, 415, 503],
    "updateTrip": [400, 401, 403, 404, 409, 413, 415, 422, 429, 500, 503],
    "deleteTrip": [401, 403, 404, 409, 422, 429, 500, 400, 413, 415, 503],
    "addTripItem": [400, 401, 403, 404, 409, 413, 415, 422, 429, 500, 503],
    "updateTripItem": [400, 401, 403, 404, 409, 413, 415, 422, 429, 500, 503],
    "deleteTripItem": [401, 403, 404, 409, 422, 429, 500, 400, 413, 415, 503],
    "createPlanningJob": [400, 401, 403, 404, 409, 413, 415, 422, 429, 500, 503],
    "listPlanningJobs": [401, 403, 422, 429, 500, 400, 413, 415, 503],
    "getPlanningJob": [401, 403, 404, 422, 429, 500, 400, 413, 415, 503],
    "cancelPlanningJob": [401, 403, 404, 409, 422, 429, 500, 400, 413, 415, 503],
    "createChatSession": [400, 401, 403, 404, 413, 415, 422, 429, 500, 503],
    "listChatSessions": [401, 403, 422, 429, 500, 400, 413, 415, 503],
    "getChatSession": [401, 403, 404, 422, 429, 500, 400, 413, 415, 503],
    "updateChatSession": [400, 401, 403, 404, 413, 415, 422, 429, 500, 503],
    "deleteChatSession": [401, 403, 404, 422, 429, 500, 400, 413, 415, 503],
    "listMessages": [401, 403, 404, 422, 429, 500, 400, 413, 415, 503],
    "sendMessage": [400, 401, 403, 404, 409, 413, 415, 422, 429, 500, 503, 504],
    "recordBehavior": [400, 401, 403, 404, 409, 413, 415, 422, 429, 500, 503],
    "getRecommendations": [401, 403, 422, 429, 500, 400, 413, 415, 503],
    "liveness": [422, 429, 500, 400, 413, 415, 503],
    "readiness": [422, 429, 500, 503, 400, 413, 415],
}
