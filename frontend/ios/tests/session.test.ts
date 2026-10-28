import { expect, it } from 'vitest';
import { Session } from '../src/auth/session';
import type { Model } from '../src/api/types';
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}
const user: Model<'User'> = {
  id: 'ed6724c2-5514-43a7-b9ab-ae352f52c60c',
  username: 'test_user',
  email: 'test@example.invalid',
  email_verified: false,
  nickname: 'TEST',
  signature: '',
  preferences: { tags: [], pace: 'normal' },
};
function tokens(refresh = 'r'): Model<'TokenPair'> {
  return {
    access_token: 'a' + refresh,
    refresh_token: refresh,
    token_type: 'Bearer',
    expires_in: 900,
    refresh_expires_at: '2027-01-01T00:00:00Z',
  };
}
function setup() {
  let stored: string | null = null;
  let refreshCalls = 0;
  const gate = deferred<Model<'TokenPair'>>();
  const session = new Session(
    {
      get: async () => stored,
      set: async (value: string) => {
        stored = value;
      },
      remove: async () => {
        stored = null;
      },
    },
    {
      login: async () => ({ user, tokens: tokens() }),
      refresh: async () => {
        refreshCalls++;
        return gate.promise;
      },
      me: async () => user,
      logout: async () => {},
    },
  );
  return { session, gate, stored: () => stored, calls: () => refreshCalls };
}
it('shares refresh and ignores late 401 after token rotation', async () => {
  const s = setup();
  await s.session.signIn('test', 'password');
  const stamp = s.session.stamp();
  const one = s.session.recover(stamp);
  const two = s.session.recover(stamp);
  s.gate.resolve(tokens('r2'));
  await Promise.all([one, two]);
  await s.session.recover(stamp);
  expect(s.calls()).toBe(1);
  expect(s.stored()).toBe('r2');
});
it('logout defeats an in-flight refresh and cannot restore credentials', async () => {
  const s = setup();
  await s.session.signIn('test', 'password');
  const recovery = s.session.recover(s.session.stamp()).catch(() => undefined);
  await s.session.logout();
  s.gate.resolve(tokens('r2'));
  await recovery;
  expect(s.session.snapshot().user).toBeNull();
  expect(s.stored()).toBeNull();
});
it('an old account response cannot be retried with the next account', async () => {
  const s = setup();
  await s.session.signIn('test', 'password');
  const stamp = s.session.stamp();
  await s.session.logout();
  await s.session.signIn('other', 'password');
  await expect(s.session.recover(stamp)).rejects.toMatchObject({ kind: 'cancelled' });
  expect(s.calls()).toBe(0);
});
it('still attempts server revocation when local credential removal fails', async () => {
  let failing = false;
  let revoked = 0;
  const session = new Session(
    {
      get: async () => null,
      set: async () => {},
      remove: async () => {
        if (failing) throw new Error('storage unavailable');
      },
    },
    {
      login: async () => ({ user, tokens: tokens() }),
      refresh: async () => tokens(),
      me: async () => user,
      logout: async () => {
        revoked++;
      },
    },
  );
  await session.signIn('test', 'password');
  failing = true;
  await expect(session.logout()).rejects.toBeDefined();
  expect(revoked).toBe(1);
  expect(session.snapshot().user).toBeNull();
});
it('a delayed logout failure cannot show an old-account notice in the next session', async () => {
  const gate = deferred<void>();
  const nextUser = {
    ...user,
    id: 'aac96546-c015-4680-9a2c-fba5c3ad393d',
    username: 'next_test_user',
  };
  const session = new Session(
    { get: async () => null, set: async () => {}, remove: async () => {} },
    {
      login: async (identifier) => ({
        user: identifier === 'a' ? user : nextUser,
        tokens: tokens(identifier),
      }),
      refresh: async () => tokens(),
      me: async () => user,
      logout: async () => {
        await gate.promise;
        throw new Error('offline');
      },
    },
  );
  await session.signIn('a', 'password');
  const oldLogout = session.logout().catch((e) => e);
  await session.signIn('b', 'password');
  gate.resolve();
  expect(await oldLogout).toMatchObject({ kind: 'cancelled' });
  expect(session.snapshot().user?.id).toBe(nextUser.id);
  expect(session.snapshot().notice).toBeUndefined();
});
