import { useEffect, useRef, useState } from 'react';
import { useApp } from './app-context';
export function useResource<T>(
  key: string,
  load: (signal: AbortSignal) => Promise<T>,
  enabled = true,
) {
  const { state } = useApp();
  const loadRef = useRef(load);
  loadRef.current = load;
  const scope = state.epoch + ':' + key;
  const [tick, setTick] = useState(0);
  const [result, setResult] = useState<{
    data: T | null;
    error: unknown;
    loading: boolean;
    refreshing: boolean;
    scope: string;
  }>({ data: null, error: null, loading: enabled, refreshing: false, scope });
  const oldScope = useRef(scope);
  useEffect(() => {
    const controller = new AbortController();
    if (!enabled) {
      setResult({ data: null, error: null, loading: false, refreshing: false, scope });
      return;
    }
    const changed = oldScope.current !== scope;
    oldScope.current = scope;
    setResult((old) => ({
      data: old.scope !== scope ? null : old.data,
      error: null,
      loading: changed || !old.data,
      refreshing: !changed && !!old.data,
      scope,
    }));
    void loadRef.current(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted)
          setResult({ data, error: null, loading: false, refreshing: false, scope });
      },
      (error) => {
        if (!controller.signal.aborted)
          setResult((old) => ({ ...old, error, loading: false, refreshing: false }));
      },
    );
    return () => controller.abort();
  }, [scope, tick, enabled]);
  const visible =
    result.scope === scope
      ? result
      : { data: null, error: null, loading: enabled, refreshing: false };
  return { ...visible, reload: () => setTick((v) => v + 1) };
}
type Page<T> = {
  data: T[];
  meta: { page: number; page_size: number; total: number; has_more: boolean };
};
export function usePage<T extends { id: string }>(
  key: string,
  load: (page: number, signal: AbortSignal) => Promise<Page<T>>,
  enabled = true,
) {
  const { state } = useApp();
  const loadRef = useRef(load);
  loadRef.current = load;
  const [page, setPage] = useState(1);
  const [tick, setTick] = useState(0);
  const scope = state.epoch + ':' + key;
  const scopeRef = useRef(scope);
  const [result, setResult] = useState<{
    items: T[];
    error: unknown;
    loading: boolean;
    refreshing: boolean;
    loadingMore: boolean;
    hasMore: boolean;
    scope: string;
  }>({
    items: [],
    error: null,
    loading: enabled,
    refreshing: false,
    loadingMore: false,
    hasMore: false,
    scope,
  });
  const busy = useRef(false);
  useEffect(() => {
    setPage(1);
    setTick((v) => v + 1);
  }, [scope]);
  useEffect(() => {
    const controller = new AbortController();
    if (!enabled) {
      setResult({
        items: [],
        error: null,
        loading: false,
        refreshing: false,
        loadingMore: false,
        hasMore: false,
        scope,
      });
      return;
    }
    const changed = scopeRef.current !== scope;
    scopeRef.current = scope;
    if (changed && page !== 1) return;
    busy.current = true;
    setResult((old) => ({
      ...old,
      items: old.scope !== scope ? [] : old.items,
      scope,
      error: null,
      loading: page === 1 && (changed || old.items.length === 0),
      refreshing: page === 1 && !changed && old.items.length > 0,
      loadingMore: page > 1,
    }));
    void loadRef
      .current(page, controller.signal)
      .then(
        (response) => {
          if (controller.signal.aborted) return;
          setResult((old) => {
            const all = page === 1 ? response.data : [...old.items, ...response.data];
            return {
              items: [...new Map(all.map((item) => [item.id, item])).values()],
              error: null,
              loading: false,
              refreshing: false,
              loadingMore: false,
              hasMore: response.meta.has_more,
              scope,
            };
          });
        },
        (error) => {
          if (!controller.signal.aborted)
            setResult((old) => ({
              ...old,
              error,
              loading: false,
              refreshing: false,
              loadingMore: false,
            }));
        },
      )
      .finally(() => {
        if (!controller.signal.aborted) busy.current = false;
      });
    return () => {
      controller.abort();
      busy.current = false;
    };
  }, [scope, page, tick, enabled]);
  const visible =
    result.scope === scope
      ? result
      : {
          items: [] as T[],
          error: null,
          loading: enabled,
          refreshing: false,
          loadingMore: false,
          hasMore: false,
        };
  return {
    ...visible,
    reload: () => {
      setPage(1);
      setTick((v) => v + 1);
    },
    loadMore: () => {
      if (!busy.current && (result.hasMore || !!result.error)) {
        if (result.error) setTick((v) => v + 1);
        else setPage((v) => v + 1);
      }
    },
  };
}
