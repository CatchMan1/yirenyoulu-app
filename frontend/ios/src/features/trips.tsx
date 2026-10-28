import { Dialog as Alert } from '../platform/dialog';
import React, { useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useIsFocused, useNavigation, usePreventRemove } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { ApiError } from '../api/client';
import type { Kind, Model } from '../api/types';
import { useApp } from '../app-context';
import { usePage, useResource } from '../hooks';
import type { RootRoutes, ScreenProps } from '../navigation';
import {
  Button,
  Card,
  Chip,
  Empty,
  errorMessage,
  Field,
  Heading,
  Notice,
  PlaceRow,
  Screen,
  useTheme,
} from '../ui';
import { money, moneyText, newId, timeText, today } from '../utils';
import { datesOutsideTrip, nextTripIntent, parseTime, visitDays } from './trip-rules';

type Trip = Model<'Trip'>;
type Item = Model<'TripItem'>;
type StackNavigation = NativeStackNavigationProp<RootRoutes>;
const kinds: { kind: Kind; label: string }[] = [
  { kind: 'attraction', label: '景点' },
  { kind: 'restaurant', label: '餐厅' },
  { kind: 'hotel', label: '酒店' },
];
const paces: { value: Model<'Preferences'>['pace']; label: string }[] = [
  { value: 'relaxed', label: '轻松' },
  { value: 'normal', label: '适中' },
  { value: 'fast', label: '紧凑' },
];

function Copy({ children, muted = false }: { children: React.ReactNode; muted?: boolean }) {
  const theme = useTheme();
  return <Text style={[styles.copy, { color: muted ? theme.muted : theme.text }]}>{children}</Text>;
}
function Gate() {
  const navigation = useNavigation<StackNavigation>();
  return (
    <Screen>
      <Empty
        title="登录后安排自己的旅程"
        description="行程和草稿属于当前账户。登录后可回到这里继续。"
        action={<Button label="去登录" onPress={() => navigation.navigate('Login')} />}
      />
    </Screen>
  );
}
function Failure({ error, retry }: { error: unknown; retry: () => void }) {
  return (
    <>
      <Notice tone="error">{errorMessage(error)}</Notice>
      <Button label="重试读取" secondary onPress={retry} />
    </>
  );
}
function useAlive() {
  const { session, state } = useApp();
  const epoch = state.epoch;
  const userId = state.user?.id;
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  return () =>
    alive.current && session.stamp().epoch === epoch && session.snapshot().user?.id === userId;
}
function useDiscard(dirty: boolean, busy: boolean, navigation: StackNavigation) {
  const alive = useAlive();
  usePreventRemove(dirty && !busy, ({ data }) => {
    Alert.alert('放弃未保存的修改？', '本次输入尚未提交。', [
      { text: '继续编辑', style: 'cancel' },
      {
        text: '放弃修改',
        style: 'destructive',
        onPress: () => {
          if (alive()) navigation.dispatch(data.action);
        },
      },
    ]);
  });
}
function useWait() {
  const [until, setUntil] = useState(0);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (until <= Date.now()) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [until]);
  return {
    remaining: Math.max(0, Math.ceil((until - now) / 1000)),
    wait: (error: unknown) => {
      if (error instanceof ApiError && error.status === 429) {
        setNow(Date.now());
        setUntil(Date.now() + (error.retryAfter ?? 30) * 1000);
      }
    },
  };
}

/** 无幂等保证的写入失败后先读取，保留草稿，明确确认才采用最新版本。 */
function useTripWrite(initial: Trip | null, done: (trip: Trip | null) => void) {
  const { api, invalidate } = useApp();
  const alive = useAlive();
  const locked = useRef(false);
  const [base, setBase] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [blocked, setBlocked] = useState(false);
  const [latest, setLatest] = useState<Trip | null>(null);
  const cooldown = useWait();
  const readLatest = async () => {
    if (!initial) return;
    try {
      const response = await api.get(`/trips/${initial.id}`, 'TripResponse', undefined, {
        auth: true,
      });
      if (alive()) setLatest(response.data);
    } catch (readError) {
      if (alive()) setError(readError);
    }
  };
  const run = async (operation: (version: number) => Promise<Model<'TripResponse'> | void>) => {
    if (!base || locked.current || blocked || cooldown.remaining > 0) return;
    locked.current = true;
    setBusy(true);
    setError(null);
    try {
      const response = await operation(base.version);
      if (!alive()) return;
      invalidate();
      done(response ? response.data : null);
    } catch (writeError) {
      if (!alive()) return;
      setError(writeError);
      cooldown.wait(writeError);
      if (
        !(writeError instanceof ApiError) ||
        writeError.status === 409 ||
        writeError.kind !== 'http' ||
        (writeError.status ?? 0) >= 500
      ) {
        setBlocked(true);
        setLatest(null);
        await readLatest();
      }
    } finally {
      locked.current = false;
      if (alive()) setBusy(false);
    }
  };
  return {
    base,
    busy,
    error,
    blocked,
    latest,
    remaining: cooldown.remaining,
    run,
    readLatest: async () => {
      if (locked.current) return;
      locked.current = true;
      setBusy(true);
      await readLatest();
      locked.current = false;
      if (alive()) setBusy(false);
    },
    acceptLatest: () => {
      if (latest) {
        setBase(latest);
        setLatest(null);
        setBlocked(false);
        setError(null);
      }
    },
  };
}
type TripWrite = ReturnType<typeof useTripWrite>;
function WriteStatus({ write }: { write: TripWrite }) {
  return (
    <>
      {write.error ? <Notice tone="error">{errorMessage(write.error)}</Notice> : null}
      {write.remaining > 0 ? <Notice>请在 {write.remaining} 秒后再操作。</Notice> : null}
      {write.blocked ? (
        <Card>
          <Copy>保存未确认或版本已变化。本次草稿已保留，不会自动覆盖。</Copy>
          {write.latest ? (
            <>
              <Copy>
                最新：{write.latest.title} · {write.latest.start_date} 至 {write.latest.end_date} ·
                版本 {write.latest.version}
              </Copy>
              <Copy>
                预算 {moneyText(write.latest.budget_minor)} · {write.latest.items.length} 个地点 ·{' '}
                {paces.find((pace) => pace.value === write.latest?.preferences.pace)?.label}节奏
              </Copy>
              {write.latest.items.map((item) => (
                <Copy key={item.id} muted>
                  {item.date} {item.snapshot.name} ·{' '}
                  {item.snapshot.kind === 'hotel'
                    ? '住宿'
                    : `${timeText(item.start_minute)}–${timeText(item.end_minute)}`}{' '}
                  · {item.note || '无备注'}
                </Copy>
              ))}
              <Button label="已比较，采用此版本并保留草稿" secondary onPress={write.acceptLatest} />
            </>
          ) : (
            <Button
              label="读取最新版本后比较"
              secondary
              busy={write.busy}
              onPress={() => {
                void write.readLatest();
              }}
            />
          )}
        </Card>
      ) : null}
    </>
  );
}
function Cost({ trip }: { trip: Trip }) {
  return (
    <Card>
      <Heading title="费用与资料" />
      <Copy>预算：{moneyText(trip.budget_minor)}</Copy>
      <Copy>已知事实费用：{moneyText(trip.cost_summary.known_cost_minor)}</Copy>
      <Copy>含可得估算的合计：{moneyText(trip.cost_summary.estimated_cost_minor)}</Copy>
      <Copy muted>
        {trip.cost_summary.unknown_item_count} 项缺少事实价格。
        {trip.cost_summary.complete ? '已安排项目的费用资料完整。' : '费用资料不完整。'}
        不含未安排项目，不是完整旅行报价。
      </Copy>
      {trip.warnings.map((warning, index) => (
        <Notice key={`${warning.code}:${index}`} tone="warning">
          {warning.message}
        </Notice>
      ))}
    </Card>
  );
}
function useCityNames(trips: readonly Model<'TripSummary'>[]) {
  const { api } = useApp();
  const ids = [...new Set(trips.map((trip) => trip.city_id))].sort();
  return useResource(
    `trip-cities:${ids.join(',')}`,
    async (signal) => {
      const wanted = new Set(ids);
      const names: Record<string, string> = {};
      for (let page = 1; page <= 10000 && wanted.size > 0; page += 1) {
        const response = await api.get(
          '/cities',
          'CityPageResponse',
          { page, page_size: 50 },
          { signal },
        );
        for (const city of response.data) {
          if (wanted.has(city.id)) {
            names[city.id] = city.name;
            wanted.delete(city.id);
          }
        }
        if (!response.meta.has_more) break;
      }
      return names;
    },
    ids.length > 0,
  );
}

export function TripsScreen() {
  const { state } = useApp();
  return state.user ? <TripsList key={state.epoch} /> : <Gate />;
}
function TripsList() {
  const { api, state, revision } = useApp();
  const navigation = useNavigation<StackNavigation>();
  const focused = useIsFocused();
  const [q, setQ] = useState('');
  const page = usePage(`trips:${state.epoch}:${revision}:${focused}:${q}`, (number, signal) =>
    api.get(
      '/trips',
      'TripSummaryPageResponse',
      { q: q.trim() || undefined, page: number, page_size: 20 },
      { auth: true, signal },
    ),
  );
  const cities = useCityNames(page.items);
  return (
    <Screen refreshing={page.refreshing} onRefresh={page.reload}>
      <Heading
        title="我的行程"
        subtitle="从一段空白开始，安排自己的节奏。"
        action={<Button label="新建" onPress={() => navigation.navigate('TripForm')} />}
      />
      <Field label="按标题搜索" value={q} onChangeText={setQ} placeholder="输入行程标题" />
      {page.loading ? <Copy>正在读取行程…</Copy> : null}
      {page.items.map((trip) => (
        <Card key={trip.id}>
          <Heading
            title={trip.title}
            subtitle={`${cities.data ? (cities.data[trip.city_id] ?? '城市资料不可用') : '正在读取城市资料'} · ${trip.start_date} 至 ${trip.end_date}`}
          />
          <Button
            label="查看每日安排"
            secondary
            onPress={() => navigation.navigate('Trip', { id: trip.id })}
          />
        </Card>
      ))}
      {cities.error ? <Failure error={cities.error} retry={cities.reload} /> : null}
      {!page.loading && !page.error && page.items.length === 0 ? (
        <Empty
          title={q.trim() ? '没有匹配的行程' : '还没有行程'}
          description="创建空行程后，再逐日添加地点。"
          action={
            <Button
              label={q.trim() ? '清空搜索' : '创建行程'}
              onPress={() => (q.trim() ? setQ('') : navigation.navigate('TripForm'))}
            />
          }
        />
      ) : null}
      {page.error ? (
        <Failure error={page.error} retry={page.items.length > 0 ? page.loadMore : page.reload} />
      ) : null}
      {page.hasMore ? (
        <Button label="加载更多行程" secondary busy={page.loadingMore} onPress={page.loadMore} />
      ) : null}
    </Screen>
  );
}

export function TripScreen(props: ScreenProps<'Trip'>) {
  const { state } = useApp();
  return state.user ? (
    <TripDetail key={`${state.epoch}:${props.route.params.id}`} {...props} />
  ) : (
    <Gate />
  );
}
function TripDetail({ route, navigation }: ScreenProps<'Trip'>) {
  const { api, state, revision } = useApp();
  const focused = useIsFocused();
  const resource = useResource(
    `trip:${route.params.id}:${state.epoch}:${revision}:${focused}`,
    (signal) =>
      api.get(`/trips/${route.params.id}`, 'TripResponse', undefined, { auth: true, signal }),
  );
  return (
    <Screen refreshing={resource.refreshing} onRefresh={resource.reload}>
      <Button label="刷新行程资料" secondary onPress={resource.reload} busy={resource.refreshing} />
      {resource.loading ? <Copy>正在读取每日安排…</Copy> : null}
      {resource.error ? <Failure error={resource.error} retry={resource.reload} /> : null}
      {resource.data &&
      !(
        resource.error instanceof ApiError && [401, 403, 404].includes(resource.error.status ?? 0)
      ) ? (
        <TripDetailBody
          key={`${resource.data.data.id}:${resource.data.data.version}`}
          trip={resource.data.data}
          navigation={navigation}
        />
      ) : !resource.loading && !resource.error ? (
        <Empty
          title="行程不可访问"
          action={<Button label="返回" onPress={() => navigation.goBack()} />}
        />
      ) : null}
    </Screen>
  );
}
function TripDetailBody({
  trip,
  navigation,
}: {
  trip: Trip;
  navigation: ScreenProps<'Trip'>['navigation'];
}) {
  const { api } = useApp();
  const alive = useAlive();
  const [date, setDate] = useState(trip.start_date);
  const cities = useCityNames([trip]);
  const write = useTripWrite(trip, () => {
    Alert.alert('行程已删除');
    navigation.popTo('Main', { screen: 'Trips' });
  });
  // Read display facts from the latest server response, even when version is unchanged.
  const base = trip;
  const day = base.items.filter((item) => item.date === date);
  const daytime = day
    .filter((item) => item.snapshot.kind !== 'hotel')
    .sort((a, b) => (a.start_minute ?? 0) - (b.start_minute ?? 0));
  const hotels = day.filter((item) => item.snapshot.kind === 'hotel');
  const remove = () =>
    Alert.alert('删除这段行程？', '行程及其中地点安排将被删除，无法撤销。', [
      { text: '保留', style: 'cancel' },
      {
        text: '删除行程',
        style: 'destructive',
        onPress: () => {
          if (alive())
            void write.run((version) =>
              api.send('DELETE', `/trips/${trip.id}?version=${version}`, null, undefined, {
                auth: true,
              }),
            );
        },
      },
    ]);
  const itemCard = (item: Item) => (
    <Card key={item.id}>
      <Heading
        title={item.snapshot.name}
        subtitle={
          item.snapshot.kind === 'hotel'
            ? '当晚入住 · 次日退房'
            : `${timeText(item.start_minute)} — ${timeText(item.end_minute)}`
        }
      />
      {item.current_status === 'inactive' ? (
        <Notice tone="warning">当前地点已停用，仍可修改备注或删除这项安排。</Notice>
      ) : null}
      {item.note ? <Copy>{item.note}</Copy> : null}
      <Copy muted>
        费用估算：{moneyText(item.estimated_cost_minor)}
        {item.estimate_reason ? ` · ${item.estimate_reason}` : ''}
      </Copy>
      <Button
        label="编辑地点安排"
        secondary
        onPress={() => navigation.navigate('ItemForm', { tripId: trip.id, itemId: item.id })}
      />
    </Card>
  );
  return (
    <>
      <Heading
        title={base.title}
        subtitle={`${cities.data ? (cities.data[base.city_id] ?? '城市资料不可用') : '正在读取城市资料'} · ${base.start_date} 至 ${base.end_date}`}
      />
      <Button
        label="编辑行程信息"
        secondary
        disabled={write.busy}
        onPress={() => navigation.navigate('TripForm', { id: trip.id })}
      />
      <View style={styles.wrap}>
        {visitDays(base.start_date, base.end_date).map((value) => (
          <Chip
            key={value}
            label={value.slice(5)}
            selected={date === value}
            onPress={() => setDate(value)}
          />
        ))}
      </View>
      <Heading title={`${date} · 白天安排`} />
      {daytime.length ? (
        daytime.map(itemCard)
      ) : (
        <Empty title="这一天留白" description="可以添加景点或餐厅，按自己的时间出发。" />
      )}
      <Heading title="当晚住宿" />
      {hotels.length ? (
        hotels.map(itemCard)
      ) : (
        <Copy muted>
          {date === base.end_date ? '行程最后一天不再安排入住夜。' : '尚未安排住宿。'}
        </Copy>
      )}
      <Button
        label="添加地点"
        onPress={() => navigation.navigate('ItemForm', { tripId: trip.id })}
      />
      <Cost trip={base} />
      <WriteStatus write={write} />
      <Button
        label="删除行程"
        danger
        busy={write.busy}
        disabled={write.blocked || write.remaining > 0}
        onPress={remove}
      />
    </>
  );
}

function Preferences({
  pace,
  tags,
  onPace,
  onTags,
}: {
  pace: Model<'Preferences'>['pace'];
  tags: string[];
  onPace: (pace: Model<'Preferences'>['pace']) => void;
  onTags: (tags: string[]) => void;
}) {
  const { api } = useApp();
  const [q, setQ] = useState('');
  const page = usePage(`trip-tags:${q}`, (number, signal) =>
    api.get(
      '/tags',
      'NamedEntryPageResponse',
      { q: q.trim() || undefined, page: number, page_size: 20 },
      { signal },
    ),
  );
  return (
    <Card>
      <Heading title="旅行偏好" />
      <View style={styles.wrap}>
        {paces.map((item) => (
          <Chip
            key={item.value}
            label={item.label}
            selected={pace === item.value}
            onPress={() => onPace(item.value)}
          />
        ))}
      </View>
      <Field label="搜索偏好标签" value={q} onChangeText={setQ} placeholder="可选，最多20项" />
      <Copy muted>已选 {tags.length} 项；偏好用于参考，不代表硬性筛选。</Copy>
      {tags
        .filter((id) => !page.items.some((item) => item.id === id))
        .map((id) => (
          <Chip
            key={id}
            label={`已选标签 ${id.slice(0, 8)} · 移除`}
            selected
            onPress={() => onTags(tags.filter((value) => value !== id))}
          />
        ))}
      <View style={styles.wrap}>
        {page.items.map((tag) => (
          <Chip
            key={tag.id}
            label={tag.name}
            selected={tags.includes(tag.id)}
            onPress={() => {
              if (tags.includes(tag.id)) onTags(tags.filter((id) => id !== tag.id));
              else if (tags.length < 20) onTags([...tags, tag.id]);
            }}
          />
        ))}
      </View>
      {page.loading ? <Copy>正在读取标签…</Copy> : null}
      {page.error ? <Failure error={page.error} retry={page.reload} /> : null}
      {page.hasMore ? (
        <Button label="更多标签" secondary busy={page.loadingMore} onPress={page.loadMore} />
      ) : null}
    </Card>
  );
}

export function TripFormScreen(props: ScreenProps<'TripForm'>) {
  const { state } = useApp();
  return state.user ? (
    <TripFormLoader
      key={`${state.epoch}:${props.route.params?.id ?? 'new'}:${props.route.params?.placeId ?? ''}`}
      {...props}
    />
  ) : (
    <Gate />
  );
}
function TripFormLoader(props: ScreenProps<'TripForm'>) {
  const { api, state } = useApp();
  const id = props.route.params?.id;
  const placeId = props.route.params?.placeId;
  const trip = useResource(
    `trip-form:${state.epoch}:${id}`,
    (signal) => api.get(`/trips/${id}`, 'TripResponse', undefined, { auth: true, signal }),
    !!id,
  );
  const place = useResource(
    `trip-form-place:${state.epoch}:${placeId}`,
    (signal) => api.get(`/places/${placeId}`, 'PlaceDetailResponse', undefined, { signal }),
    !!placeId,
  );
  if (trip.loading || place.loading)
    return (
      <Screen>
        <Copy>正在读取行程信息…</Copy>
      </Screen>
    );
  if (trip.error || place.error)
    return (
      <Screen>
        <Failure
          error={trip.error ?? place.error}
          retry={() => {
            if (trip.error) trip.reload();
            if (place.error) place.reload();
          }}
        />
      </Screen>
    );
  if ((id && !trip.data) || (placeId && !place.data))
    return (
      <Screen>
        <Copy>正在准备表单…</Copy>
      </Screen>
    );
  return (
    <TripFormBody {...props} initial={trip.data?.data ?? null} place={place.data?.data ?? null} />
  );
}
function TripFormBody({
  route,
  navigation,
  initial,
  place,
}: ScreenProps<'TripForm'> & { initial: Trip | null; place: Model<'PlaceDetail'> | null }) {
  const { api, city, state, invalidate } = useApp();
  const alive = useAlive();
  const [title, setTitle] = useState(initial?.title ?? '');
  const [start, setStart] = useState(initial?.start_date ?? today());
  const [end, setEnd] = useState(initial?.end_date ?? today());
  const [budget, setBudget] = useState(
    initial?.budget_minor == null ? '' : (initial.budget_minor / 100).toFixed(2),
  );
  const [pace, setPace] = useState<Model<'Preferences'>['pace']>(
    initial?.preferences.pace ?? 'normal',
  );
  const [tags, setTags] = useState<string[]>(initial?.preferences.tags ?? []);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const intent = useRef<{ fingerprint: string; key: string } | null>(null);
  const locked = useRef(false);
  const cooldown = useWait();
  const creationCity = place?.city ?? city;
  const write = useTripWrite(initial, (result) => {
    if (result) {
      Alert.alert('行程已保存');
      navigation.popTo('Trip', { id: result.id });
    }
  });
  const edit =
    <T,>(set: (value: T) => void) =>
    (value: T) => {
      if (!busy && !write.busy) {
        set(value);
        setDirty(true);
        intent.current = null;
      }
    };
  const base = write.base;
  useEffect(() => {
    intent.current = null;
  }, [creationCity?.id]);
  useDiscard(dirty, busy || write.busy, navigation);
  const save = async () => {
    if (locked.current || busy || write.busy || write.blocked || cooldown.remaining > 0) return;
    setError(null);
    try {
      if (!title.trim() || title.trim().length > 200) throw new Error('请输入1—200字的行程标题');
      visitDays(start, end);
      const amount = money(budget);
      if (initial && base) {
        const outside = datesOutsideTrip(base.items, start, end);
        if (outside.length)
          throw new Error(
            `缩短日期会使以下安排越界，请先调整或移除：${outside.map((item) => `${item.date} ${item.snapshot.name}`).join('、')}`,
          );
        const body: Model<'TripUpdate'> = { version: base.version };
        if (title.trim() !== base.title) body.title = title.trim();
        if (start !== base.start_date) body.start_date = start;
        if (end !== base.end_date) body.end_date = end;
        if (
          pace !== base.preferences.pace ||
          [...tags].sort().join(',') !== [...base.preferences.tags].sort().join(',')
        )
          body.preferences = { tags, pace };
        // 未修改预算时不重新触发历史预算检查。
        if (amount !== base.budget_minor) body.budget_minor = amount;
        if (Object.keys(body).length === 1) throw new Error('尚无需要保存的修改');
        await write.run((version) =>
          api.send(
            'PATCH',
            `/trips/${initial.id}`,
            'TripResponse',
            { ...body, version },
            { auth: true },
          ),
        );
      } else {
        if (!creationCity) throw new Error('请先选择目的地城市');
        if (place && place.status !== 'active') throw new Error('该地点已停用，请返回选择其他地点');
        const body: Model<'TripCreate'> = {
          title: title.trim(),
          city_id: creationCity.id,
          start_date: start,
          end_date: end,
          budget_minor: amount,
          preferences: { tags: [...tags].sort(), pace },
        };
        const fingerprint = `${state.epoch}:${JSON.stringify(body)}`;
        intent.current = nextTripIntent(intent.current, fingerprint, newId);
        locked.current = true;
        setBusy(true);
        try {
          const response = await api.send('POST', '/trips', 'TripResponse', body, {
            auth: true,
            idempotencyKey: intent.current.key,
          });
          if (!alive()) return;
          invalidate();
          Alert.alert('空行程已创建');
          if (route.params?.placeId)
            navigation.replace('ItemForm', {
              tripId: response.data.id,
              placeId: route.params.placeId,
            });
          else navigation.popTo('Trip', { id: response.data.id });
        } catch (createError) {
          if (alive()) {
            setError(createError);
            cooldown.wait(createError);
          }
        } finally {
          locked.current = false;
          if (alive()) setBusy(false);
        }
      }
    } catch (validationError) {
      if (alive()) setError(validationError);
    }
  };
  return (
    <Screen>
      <Heading
        title={initial ? '编辑行程' : '创建手动行程'}
        subtitle="先保存空行程，再逐日安排地点。"
      />
      <Field
        label="行程标题"
        value={title}
        onChangeText={edit(setTitle)}
        placeholder="给旅程起个名字"
      />
      {initial ? (
        <Copy muted>城市在创建后不可更改。</Copy>
      ) : (
        <Card>
          <Copy>目的地：{creationCity?.name ?? '尚未选择'}</Copy>
          {!place ? (
            <Button label="选择城市" secondary onPress={() => navigation.navigate('CityPicker')} />
          ) : (
            <Copy muted>沿用该地点所属城市，创建后仍需确认添加。</Copy>
          )}
        </Card>
      )}
      <Field
        label="开始日期 YYYY-MM-DD"
        value={start}
        onChangeText={edit(setStart)}
        autoCapitalize="none"
      />
      <Field
        label="结束日期 YYYY-MM-DD"
        value={end}
        onChangeText={edit(setEnd)}
        autoCapitalize="none"
      />
      {initial ? (
        <Notice>
          修改日期前，请确认所有地点和住宿夜仍在新日期内；越界安排会阻止保存，不会被删除。
        </Notice>
      ) : null}
      <Field
        label="预算（人民币元，可留空）"
        value={budget}
        onChangeText={edit(setBudget)}
        keyboardType="decimal-pad"
        placeholder="留空为未知，0为明确零预算"
      />
      <Preferences pace={pace} tags={tags} onPace={edit(setPace)} onTags={edit(setTags)} />
      {error ? <Notice tone="error">{errorMessage(error)}</Notice> : null}
      {initial ? (
        <WriteStatus write={write} />
      ) : (
        <Notice>网络结果不确定时保留本次输入，重试同一创建意图会复用幂等键。</Notice>
      )}
      {cooldown.remaining > 0 ? <Notice>请在 {cooldown.remaining} 秒后重试。</Notice> : null}
      <Button
        label={initial ? '确认保存' : '创建空行程'}
        busy={busy || write.busy}
        disabled={write.blocked || cooldown.remaining > 0 || write.remaining > 0}
        onPress={() => {
          void save();
        }}
      />
    </Screen>
  );
}

export function ItemFormScreen(props: ScreenProps<'ItemForm'>) {
  const { state } = useApp();
  return state.user ? (
    <ItemFormLoader
      key={`${state.epoch}:${props.route.params.tripId}:${props.route.params.itemId ?? ''}:${props.route.params.placeId ?? ''}`}
      {...props}
    />
  ) : (
    <Gate />
  );
}
function ItemFormLoader(props: ScreenProps<'ItemForm'>) {
  const { api, state } = useApp();
  const { tripId, placeId } = props.route.params;
  const trip = useResource(`item-form:${state.epoch}:${tripId}`, (signal) =>
    api.get(`/trips/${tripId}`, 'TripResponse', undefined, { auth: true, signal }),
  );
  const place = useResource(
    `item-place:${state.epoch}:${placeId}`,
    (signal) => api.get(`/places/${placeId}`, 'PlaceDetailResponse', undefined, { signal }),
    !!placeId,
  );
  if (trip.error || place.error)
    return (
      <Screen>
        <Failure
          error={trip.error ?? place.error}
          retry={() => {
            if (trip.error) trip.reload();
            if (place.error) place.reload();
          }}
        />
      </Screen>
    );
  if (!trip.data || (placeId && !place.data))
    return (
      <Screen>
        <Copy>正在读取地点和行程…</Copy>
      </Screen>
    );
  if (
    props.route.params.itemId &&
    !trip.data.data.items.some((item) => item.id === props.route.params.itemId)
  )
    return (
      <Screen>
        <Empty
          title="该项安排已不可访问"
          action={<Button label="返回" onPress={() => props.navigation.goBack()} />}
        />
      </Screen>
    );
  return <ItemFormBody {...props} initial={trip.data.data} incoming={place.data?.data ?? null} />;
}
function ItemFormBody({
  route,
  navigation,
  initial,
  incoming,
}: ScreenProps<'ItemForm'> & { initial: Trip; incoming: Model<'PlaceDetail'> | null }) {
  const { api } = useApp();
  const alive = useAlive();
  const existing = initial.items.find((item) => item.id === route.params.itemId);
  const [selected, setSelected] = useState<Model<'Place'> | null>(incoming);
  const [selecting, setSelecting] = useState(!existing && !incoming);
  const [kind, setKind] = useState<Kind>(incoming?.kind ?? existing?.snapshot.kind ?? 'attraction');
  const [q, setQ] = useState('');
  const [date, setDate] = useState(existing?.date ?? initial.start_date);
  const [start, setStart] = useState(
    existing?.start_minute == null ? '09:00' : timeText(existing.start_minute),
  );
  const [end, setEnd] = useState(
    existing?.end_minute == null ? '10:00' : timeText(existing.end_minute),
  );
  const [note, setNote] = useState(existing?.note ?? '');
  const [dirty, setDirty] = useState(false);
  const [validation, setValidation] = useState<unknown>(null);
  const write = useTripWrite(initial, (result) => {
    if (result) {
      Alert.alert('地点安排已保存');
      navigation.popTo('Trip', { id: result.id });
    }
  });
  const base = write.base ?? initial;
  const currentExisting = base.items.find((item) => item.id === existing?.id);
  const page = usePage(
    `trip-places:${initial.city_id}:${kind}:${q}`,
    (number, signal) =>
      api.get(
        '/places',
        'PlacePageResponse',
        { city_id: initial.city_id, kind, q: q.trim() || undefined, page: number, page_size: 20 },
        { signal },
      ),
    selecting,
  );
  useDiscard(dirty, write.busy, navigation);
  const edit =
    <T,>(set: (value: T) => void) =>
    (value: T) => {
      if (!write.busy) {
        set(value);
        setDirty(true);
      }
    };
  const currentKind = selected?.kind ?? currentExisting?.snapshot.kind;
  const placeId = selected?.id ?? currentExisting?.place_id;
  const dates = visitDays(base.start_date, base.end_date);
  const selectableDates = currentKind === 'hotel' ? dates.slice(0, -1) : dates;
  const save = async () => {
    if (write.busy || write.blocked) return;
    setValidation(null);
    try {
      if (!placeId || !currentKind) throw new Error('请先选择一个同城有效地点');
      if (selected && (selected.city.id !== base.city_id || selected.status !== 'active'))
        throw new Error('只能选择行程同城的有效地点，请重新选择');
      if (!selectableDates.includes(date))
        throw new Error(
          currentKind === 'hotel'
            ? '请选择有效入住夜；最后一天不能入住，单日行程不安排住宿'
            : '请选择行程日期范围内的一天',
        );
      if (note.length > 1000) throw new Error('备注最多1000字');
      const startMinute = currentKind === 'hotel' ? null : parseTime(start);
      const endMinute = currentKind === 'hotel' ? null : parseTime(end, true);
      if (startMinute != null && endMinute != null && startMinute >= endMinute)
        throw new Error('结束时间必须晚于开始时间，不能跨午夜');
      const other = base.items.filter((item) => item.id !== existing?.id && item.date === date);
      if (other.some((item) => item.place_id === placeId))
        throw new Error('同一天不能重复添加同一地点');
      if (currentKind === 'hotel' && other.some((item) => item.snapshot.kind === 'hotel'))
        throw new Error('每个入住夜最多一项酒店，请先调整现有住宿');
      if (
        startMinute != null &&
        endMinute != null &&
        other.some(
          (item) =>
            item.snapshot.kind !== 'hotel' &&
            item.start_minute != null &&
            item.end_minute != null &&
            startMinute < item.end_minute &&
            endMinute > item.start_minute,
        )
      )
        throw new Error('该时段与现有安排重叠，请调整时间');
      if (existing) {
        if (!base.items.some((item) => item.id === existing.id))
          throw new Error('最新版本中该项已被删除，请返回行程重新查看');
        const body: Model<'TripItemUpdate'> = { version: base.version, note };
        if (date !== currentExisting?.date) body.date = date;
        if (
          startMinute !== currentExisting?.start_minute ||
          endMinute !== currentExisting?.end_minute ||
          (selected && selected.kind !== currentExisting?.snapshot.kind)
        ) {
          body.start_minute = startMinute;
          body.end_minute = endMinute;
        }
        // 只在替换地点时提交place_id，允许保留失效地点的历史快照。
        if (placeId !== currentExisting?.place_id) body.place_id = placeId;
        if (Object.keys(body).length === 2 && note === currentExisting?.note)
          throw new Error('尚无需要保存的修改');
        await write.run((version) =>
          api.send(
            'PATCH',
            `/trips/${initial.id}/items/${existing.id}`,
            'TripResponse',
            { ...body, version },
            { auth: true },
          ),
        );
      } else {
        const body: Model<'TripItemCreate'> = {
          version: base.version,
          place_id: placeId,
          date,
          start_minute: startMinute,
          end_minute: endMinute,
          note,
        };
        await write.run((version) =>
          api.send(
            'POST',
            `/trips/${initial.id}/items`,
            'TripResponse',
            { ...body, version },
            { auth: true },
          ),
        );
      }
    } catch (error) {
      if (alive()) setValidation(error);
    }
  };
  const remove = () => {
    if (!existing || write.busy || write.blocked) return;
    Alert.alert('删除这项安排？', `${existing.snapshot.name} 将从行程中移除。`, [
      { text: '保留', style: 'cancel' },
      {
        text: '删除安排',
        style: 'destructive',
        onPress: () => {
          if (alive())
            void write.run((version) =>
              api.send(
                'DELETE',
                `/trips/${initial.id}/items/${existing.id}?version=${version}`,
                'TripResponse',
                undefined,
                { auth: true },
              ),
            );
        },
      },
    ]);
  };
  return (
    <Screen>
      <Heading
        title={existing ? '编辑地点安排' : '添加地点'}
        subtitle="同城目录 · 确认后保存到行程"
      />
      <Card>
        <Heading title={selected?.name ?? currentExisting?.snapshot.name ?? '尚未选择地点'} />
        {existing?.current_status === 'inactive' && !selected ? (
          <Notice tone="warning">
            此历史地点已停用，可保留快照修改备注或删除；替换时须选有效地点。
          </Notice>
        ) : null}
        {incoming?.city.id !== undefined && incoming.city.id !== initial.city_id ? (
          <Notice tone="error">带入地点与行程城市不同，请更换地点。</Notice>
        ) : null}
        <Button
          label={selecting ? '收起地点目录' : '搜索 / 更换地点'}
          secondary
          disabled={write.busy}
          onPress={() => setSelecting((value) => !value)}
        />
      </Card>
      {selecting ? (
        <Card>
          <Heading title="选择同城地点" />
          <View style={styles.wrap}>
            {kinds.map((item) => (
              <Chip
                key={item.kind}
                label={item.label}
                selected={kind === item.kind}
                onPress={() => {
                  setKind(item.kind);
                  setQ('');
                }}
              />
            ))}
          </View>
          <Field label="搜索地点名称" value={q} onChangeText={setQ} placeholder="输入关键词" />
          {page.loading ? <Copy>正在搜索同城地点…</Copy> : null}
          {page.items
            .filter((place) => place.city.id === initial.city_id && place.status === 'active')
            .map((place) => (
              <PlaceRow
                key={place.id}
                place={place}
                onPress={() => {
                  if (!write.busy) {
                    setSelected(place);
                    setSelecting(false);
                    setDirty(true);
                  }
                }}
              />
            ))}
          {page.error ? (
            <Failure error={page.error} retry={page.items.length ? page.loadMore : page.reload} />
          ) : null}
          {!page.loading && !page.error && page.items.length === 0 ? (
            <Empty
              title="没有匹配的同城地点"
              description="尝试清空关键词或更换类型。"
              action={<Button label="清空搜索" secondary onPress={() => setQ('')} />}
            />
          ) : null}
          {page.hasMore ? (
            <Button
              label="加载更多地点"
              secondary
              busy={page.loadingMore}
              onPress={page.loadMore}
            />
          ) : null}
        </Card>
      ) : null}
      <Heading title={currentKind === 'hotel' ? '选择入住夜' : '选择日期'} />
      <View style={styles.wrap}>
        {selectableDates.map((value) => (
          <Chip
            key={value}
            label={value.slice(5)}
            selected={date === value}
            onPress={() => edit(setDate)(value)}
          />
        ))}
      </View>
      {currentKind === 'hotel' ? (
        <Notice>
          酒店每项代表一晚，次日退房，不占白天时段，提交时间均为空。
          {selectableDates.length === 0 ? '该单日行程没有可选入住夜。' : ''}
        </Notice>
      ) : (
        <>
          <Field
            label="开始时间 HH:mm"
            value={start}
            onChangeText={edit(setStart)}
            autoCapitalize="none"
          />
          <Field
            label="结束时间 HH:mm"
            value={end}
            onChangeText={edit(setEnd)}
            autoCapitalize="none"
          />
        </>
      )}
      <Field
        label="备注（可选）"
        value={note}
        onChangeText={edit(setNote)}
        multiline
        placeholder="为这段安排留一点提醒"
      />
      {validation ? <Notice tone="error">{errorMessage(validation)}</Notice> : null}
      <WriteStatus write={write} />
      <Button
        label="确认保存地点"
        busy={write.busy}
        disabled={write.blocked || write.remaining > 0}
        onPress={() => {
          void save();
        }}
      />
      {existing ? (
        <Button
          label="删除这项安排"
          danger
          disabled={write.busy || write.blocked || write.remaining > 0}
          onPress={remove}
        />
      ) : null}
    </Screen>
  );
}

export function ChooseTripScreen(props: ScreenProps<'ChooseTrip'>) {
  const { state } = useApp();
  return state.user ? (
    <ChooseTripList
      key={`${state.epoch}:${props.route.params.placeId}:${props.route.params.cityId}`}
      {...props}
    />
  ) : (
    <Gate />
  );
}
function ChooseTripList({ route, navigation }: ScreenProps<'ChooseTrip'>) {
  const { api, state, revision } = useApp();
  const focused = useIsFocused();
  const [q, setQ] = useState('');
  const page = usePage(`choose-trip:${state.epoch}:${revision}:${focused}:${q}`, (number, signal) =>
    api.get(
      '/trips',
      'TripSummaryPageResponse',
      { q: q.trim() || undefined, page: number, page_size: 20 },
      { auth: true, signal },
    ),
  );
  const sameCity = page.items.filter((trip) => trip.city_id === route.params.cityId);
  return (
    <Screen refreshing={page.refreshing} onRefresh={page.reload}>
      <Heading
        title="加入哪段行程？"
        subtitle="只选择本人已有的同城行程，下一步再确认日期和时段。"
      />
      <Field label="按行程标题搜索" value={q} onChangeText={setQ} />
      {page.loading ? <Copy>正在读取本人行程…</Copy> : null}
      {sameCity.map((trip) => (
        <Card key={trip.id}>
          <Heading title={trip.title} subtitle={`${trip.start_date} 至 ${trip.end_date}`} />
          <Button
            label="选择这段行程"
            onPress={() =>
              navigation.replace('ItemForm', { tripId: trip.id, placeId: route.params.placeId })
            }
          />
        </Card>
      ))}
      {page.error ? (
        <Failure error={page.error} retry={page.items.length ? page.loadMore : page.reload} />
      ) : null}
      {!page.loading && !page.error && sameCity.length === 0 ? (
        <Empty
          title={
            page.hasMore
              ? '当前已读页面没有同城行程'
              : q.trim()
                ? '搜索结果中没有同城行程'
                : '还没有同城行程'
          }
          description={
            page.hasMore
              ? '还有未加载的本人行程，请继续加载，或新建一段行程。'
              : '创建空行程后，会进入地点表单，仍由你确认添加。'
          }
        />
      ) : null}
      {page.hasMore ? (
        <Button
          label="继续加载本人行程"
          secondary
          busy={page.loadingMore}
          onPress={page.loadMore}
        />
      ) : null}
      <Button
        label="新建同城行程"
        secondary
        onPress={() => navigation.navigate('TripForm', { placeId: route.params.placeId })}
      />
    </Screen>
  );
}
const styles = StyleSheet.create({
  copy: { fontSize: 16, lineHeight: 24, flexShrink: 1 },
  wrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
});
