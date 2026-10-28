import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
} from 'react';
import type { PropsWithChildren } from 'react';
import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import { ApiClient, Transport } from './api/client';
import { Session } from './auth/session';
import type { Model } from './api/types';
const apiUrl: string = process.env.EXPO_PUBLIC_API_URL ?? 'http://127.0.0.1:8000/api/v1';
export const appEnvironment = process.env.EXPO_PUBLIC_APP_ENV ?? 'development';
if (!['development', 'test', 'production'].includes(appEnvironment))
  throw new Error('环境必须是 development/test/production');
if (appEnvironment === 'production' && !apiUrl.startsWith('https://'))
  throw new Error('生产环境必须使用 HTTPS');
let browserCredential: string | null = null;
const key =
  'yirenyoulu.refresh.' +
  appEnvironment +
  '.' +
  Array.from(apiUrl, (c) => c.charCodeAt(0).toString(16)).join('');
const store =
  Platform.OS === 'web'
    ? {
        get: async () => browserCredential,
        set: async (v: string) => {
          browserCredential = v;
        },
        remove: async () => {
          browserCredential = null;
        },
      }
    : {
        get: () => SecureStore.getItemAsync(key),
        set: (value: string) =>
          SecureStore.setItemAsync(key, value, {
            keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
          }),
        remove: () => SecureStore.deleteItemAsync(key),
      };
const transport = new Transport(apiUrl);
const session = new Session(store, {
  login: async (identifier, password) =>
    (
      await transport.request('POST', '/auth/login', 'LoginResultResponse', {
        identifier,
        password,
      })
    ).data,
  refresh: async (refresh_token) =>
    (await transport.request('POST', '/auth/refresh', 'TokenPairResponse', { refresh_token })).data,
  me: async (token) =>
    (await transport.request('GET', '/me', 'UserResponse', undefined, {}, token)).data,
  logout: async (token) => transport.request('POST', '/auth/logout', null, undefined, {}, token),
});
const api = new ApiClient(transport, session);
function useAppState() {
  const state = useSyncExternalStore(session.subscribe, session.snapshot);
  const [city, setCity] = useState<Model<'City'> | null>(null);
  const [revision, update] = useState(0);
  useEffect(() => {
    void session.hydrate();
  }, []);
  return useMemo(
    () => ({
      api,
      session,
      state,
      city,
      setCity,
      revision,
      invalidate: () => update((v) => v + 1),
    }),
    [state, city, revision],
  );
}
const AppContext = createContext<ReturnType<typeof useAppState> | null>(null);
export function AppProvider({ children }: PropsWithChildren) {
  const value = useAppState();
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}
export function useApp() {
  const value = useContext(AppContext);
  if (!value) throw new Error('AppProvider missing');
  return value;
}
