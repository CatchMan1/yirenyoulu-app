/** V1 wire DTOs. Source: the reviewed OpenAPI contract. */
export interface PageMeta {
  page: number;
  page_size: number;
  total: number;
  has_more: boolean;
}

export interface CursorMeta {
  next_before_sequence: number | null;
  has_more: boolean;
}

export interface FieldError {
  path: string;
  code: "REQUIRED" | "UNKNOWN_FIELD" | "INVALID_TYPE" | "INVALID_FORMAT" | "OUT_OF_RANGE" | "INVALID_ENUM" | "INVALID_COMBINATION";
}

export interface ErrorBody {
  code: string;
  message: string;
  details: FieldError[];
}

export interface ErrorResponse {
  error: ErrorBody;
  request_id: string;
}

export interface Warning {
  code: "PRICE_UNKNOWN" | "OPENING_HOURS_UNKNOWN" | "TRAVEL_TIME_UNKNOWN" | "COST_INCOMPLETE" | "ESTIMATE_OVER_BUDGET" | "PLACE_INACTIVE" | "SNAPSHOT_MAY_BE_OUTDATED" | "PREFERENCE_UNSATISFIED";
  message: string;
  place_id: string | null;
}

export interface Preferences {
  tags: string[];
  pace: "relaxed" | "normal" | "fast";
}

export interface Coordinates {
  longitude: number;
  latitude: number;
  crs: "GCJ-02" | "WGS84" | "BD09";
}

export interface PriceFact {
  amount_minor: number;
  currency: "CNY";
  unit: "entry" | "night" | "person";
  observed_at: string | null;
  conditions?: string | null;
}

export interface Estimate {
  amount_minor: number;
  reason: string;
  source: string | null;
}

export interface Provenance {
  source_name: string;
  source_url: string | null;
  checked_at: string | null;
}

export interface City {
  id: string;
  code: string;
  name: string;
  timezone: "Asia/Shanghai";
}

export interface NamedEntry {
  id: string;
  code: string;
  name: string;
}

export interface Rating {
  value: number;
  scale: number;
}

export interface OpeningInterval {
  weekday: number;
  opens_minute: number;
  closes_minute: number;
}

export interface OpeningHours {
  raw_text: string;
  timezone: "Asia/Shanghai";
  parse_status: "unparsed" | "parsed";
  weekly: OpeningInterval[];
  observed_at: string | null;
}

export interface PlaceImage {
  url: string;
  source_name: string;
}

export interface Place {
  id: string;
  kind: "attraction" | "hotel" | "restaurant";
  name: string;
  city: City;
  category: NamedEntry | null;
  tags: NamedEntry[];
  address: string | null;
  coordinates: Coordinates | null;
  price: PriceFact | null;
  estimate: Estimate | null;
  status: "active" | "inactive";
  provenance: Provenance;
  is_test: boolean;
}

export interface PlaceDetail {
  id: string;
  kind: "attraction" | "hotel" | "restaurant";
  name: string;
  city: City;
  category: NamedEntry | null;
  tags: NamedEntry[];
  address: string | null;
  coordinates: Coordinates | null;
  price: PriceFact | null;
  estimate: Estimate | null;
  status: "active" | "inactive";
  provenance: Provenance;
  is_test: boolean;
  description: string | null;
  opening_hours: OpeningHours | null;
  rating: Rating | null;
  images: PlaceImage[];
  hotel_stars: number | null;
  cuisine: string | null;
}

export interface User {
  id: string;
  username: string;
  email: string;
  email_verified: boolean;
  nickname: string;
  signature: string;
  preferences: Preferences;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: "Bearer";
  expires_in: number;
  refresh_expires_at: string;
}

export interface LoginResult {
  tokens: TokenPair;
  user: User;
}

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
  nickname?: string;
}

export interface LoginRequest {
  identifier: string;
  password: string;
}

export interface RefreshRequest {
  refresh_token: string;
}

export interface ProfileUpdate {
  nickname?: string;
  signature?: string;
  preferences?: PreferencesInput;
}

export interface PasswordChange {
  current_password: string;
  new_password: string;
}

export interface AccountDelete {
  current_password: string;
}

export interface RecoveryRequest {
  email: string;
}

export interface RecoveryConfirm {
  token: string;
  new_password: string;
}

export interface VerificationConfirm {
  token: string;
}

export interface DeliveryReceipt {
  status: "accepted";
}

export interface Snapshot {
  schema_version: number;
  name: string;
  kind: "attraction" | "hotel" | "restaurant";
  address: string | null;
  coordinates: Coordinates | null;
  price: PriceFact | null;
  provenance: Provenance;
  captured_at: string;
}

export interface TripItem {
  id: string;
  place_id: string;
  date: string;
  start_minute: number | null;
  end_minute: number | null;
  note: string;
  snapshot: Snapshot;
  current_status: "active" | "inactive";
  estimated_cost_minor: number | null;
  estimate_reason: string | null;
}

export interface CostSummary {
  known_cost_minor: number;
  estimated_cost_minor: number | null;
  unknown_item_count: number;
  currency: "CNY";
  complete: boolean;
}

export interface TripSummary {
  id: string;
  title: string;
  city_id: string;
  start_date: string;
  end_date: string;
  budget_minor: number | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface Trip {
  id: string;
  title: string;
  city_id: string;
  start_date: string;
  end_date: string;
  budget_minor: number | null;
  version: number;
  created_at: string;
  updated_at: string;
  preferences: Preferences;
  items: TripItem[];
  cost_summary: CostSummary;
  warnings: Warning[];
}

export interface TripCreate {
  title: string;
  city_id: string;
  start_date: string;
  end_date: string;
  budget_minor?: number | null;
  preferences?: PreferencesInput;
}

export interface TripUpdate {
  version: number;
  title?: string;
  start_date?: string;
  end_date?: string;
  budget_minor?: number | null;
  preferences?: PreferencesInput;
}

export interface TripItemCreate {
  version: number;
  place_id: string;
  date: string;
  start_minute: number | null;
  end_minute: number | null;
  note?: string;
}

export interface TripItemUpdate {
  version: number;
  place_id?: string;
  date?: string;
  start_minute?: number | null;
  end_minute?: number | null;
  note?: string;
}

export interface PlanningRequest {
  city_id: string;
  start_date: string;
  end_date: string;
  budget_minor?: number | null;
  preferences?: PreferencesInput;
  explicit_tags?: string[];
  request_text?: string;
}

export interface Job {
  id: string;
  status: "queued" | "running" | "succeeded" | "failed" | "timed_out" | "cancelled";
  trip_id: string | null;
  result_deleted: boolean;
  error_code: "JOB_TIMEOUT" | "NO_CANDIDATES" | "PLAN_INVALID" | "BUDGET_EXCEEDED" | "PROVIDER_UNAVAILABLE" | "PROVIDER_TIMEOUT" | "INTERNAL_ERROR" | null;
  warnings: Warning[];
  created_at: string;
  updated_at: string;
  deadline: string;
  provider_mode: "disabled" | "mock" | "real";
}

export interface ChatSession {
  id: string;
  title: string;
  trip_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChatSessionCreate {
  title?: string;
  trip_id?: string | null;
}

export interface ChatSessionUpdate {
  title: string;
}

export interface Message {
  id: string;
  message_id: string;
  sequence: number;
  role: "user" | "assistant";
  content: string;
  status: "pending" | "running" | "succeeded" | "failed";
  error_code: "PROVIDER_UNAVAILABLE" | "PROVIDER_TIMEOUT" | "INTERNAL_ERROR" | "SESSION_BUSY" | null;
  created_at: string;
}

export interface MessageCreate {
  message_id: string;
  content: string;
}

export interface MessageTurn {
  user_message: Message;
  assistant_message: Message;
  provider_mode: "disabled" | "mock" | "real";
}

export interface BehaviorCreate {
  event_id: string;
  place_id: string;
  type: "view";
  occurred_at: string;
}

export interface BehaviorReceipt {
  event_id: string;
  status: "accepted" | "duplicate";
}

export interface RecommendationResult {
  items: Place[];
  reason: "collaborative" | "fallback_preferences" | "fallback_catalog";
  algorithm_version: string;
}

export interface NavigationDestination {
  place_id: string;
  name: string;
  address: string | null;
  coordinates: Coordinates | null;
}

export interface NavigationResult {
  status: "available" | "unavailable";
  provider: "amap" | "google" | "none";
  mode: "walking" | "driving" | "transit" | "cycling";
  destination: NavigationDestination;
  url: string | null;
  reason: "NO_COORDINATES" | "UNSUPPORTED_CRS" | "PROVIDER_DISABLED" | "PROVIDER_ERROR" | null;
}

export interface Health {
  status: "ok" | "not_ready";
}

export interface UserResponse {
  data: User;
  meta: null;
  request_id: string;
}

export interface LoginResultResponse {
  data: LoginResult;
  meta: null;
  request_id: string;
}

export interface TokenPairResponse {
  data: TokenPair;
  meta: null;
  request_id: string;
}

export interface PlaceDetailResponse {
  data: PlaceDetail;
  meta: null;
  request_id: string;
}

export interface TripResponse {
  data: Trip;
  meta: null;
  request_id: string;
}

export interface JobResponse {
  data: Job;
  meta: null;
  request_id: string;
}

export interface ChatSessionResponse {
  data: ChatSession;
  meta: null;
  request_id: string;
}

export interface MessageTurnResponse {
  data: MessageTurn;
  meta: null;
  request_id: string;
}

export interface DeliveryReceiptResponse {
  data: DeliveryReceipt;
  meta: null;
  request_id: string;
}

export interface BehaviorReceiptResponse {
  data: BehaviorReceipt;
  meta: null;
  request_id: string;
}

export interface RecommendationResultResponse {
  data: RecommendationResult;
  meta: null;
  request_id: string;
}

export interface NavigationResultResponse {
  data: NavigationResult;
  meta: null;
  request_id: string;
}

export interface HealthResponse {
  data: Health;
  meta: null;
  request_id: string;
}

export interface CityPageResponse {
  data: City[];
  meta: PageMeta;
  request_id: string;
}

export interface NamedEntryPageResponse {
  data: NamedEntry[];
  meta: PageMeta;
  request_id: string;
}

export interface PlacePageResponse {
  data: Place[];
  meta: PageMeta;
  request_id: string;
}

export interface TripSummaryPageResponse {
  data: TripSummary[];
  meta: PageMeta;
  request_id: string;
}

export interface JobPageResponse {
  data: Job[];
  meta: PageMeta;
  request_id: string;
}

export interface ChatSessionPageResponse {
  data: ChatSession[];
  meta: PageMeta;
  request_id: string;
}

export interface MessageHistoryResponse {
  data: Message[];
  meta: CursorMeta;
  request_id: string;
}

export interface PreferencesInput {
  tags?: string[];
  pace?: "relaxed" | "normal" | "fast";
}

export interface FavoriteStatus {
  place_id: string;
  is_favorited: boolean;
}

export interface FavoriteStatusResponse {
  data: FavoriteStatus;
  meta: null;
  request_id: string;
}

export interface Envelope<T> {
  data: T | null;
  meta: PageMeta | CursorMeta | null;
  request_id: string;
}
export interface RouteId { id: string; }
