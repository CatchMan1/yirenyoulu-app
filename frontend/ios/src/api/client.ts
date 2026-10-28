import Ajv2020 from 'ajv/dist/2020';
import addFormats from 'ajv-formats';
import type { ValidateFunction } from 'ajv';
import contract from './contract.json';
import type { Model, Models, Query } from './types';
import type { Session } from '../auth/session';

export class ApiError extends Error {
  constructor(
    public kind: 'network' | 'timeout' | 'cancelled' | 'http' | 'contract',
    message: string,
    public status?: number,
    public code?: string,
    public requestId?: string,
    public details: readonly { path: string; code: string }[] = [],
    public retryAfter?: number,
  ) {
    super(message);
  }
}
const ajv = new Ajv2020({ strict: false, allErrors: false });
addFormats(ajv);
ajv.addSchema(contract);
const validators = new Map<string, ValidateFunction>();
export function decode<K extends keyof Models>(name: K, value: unknown): Model<K> {
  let check = validators.get(name);
  if (!check) {
    check = ajv.compile({ $ref: `yirenyoulu-contract#/components/schemas/${name}` });
    validators.set(name, check);
  }
  if (!check(value)) throw new ApiError('contract', '服务数据格式不符合约定，请稍后重试');
  return value as Model<K>; // Only after runtime schema validation.
}
export type Options = { auth?: boolean; signal?: AbortSignal; idempotencyKey?: string };
export class Transport {
  constructor(
    private base: string,
    private fetcher: typeof fetch = (input, init) => globalThis.fetch(input, init),
  ) {
    const url = new URL(base);
    if (
      !['https:', 'http:'].includes(url.protocol) ||
      url.username ||
      url.password ||
      url.search ||
      url.hash
    )
      throw new Error('无效的服务地址');
    this.base = base.replace(/\/$/, '');
  }
  async request<K extends keyof Models>(
    method: string,
    path: string,
    schema: K,
    body?: unknown,
    options?: Options,
    token?: string,
    query?: Query,
  ): Promise<Model<K>>;
  async request(
    method: string,
    path: string,
    schema: null,
    body?: unknown,
    options?: Options,
    token?: string,
    query?: Query,
  ): Promise<void>;
  async request(
    method: string,
    path: string,
    schema: keyof Models | null,
    body?: unknown,
    options: Options = {},
    token?: string,
    query?: Query,
  ): Promise<Models[keyof Models] | void> {
    if (!path.startsWith('/') || path.startsWith('//'))
      throw new ApiError('contract', '无效的接口路径');
    const url = new URL(this.base + path);
    for (const [key, value] of Object.entries(query ?? {})) {
      if (value == null) continue;
      for (const part of Array.isArray(value) ? value : [value])
        url.searchParams.append(key, String(part));
    }
    const controller = new AbortController();
    let timeout = false;
    const cancel = () => controller.abort();
    if (options.signal?.aborted) controller.abort();
    options.signal?.addEventListener('abort', cancel, { once: true });
    const timer = setTimeout(() => {
      timeout = true;
      controller.abort();
    }, 15000);
    try {
      const headers: Record<string, string> = { Accept: 'application/json' };
      if (body !== undefined) headers['Content-Type'] = 'application/json';
      if (token) headers.Authorization = 'Bearer ' + token;
      if (options.idempotencyKey) headers['Idempotency-Key'] = options.idempotencyKey;
      const response = await this.fetcher(url.toString(), {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
      if (response.status === 204) {
        if (schema !== null) throw new ApiError('contract', '响应缺少必要内容');
        return;
      }
      let json: unknown;
      try {
        json = await response.json();
      } catch {
        throw new ApiError('contract', '服务返回了无法识别的数据', response.status);
      }
      if (!response.ok) {
        const error = decode('ErrorResponse', json);
        throw new ApiError(
          'http',
          error.error.message,
          response.status,
          error.error.code,
          error.request_id,
          error.error.details,
          Number(response.headers.get('Retry-After')) || undefined,
        );
      }
      if (schema === null)
        throw new ApiError('contract', '服务返回状态与约定不符', response.status);
      return decode(schema, json);
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (controller.signal.aborted)
        throw new ApiError(
          timeout ? 'timeout' : 'cancelled',
          timeout ? '请求超时，请重试' : '操作已取消',
        );
      throw new ApiError('network', '连接失败，请检查网络和服务地址');
    } finally {
      clearTimeout(timer);
      options.signal?.removeEventListener('abort', cancel);
    }
  }
}
export class ApiClient {
  constructor(
    private transport: Transport,
    private session: Session,
  ) {}
  get<K extends keyof Models>(path: string, schema: K, query?: Query, options: Options = {}) {
    return this.execute('GET', path, schema, undefined, options, query);
  }
  send<K extends keyof Models>(
    method: string,
    path: string,
    schema: K,
    body?: unknown,
    options?: Options,
  ): Promise<Model<K>>;
  send(
    method: string,
    path: string,
    schema: null,
    body?: unknown,
    options?: Options,
  ): Promise<void>;
  send(
    method: string,
    path: string,
    schema: keyof Models | null,
    body?: unknown,
    options: Options = {},
  ) {
    return schema === null
      ? this.execute(method, path, null, body, options)
      : this.execute(method, path, schema, body, options);
  }
  private async execute<K extends keyof Models>(
    method: string,
    path: string,
    schema: K,
    body: unknown,
    options: Options,
    query?: Query,
  ): Promise<Model<K>>;
  private async execute(
    method: string,
    path: string,
    schema: null,
    body: unknown,
    options: Options,
    query?: Query,
  ): Promise<void>;
  private async execute(
    method: string,
    path: string,
    schema: keyof Models | null,
    body: unknown,
    options: Options,
    query?: Query,
  ): Promise<Models[keyof Models] | void> {
    const stamp = this.session.stamp();
    if (options.auth && !this.session.accessToken())
      throw new ApiError('http', '请先登录', 401, 'SESSION_INVALID');
    const perform = () =>
      schema === null
        ? this.transport.request(
            method,
            path,
            null,
            body,
            options,
            this.session.accessToken(),
            query,
          )
        : this.transport.request(
            method,
            path,
            schema,
            body,
            options,
            this.session.accessToken(),
            query,
          );
    try {
      let result;
      try {
        result = await perform();
      } catch (error) {
        if (
          !(error instanceof ApiError) ||
          error.status !== 401 ||
          error.code !== 'SESSION_INVALID'
        )
          throw error;
        await this.session.recover(stamp);
        // Only reads and server-defined idempotent writes may be replayed.
        if (!['GET', 'PUT'].includes(method) && !options.idempotencyKey)
          throw new ApiError('http', '登录已恢复，请核对后重新提交', 401, 'RETRY_REQUIRED');
        result = await perform();
      }
      if (this.session.stamp().epoch !== stamp.epoch) throw new ApiError('cancelled', '账户已切换');
      return result;
    } catch (error) {
      if (this.session.stamp().epoch !== stamp.epoch) throw new ApiError('cancelled', '账户已切换');
      if (error instanceof ApiError && error.status === 403 && error.code === 'ACCOUNT_DISABLED')
        await this.session.invalidate('账户当前不可用，请联系支持或重新登录');
      throw error;
    }
  }
}
