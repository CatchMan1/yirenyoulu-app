import { http } from '@kit.NetworkKit';
import { AppConstants } from '../common/constants/AppConstants';
import { Envelope, ErrorResponse, TokenPair, LoginResult } from '../models/ApiModels';

export class ApiFailure extends Error {
  code: string;
  requestId: string;
  status: number;
  constructor(code: string, message: string, status: number = 0, requestId: string = '') {
    super(message);
    this.code = code; this.status = status; this.requestId = requestId;
  }
}

// Credentials stay in this process. Restart requires login until protected persistence is verified.
export class ApiClient {
  private static singleton: ApiClient = new ApiClient();
  private access: string = '';
  private refresh: string = '';
  private epoch: number = 0;
  private tokenGeneration: number = 0;
  private refreshing: Promise<void> | null = null;
  onExpired: () => void = () => {};
  private expire(): void { this.clear(); this.onExpired(); }
  static get(): ApiClient { return ApiClient.singleton; }
  clear(): void { this.epoch++; this.access = ''; this.refresh = ''; this.refreshing = null; }
  isAuthenticated(): boolean { return this.access.length > 0; }

  async login(identifier: string, password: string): Promise<void> {
    this.clear();
    const epoch = this.epoch;
    const result = await this.send<LoginResult>('/auth/login', http.RequestMethod.POST,
      JSON.stringify({ identifier: identifier, password: password }), false);
    if (epoch !== this.epoch) { throw new ApiFailure('SESSION_CHANGED', '会话已变更'); }
    if (!result.data) { throw new ApiFailure('INVALID_RESPONSE', '登录响应无效'); }
    const tokens = result.data.tokens;
    if (!tokens || typeof tokens.access_token !== 'string' || typeof tokens.refresh_token !== 'string') {
      throw new ApiFailure('INVALID_RESPONSE', '登录响应无效');
    }
    this.access = tokens.access_token; this.refresh = tokens.refresh_token; this.tokenGeneration++;
  }

  private async rotate(epoch: number): Promise<void> {
    try {
      // Refresh is sent once: an ambiguous network result requires login again.
      const result = await this.send<TokenPair>('/auth/refresh', http.RequestMethod.POST,
        JSON.stringify({ refresh_token: this.refresh }), false);
      if (epoch !== this.epoch) { throw new ApiFailure('SESSION_CHANGED', '会话已变更'); }
      if (!result.data || typeof result.data.access_token !== 'string' || typeof result.data.refresh_token !== 'string') {
        throw new ApiFailure('INVALID_RESPONSE', '会话响应无效');
      }
      this.access = result.data.access_token; this.refresh = result.data.refresh_token; this.tokenGeneration++;
    } catch (error) {
      if (epoch === this.epoch) { this.expire(); }
      throw new ApiFailure('SESSION_INVALID', '请重新登录', 401);
    }
  }

  async request<T>(path: string, method: http.RequestMethod = http.RequestMethod.GET,
    body: string = '', key: string = ''): Promise<Envelope<T>> {
    const epoch = this.epoch; const generation = this.tokenGeneration;
    try {
      const response = await this.send<T>(path, method, body, true, key);
      if (epoch !== this.epoch) { throw new ApiFailure('SESSION_CHANGED', '会话已变更'); }
      return response;
    } catch (error) {
      if (!(error instanceof ApiFailure) || error.status !== 401 || error.code !== 'SESSION_INVALID' || epoch !== this.epoch) { throw error; }
      if (!this.refresh) { this.expire(); throw error; }
      if (generation === this.tokenGeneration) {
        if (!this.refreshing) { this.refreshing = this.rotate(epoch); }
        const pending = this.refreshing;
        try { await pending; } finally { if (this.refreshing === pending) { this.refreshing = null; } }
      }
      if (epoch !== this.epoch) { throw new ApiFailure('SESSION_INVALID', '请重新登录', 401); }
      try {
        const response = await this.send<T>(path, method, body, true, key);
        if (epoch !== this.epoch) { throw new ApiFailure('SESSION_CHANGED', '会话已变更'); }
        return response;
      } catch (retryError) {
        if (retryError instanceof ApiFailure && retryError.status === 401 && retryError.code === 'SESSION_INVALID' && epoch === this.epoch) { this.expire(); }
        throw retryError;
      }
    }
  }

  async send<T>(path: string, method: http.RequestMethod, body: string,
    authorized: boolean, key: string = ''): Promise<Envelope<T>> {
    const request = http.createHttp();
    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (authorized && this.access) { headers['Authorization'] = 'Bearer ' + this.access; }
      if (key) { headers['Idempotency-Key'] = key; }
      const response = await request.request(AppConstants.API_BASE_URL + path, {
        method: method, header: headers, extraData: body,
        connectTimeout: 10000, readTimeout: AppConstants.API_TIMEOUT
      });
      if (response.responseCode === 204) {
        return { data: null, meta: null, request_id: '' };
      }
      if (response.responseCode < 200 || response.responseCode >= 300) {
        const failure = JSON.parse(response.result.toString()) as ErrorResponse;
        if (!failure || !failure.error || typeof failure.error.code !== 'string' || typeof failure.error.message !== 'string') {
          throw new ApiFailure('INVALID_RESPONSE', '服务响应无效', response.responseCode);
        }
        throw new ApiFailure(failure.error.code, failure.error.message, response.responseCode, failure.request_id);
      }
      const envelope = JSON.parse(response.result.toString()) as Envelope<T>;
      if (!envelope || typeof envelope.request_id !== 'string' || envelope.data === undefined) {
        throw new ApiFailure('INVALID_RESPONSE', '服务响应无效');
      }
      return envelope;
    } catch (error) {
      if (error instanceof ApiFailure) { throw error; }
      throw new ApiFailure('NETWORK_ERROR', '网络请求失败，请重试');
    } finally { request.destroy(); }
  }
}

// IDs are request deduplication identifiers, never security credentials.
export function messageId(): string {
  let value = '';
  const chars = '0123456789abcdef';
  for (let i = 0; i < 32; i++) { value += chars[Math.floor(Math.random() * 16)]; }
  return value.slice(0,8) + '-' + value.slice(8,12) + '-4' + value.slice(13,16) + '-8' + value.slice(17,20) + '-' + value.slice(20);
}

export function publicError(error: Error): string {
  return error instanceof ApiFailure ? error.message : '操作失败，请重试';
}
