import { ApiError } from '../api/client';
import type { Model } from '../api/types';
export interface CredentialStore {
  get(): Promise<string | null>;
  set(value: string): Promise<void>;
  remove(): Promise<void>;
}
interface AuthTransport {
  login(identifier: string, password: string): Promise<Model<'LoginResult'>>;
  refresh(token: string): Promise<Model<'TokenPair'>>;
  me(token: string): Promise<Model<'User'>>;
  logout(token: string): Promise<void>;
}
export type SessionState = {
  status: 'bootstrapping' | 'anonymous' | 'authenticated' | 'refreshing';
  user: Model<'User'> | null;
  epoch: number;
  generation: number;
  notice?: string;
};
export type Stamp = { epoch: number; generation: number };
export class Session {
  private state: SessionState = { status: 'bootstrapping', user: null, epoch: 0, generation: 0 };
  private access: string | undefined;
  private refreshToken: string | undefined;
  private queue: Promise<unknown> = Promise.resolve();
  private flight: { epoch: number; promise: Promise<void> } | undefined;
  private listeners = new Set<() => void>();
  constructor(
    private store: CredentialStore,
    private auth: AuthTransport,
  ) {}
  snapshot = () => this.state;
  subscribe = (fn: () => void) => {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  };
  stamp = (): Stamp => ({ epoch: this.state.epoch, generation: this.state.generation });
  accessToken = () => this.access;
  private emit(changes: Partial<SessionState>) {
    this.state = { ...this.state, ...changes };
    for (const fn of this.listeners) fn();
  }
  private serial<T>(fn: () => Promise<T>): Promise<T> {
    const task = this.queue.then(fn);
    this.queue = task.catch(() => {});
    return task;
  }
  private current(epoch: number) {
    if (epoch !== this.state.epoch) throw new ApiError('cancelled', '账户已切换');
  }
  private async clear(epoch: number) {
    if (epoch !== this.state.epoch) return;
    this.access = undefined;
    this.refreshToken = undefined;
    this.emit({
      user: null,
      status: 'anonymous',
      epoch: epoch + 1,
      notice: '登录已过期，请重新登录',
    });
    await this.serial(() => this.store.remove());
  }
  private async accept(pair: Model<'TokenPair'>, epoch: number, user: Model<'User'> | null) {
    this.current(epoch);
    try {
      await this.serial(async () => {
        this.current(epoch);
        await this.store.set(pair.refresh_token);
      });
    } catch (error) {
      if (epoch === this.state.epoch) await this.clear(epoch);
      throw error instanceof ApiError ? error : new ApiError('http', '安全存储不可用，请重新登录');
    }
    this.current(epoch);
    this.access = pair.access_token;
    this.refreshToken = pair.refresh_token;
    this.emit({
      generation: this.state.generation + 1,
      user,
      status: user ? 'authenticated' : 'bootstrapping',
    });
  }
  async hydrate() {
    const epoch = this.state.epoch;
    try {
      const refresh = await this.serial(() => this.store.get());
      this.current(epoch);
      if (!refresh) {
        this.emit({ status: 'anonymous' });
        return;
      }
      this.refreshToken = refresh;
      await this.recover(this.stamp());
      this.current(epoch);
      const user = await this.auth.me(this.access!);
      this.current(epoch);
      this.emit({ user, status: 'authenticated' });
    } catch {
      if (epoch === this.state.epoch) await this.clear(epoch).catch(() => {});
    }
  }
  async signIn(identifier: string, password: string) {
    const epoch = this.state.epoch + 1;
    this.access = undefined;
    this.refreshToken = undefined;
    this.emit({ epoch, user: null, status: 'anonymous', notice: undefined });
    await this.serial(() => this.store.remove());
    const result = await this.auth.login(identifier, password);
    this.current(epoch);
    await this.accept(result.tokens, epoch, result.user);
  }
  async recover(stamp: Stamp) {
    this.current(stamp.epoch);
    if (stamp.generation !== this.state.generation && this.access) return;
    if (this.flight?.epoch === stamp.epoch) return this.flight.promise;
    const refresh = this.refreshToken;
    if (!refresh) {
      await this.clear(stamp.epoch);
      throw new ApiError('http', '登录已过期，请重新登录', 401, 'SESSION_INVALID');
    }
    const user = this.state.user;
    this.emit({ status: 'refreshing' });
    const promise = (async () => {
      try {
        const pair = await this.auth.refresh(refresh);
        await this.accept(pair, stamp.epoch, user);
      } catch (error) {
        if (stamp.epoch === this.state.epoch) await this.clear(stamp.epoch);
        throw error;
      } finally {
        if (this.flight?.epoch === stamp.epoch) this.flight = undefined;
      }
    })();
    this.flight = { epoch: stamp.epoch, promise };
    return promise;
  }
  async logout(alreadyRevoked = false) {
    const access = this.access;
    const epoch = this.state.epoch + 1;
    this.emit({ epoch, user: null, status: 'anonymous', notice: undefined });
    this.access = undefined;
    this.refreshToken = undefined;
    let storageFailed = false;
    let serverFailed = false;
    try {
      await this.serial(() => this.store.remove());
    } catch {
      storageFailed = true;
    }
    try {
      if (access && !alreadyRevoked) await this.auth.logout(access);
    } catch {
      serverFailed = true;
    }
    if (this.state.epoch !== epoch) throw new ApiError('cancelled', '账户已切换');
    if (storageFailed || serverFailed) {
      const notice = storageFailed
        ? serverFailed
          ? '退出未完全确认：设备凭据清理和服务端撤销均失败，请检查网络与安全存储。'
          : '设备凭据清理失败，服务端会话已撤销；请检查安全存储。'
        : '本机已退出，服务端撤销尚未确认。';
      this.emit({ notice });
      throw new ApiError('http', notice);
    }
  }
  async invalidate(message: string) {
    const epoch = this.state.epoch;
    await this.clear(epoch).catch(() => {});
    if (this.state.epoch === epoch + 1) this.emit({ notice: message });
  }
  replaceUser(user: Model<'User'>) {
    if (this.state.user?.id === user.id) this.emit({ user });
  }
}
