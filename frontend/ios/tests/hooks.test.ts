import { act, create } from 'react-test-renderer';
import React from 'react';
import { expect, it, vi } from 'vitest';
vi.mock('../src/app-context', () => ({ useApp: () => ({ state: { epoch: 0 } }) }));
import { usePage } from '../src/hooks';
Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
it('retries a failed refresh even when the previous page was the last', async () => {
  let fail = false;
  let calls = 0;
  let page: ReturnType<typeof usePage<{ id: string }>> | undefined;
  function Probe() {
    page = usePage('test', async () => {
      calls++;
      if (fail) throw new Error('offline');
      return {
        data: [{ id: 'test-id' }],
        meta: { page: 1, page_size: 20, total: 1, has_more: false },
      };
    });
    return null;
  }
  let view: ReturnType<typeof create>;
  await act(async () => {
    view = create(React.createElement(Probe));
  });
  expect(page?.items).toHaveLength(1);
  expect(page?.hasMore).toBe(false);
  fail = true;
  await act(async () => {
    page?.reload();
  });
  expect(page?.error).toBeDefined();
  fail = false;
  const before = calls;
  await act(async () => {
    page?.loadMore();
  });
  expect(calls).toBe(before + 1);
  expect(page?.error).toBeNull();
  await act(async () => {
    view.unmount();
  });
});
