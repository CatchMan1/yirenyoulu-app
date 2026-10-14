import { http } from '@kit.NetworkKit';
import { ApiClient, ApiFailure } from './ApiClient';
import { checkPlace, checkDetail, checkTrip, checkJob, checkSession, checkMessage, checkUser, checkCity, checkNamed, checkPage, checkCursor, checkSummary } from './DataGuard';
import { Place, PlaceDetail, Trip, TripSummary, Job, ChatSession, Message, MessageTurn, User, City, RecommendationResult, NavigationResult, PageMeta, CursorMeta, NamedEntry, Envelope } from '../models/ApiModels';

export class TravelApi {
  client: ApiClient = ApiClient.get();
  async data<T>(path: string, method: http.RequestMethod = http.RequestMethod.GET, body: string = '', key: string = ''): Promise<T> {
    const envelope = await this.client.request<T>(path, method, body, key);
    if (envelope.data === null) { throw new ApiFailure('INVALID_RESPONSE', '缺少服务数据'); }
    return envelope.data;
  }
  async cities(): Promise<City[]> {
    const cities = await this.data<City[]>('/cities?page_size=50');
    if (!Array.isArray(cities)) { throw new ApiFailure('INVALID_RESPONSE', '城市响应无效'); }
    cities.forEach((city: City) => checkCity(city)); return cities;
  }
  async places(query: string): Promise<Envelope<Place[]>> {
    const envelope = await this.client.request<Place[]>('/places?' + query);
    if (!Array.isArray(envelope.data)) { throw new ApiFailure('INVALID_RESPONSE', '地点响应无效'); }
    envelope.data.forEach((place: Place) => checkPlace(place)); checkPage(envelope.meta as PageMeta);
    return envelope;
  }
  async recommendations(): Promise<RecommendationResult> {
    const result = await this.data<RecommendationResult>('/recommendations');
    if (!result || !Array.isArray(result.items)) { throw new ApiFailure('INVALID_RESPONSE', '推荐响应无效'); }
    result.items.forEach(place => checkPlace(place)); return result;
  }
  async place(id: string): Promise<PlaceDetail> {
    const place = await this.data<PlaceDetail>('/places/' + encodeURIComponent(id)); checkDetail(place); return place;
  }
  private async page<T>(path: string, page: number, validate: (value: T) => void): Promise<Envelope<T[]>> {
    const envelope = await this.client.request<T[]>(path + '?page_size=50&page=' + page);
    if (!Array.isArray(envelope.data)) { throw new ApiFailure('INVALID_RESPONSE', '列表响应无效'); }
    envelope.data.forEach(validate); checkPage(envelope.meta as PageMeta); return envelope;
  }
  async favorites(page: number = 1): Promise<Envelope<Place[]>> {
    return this.page<Place>('/favorites', page, (place: Place) => checkPlace(place));
  }
  async favorite(id: string, add: boolean): Promise<void> {
    await this.client.request<null>('/favorites/' + encodeURIComponent(id), add ? http.RequestMethod.PUT : http.RequestMethod.DELETE);
  }
  async trips(page: number = 1): Promise<Envelope<TripSummary[]>> {
    return this.page<TripSummary>('/trips', page, (value: TripSummary) => checkSummary(value));
  }
  async tags(): Promise<NamedEntry[]> {
    const tags = await this.data<NamedEntry[]>('/tags?page_size=50');
    if (!Array.isArray(tags)) { throw new ApiFailure('INVALID_RESPONSE', '标签响应无效'); }
    tags.forEach((tag: NamedEntry) => checkNamed(tag)); return tags;
  }
  async trip(id: string): Promise<Trip> {
    const trip = await this.data<Trip>('/trips/' + encodeURIComponent(id)); checkTrip(trip); return trip;
  }
  async mutateTrip(path: string, method: http.RequestMethod, body: string, key: string = ''): Promise<Trip> {
    const trip = await this.data<Trip>(path, method, body, key); checkTrip(trip); return trip;
  }
  async jobs(page: number = 1): Promise<Envelope<Job[]>> {
    return this.page<Job>('/planning-jobs', page, (value: Job) => checkJob(value));
  }
  async job(id: string, cancel: boolean = false): Promise<Job> {
    const job = await this.data<Job>('/planning-jobs/' + encodeURIComponent(id), cancel ? http.RequestMethod.DELETE : http.RequestMethod.GET); checkJob(job); return job;
  }
  async createJob(body: string, key: string): Promise<Job> {
    const job = await this.data<Job>('/planning-jobs', http.RequestMethod.POST, body, key); checkJob(job); return job;
  }
  async me(): Promise<User> { const user = await this.data<User>('/me'); checkUser(user); return user; }
  async sessions(page: number = 1): Promise<Envelope<ChatSession[]>> {
    return this.page<ChatSession>('/chat-sessions', page, (value: ChatSession) => checkSession(value));
  }
  async createSession(body: string): Promise<ChatSession> {
    const session = await this.data<ChatSession>('/chat-sessions', http.RequestMethod.POST, body); checkSession(session); return session;
  }
  async messages(id: string, before: number | null = null): Promise<Envelope<Message[]>> {
    const envelope = await this.client.request<Message[]>('/chat-sessions/' + encodeURIComponent(id) + '/messages?limit=40' + (before === null ? '' : '&before_sequence=' + before));
    if (!Array.isArray(envelope.data)) { throw new ApiFailure('INVALID_RESPONSE', '消息响应无效'); }
    envelope.data.forEach((message: Message) => checkMessage(message)); checkCursor(envelope.meta as CursorMeta); return envelope;
  }
  async send(id: string, body: string): Promise<MessageTurn> {
    const turn = await this.data<MessageTurn>('/chat-sessions/' + encodeURIComponent(id) + '/messages', http.RequestMethod.POST, body);
    if (!turn) { throw new ApiFailure('INVALID_RESPONSE', '消息响应无效'); }
    checkMessage(turn.user_message); checkMessage(turn.assistant_message); return turn;
  }
}
