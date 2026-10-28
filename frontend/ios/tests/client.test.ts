import { describe, expect, it } from 'vitest';
import { Transport } from '../src/api/client';
const rid = 'ed6724c2-5514-43a7-b9ab-ae352f52c60c';
describe('HTTP contract', () => {
  it('accepts an empty 204 without parsing JSON', async () => {
    const transport = new Transport(
      'http://127.0.0.1/api/v1',
      async () => new Response(null, { status: 204 }),
    );
    await expect(transport.request('DELETE', '/favorites/x', null)).resolves.toBeUndefined();
  });
  it('rejects malformed success instead of showing an empty result', async () => {
    const transport = new Transport('http://127.0.0.1/api/v1', async () =>
      Response.json({ data: [], meta: null, request_id: rid }),
    );
    await expect(transport.request('GET', '/places', 'PlacePageResponse')).rejects.toMatchObject({
      kind: 'contract',
    });
  });
  it('keeps field errors and rate-limit metadata without provider contents', async () => {
    const transport = new Transport('http://127.0.0.1/api/v1', async () =>
      Response.json(
        { error: { code: 'RATE_LIMITED', message: 'too many', details: [] }, request_id: rid },
        { status: 429, headers: { 'Retry-After': '3' } },
      ),
    );
    await expect(transport.request('GET', '/places', 'PlacePageResponse')).rejects.toMatchObject({
      kind: 'http',
      status: 429,
      code: 'RATE_LIMITED',
      retryAfter: 3,
      requestId: rid,
    });
  });
});
it('calls the default browser fetch with its global receiver', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = function (this: unknown) {
    if (this !== globalThis) throw new TypeError('Illegal invocation');
    return Promise.resolve(new Response(null, { status: 204 }));
  };
  try {
    await expect(
      new Transport('http://127.0.0.1/api/v1').request('DELETE', '/favorites/x', null),
    ).resolves.toBeUndefined();
  } finally {
    globalThis.fetch = original;
  }
});
