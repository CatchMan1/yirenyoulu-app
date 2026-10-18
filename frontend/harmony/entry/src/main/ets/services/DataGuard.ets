import { Place, PlaceDetail, Trip, TripSummary, Job, ChatSession, Message, User, PageMeta, CursorMeta, City, NamedEntry, Coordinates, PriceFact, Provenance, Preferences, Warning, Snapshot } from '../models/ApiModels';
import { ApiFailure } from './ApiClient';

function invalid(): void { throw new ApiFailure('INVALID_RESPONSE', '服务数据格式无效'); }
function text(value: string, min: number, max: number): boolean { return typeof value === 'string' && value.length >= min && value.length <= max; }
function nullableText(value: string | null, max: number): boolean { return value === null || text(value, 1, max); }
function integer(value: number, min: number, max: number): boolean { return typeof value === 'number' && Number.isSafeInteger(value) && value >= min && value <= max; }
function calendar(value: string): boolean { return text(value, 10, 10) && /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value; }
function utc(value: string): boolean { return typeof value === 'string' && /Z$/.test(value) && Number.isFinite(Date.parse(value)); }
export function validId(id: string): boolean { return typeof id === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id); }
export function checkNamed(value: NamedEntry): void { if (!value || !validId(value.id) || !text(value.code,1,100) || !text(value.name,1,100)) { invalid(); } }
export function checkCity(value: City): void { checkNamed(value); if (value.timezone !== 'Asia/Shanghai') { invalid(); } }
function checkCoordinates(value: Coordinates): void {
  if (!value || typeof value.longitude !== 'number' || typeof value.latitude !== 'number' || !Number.isFinite(value.longitude) || !Number.isFinite(value.latitude) || Math.abs(value.longitude) > 180 || Math.abs(value.latitude) > 90 || !['WGS84','GCJ-02','BD09'].includes(value.crs)) { invalid(); }
}
function checkPrice(value: PriceFact): void {
  if (!value || !integer(value.amount_minor,0,100000000) || value.currency !== 'CNY' || !['entry','night','person'].includes(value.unit) || (value.observed_at !== null && !utc(value.observed_at))) { invalid(); }
}
function checkProvenance(value: Provenance): void {
  if (!value || !text(value.source_name,1,200) || !nullableText(value.source_url,2000) || (value.checked_at !== null && !utc(value.checked_at))) { invalid(); }
}
function checkPreferences(value: Preferences): void {
  if (!value || !Array.isArray(value.tags) || value.tags.length > 20 || !['relaxed','normal','fast'].includes(value.pace)) { invalid(); }
  value.tags.forEach((id: string, index: number) => { if (!validId(id) || value.tags.indexOf(id) !== index) { invalid(); } });
}
function checkWarnings(values: Warning[]): void {
  if (!Array.isArray(values) || values.length > 100) { invalid(); }
  values.forEach((value: Warning) => {
    if (!value || !['PRICE_UNKNOWN','OPENING_HOURS_UNKNOWN','TRAVEL_TIME_UNKNOWN','COST_INCOMPLETE','ESTIMATE_OVER_BUDGET','PLACE_INACTIVE','SNAPSHOT_MAY_BE_OUTDATED','PREFERENCE_UNSATISFIED'].includes(value.code) || !text(value.message,1,300) || (value.place_id !== null && !validId(value.place_id))) { invalid(); }
  });
}
export function checkPlace(place: Place): void {
  if (!place || !validId(place.id) || !text(place.name,1,200) || !['attraction','hotel','restaurant'].includes(place.kind) || !['active','inactive'].includes(place.status) || !Array.isArray(place.tags) || place.tags.length > 20 || typeof place.is_test !== 'boolean' || !nullableText(place.address,500)) { invalid(); }
  checkCity(place.city); checkProvenance(place.provenance); place.tags.forEach((tag: NamedEntry) => checkNamed(tag));
  if (place.category !== null) { checkNamed(place.category); }
  if (place.coordinates !== null) { checkCoordinates(place.coordinates); }
  if (place.price !== null) { checkPrice(place.price); }
  if (place.estimate !== null && (!place.estimate || !integer(place.estimate.amount_minor,0,100000000) || !text(place.estimate.reason,1,500) || !nullableText(place.estimate.source,200))) { invalid(); }
}
export function checkDetail(place: PlaceDetail): void {
  checkPlace(place);
  if (!nullableText(place.description,10000) || !Array.isArray(place.images) || place.images.length > 20 || !nullableText(place.cuisine,100) || (place.hotel_stars !== null && (!integer(place.hotel_stars,1,5) || place.kind !== 'hotel'))) { invalid(); }
  place.images.forEach(image => { if (!image || !text(image.url,1,2000) || !text(image.source_name,1,200)) { invalid(); } });
  if (place.rating !== null && (!place.rating || !Number.isFinite(place.rating.value) || !Number.isFinite(place.rating.scale) || place.rating.scale <= 0 || place.rating.value < 0 || place.rating.value > place.rating.scale)) { invalid(); }
  if (place.opening_hours !== null) {
    const value = place.opening_hours;
    if (!value || !text(value.raw_text,1,2000) || value.timezone !== 'Asia/Shanghai' || !['parsed','unparsed'].includes(value.parse_status) || !Array.isArray(value.weekly) || value.weekly.length > 56 || (value.observed_at !== null && !utc(value.observed_at))) { invalid(); }
    if ((value.parse_status === 'parsed' && value.weekly.length === 0) || (value.parse_status === 'unparsed' && value.weekly.length !== 0)) { invalid(); }
    value.weekly.forEach(interval => { if (!interval || !integer(interval.weekday,1,7) || !integer(interval.opens_minute,0,1439) || !integer(interval.closes_minute,1,1440) || interval.opens_minute >= interval.closes_minute) { invalid(); } });
  }
}
export function checkSummary(trip: TripSummary): void {
  if (!trip || !validId(trip.id) || !validId(trip.city_id) || !text(trip.title,1,200) || !integer(trip.version,1,2147483647) || !calendar(trip.start_date) || !calendar(trip.end_date) || Date.parse(trip.end_date) < Date.parse(trip.start_date) || Date.parse(trip.end_date) - Date.parse(trip.start_date) > 13 * 86400000 || (trip.budget_minor !== null && !integer(trip.budget_minor,0,100000000)) || !utc(trip.created_at) || !utc(trip.updated_at)) { invalid(); }
}
function checkSnapshot(value: Snapshot): void {
  if (!value || value.schema_version !== 1 || !text(value.name,1,200) || !['attraction','hotel','restaurant'].includes(value.kind) || !nullableText(value.address,500) || !utc(value.captured_at)) { invalid(); }
  checkProvenance(value.provenance);
  if (value.coordinates !== null) { checkCoordinates(value.coordinates); }
  if (value.price !== null) { checkPrice(value.price); }
}
export function checkTrip(trip: Trip): void {
  checkSummary(trip); checkPreferences(trip.preferences); checkWarnings(trip.warnings);
  if (!Array.isArray(trip.items) || trip.items.length > 100 || !trip.cost_summary) { invalid(); }
  const costs = trip.cost_summary;
  if (!integer(costs.known_cost_minor,0,9007199254740991) || (costs.estimated_cost_minor !== null && !integer(costs.estimated_cost_minor,0,9007199254740991)) || !integer(costs.unknown_item_count,0,100) || costs.currency !== 'CNY' || typeof costs.complete !== 'boolean' || (costs.complete && costs.unknown_item_count > 0)) { invalid(); }
  trip.items.forEach(item => {
    if (!item || !validId(item.id) || !validId(item.place_id) || !calendar(item.date) || !text(item.note,0,1000) || !['active','inactive'].includes(item.current_status) || (item.estimated_cost_minor !== null && !integer(item.estimated_cost_minor,0,100000000)) || !nullableText(item.estimate_reason,500)) { invalid(); }
    checkSnapshot(item.snapshot);
    if (item.snapshot.kind === 'hotel') { if (item.start_minute !== null || item.end_minute !== null) { invalid(); } }
    else if (item.start_minute === null || item.end_minute === null || !integer(item.start_minute,0,1439) || !integer(item.end_minute,1,1440) || item.start_minute >= item.end_minute) { invalid(); }
  });
}
export function checkJob(job: Job): void {
  if (!job || !validId(job.id) || !['queued','running','succeeded','failed','timed_out','cancelled'].includes(job.status) || !['disabled','mock','real'].includes(job.provider_mode) || typeof job.result_deleted !== 'boolean' || (job.trip_id !== null && !validId(job.trip_id)) || !utc(job.created_at) || !utc(job.updated_at) || !utc(job.deadline)) { invalid(); }
  checkWarnings(job.warnings);
  if (job.error_code !== null && !['JOB_TIMEOUT','NO_CANDIDATES','PLAN_INVALID','BUDGET_EXCEEDED','PROVIDER_UNAVAILABLE','PROVIDER_TIMEOUT','INTERNAL_ERROR'].includes(job.error_code)) { invalid(); }
  if ((job.status === 'succeeded' && ((job.result_deleted && job.trip_id !== null) || (!job.result_deleted && job.trip_id === null) || job.error_code !== null)) || (job.status !== 'succeeded' && (job.trip_id !== null || job.result_deleted)) || (['failed','timed_out'].includes(job.status) && job.error_code === null)) { invalid(); }
}
export function checkSession(session: ChatSession): void {
  if (!session || !validId(session.id) || !text(session.title,1,100) || (session.trip_id !== null && !validId(session.trip_id)) || !utc(session.created_at) || !utc(session.updated_at)) { invalid(); }
}
export function checkMessage(message: Message): void {
  if (!message || !validId(message.id) || !validId(message.message_id) || !integer(message.sequence,1,2147483647) || !text(message.content,0,8000) || !['user','assistant'].includes(message.role) || !['pending','running','succeeded','failed'].includes(message.status) || !utc(message.created_at) || (message.error_code !== null && !['PROVIDER_UNAVAILABLE','PROVIDER_TIMEOUT','INTERNAL_ERROR','SESSION_BUSY'].includes(message.error_code))) { invalid(); }
}
export function checkUser(user: User): void {
  if (!user || !validId(user.id) || !text(user.username,3,50) || !/^[a-z0-9_]{3,50}$/.test(user.username) || !text(user.email,3,320) || typeof user.email_verified !== 'boolean' || !text(user.nickname,0,50) || !text(user.signature,0,200)) { invalid(); }
  checkPreferences(user.preferences);
}
export function checkPage(meta: PageMeta): void {
  if (!meta || !integer(meta.page,1,10000) || !integer(meta.page_size,1,50) || !integer(meta.total,0,2147483647) || typeof meta.has_more !== 'boolean') { invalid(); }
}
export function checkCursor(meta: CursorMeta): void {
  if (!meta || typeof meta.has_more !== 'boolean' || (meta.next_before_sequence !== null && !integer(meta.next_before_sequence,1,2147483647))) { invalid(); }
}
export function priceText(place: Place): string {
  if (!place.price) { return '价格未知'; }
  return '¥' + (place.price.amount_minor / 100).toFixed(2) + '/' + place.price.unit + (place.price.conditions ? '（' + place.price.conditions + '）' : '');
}
