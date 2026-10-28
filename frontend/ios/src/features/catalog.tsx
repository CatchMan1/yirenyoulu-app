import React, { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Image,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useIsFocused, useNavigation } from '@react-navigation/native';
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
  Field,
  Heading,
  Notice,
  PlaceRow,
  Screen,
  errorMessage,
  useTheme,
} from '../ui';
import { money, newId } from '../utils';
import { catalogQuery, priceFactText, safeImageUrl } from './catalog-model';

const KINDS: readonly Kind[] = ['attraction', 'hotel', 'restaurant'];
const KIND_LABEL: Record<Kind, string> = { attraction: '景点', hotel: '酒店', restaurant: '餐厅' };
const UNIT_LABEL: Record<Kind, string> = { attraction: '次', hotel: '晚', restaurant: '人' };
const REASONS: Record<Model<'RecommendationResult'>['reason'], string> = {
  collaborative: '根据浏览与收藏等历史相似偏好推荐',
  fallback_preferences: '根据明确偏好提供候选',
  fallback_catalog: '基础目录推荐，尚无足够的个性化依据',
};

function Paragraph({ children, muted = false }: { children: React.ReactNode; muted?: boolean }) {
  const theme = useTheme();
  return (
    <Text style={[styles.paragraph, { color: muted ? theme.muted : theme.text }]}>{children}</Text>
  );
}

function Loading({ label = '正在读取…' }: { label?: string }) {
  const theme = useTheme();
  return (
    <View style={styles.loading} accessibilityRole="progressbar" accessibilityLabel={label}>
      <ActivityIndicator color={theme.primary} />
      <Paragraph muted>{label}</Paragraph>
    </View>
  );
}

function Failure({ error, retry }: { error: unknown; retry: () => void }) {
  const [remaining, setRemaining] = useState(0);
  useEffect(() => {
    const seconds = error instanceof ApiError && error.status === 429 ? (error.retryAfter ?? 1) : 0;
    const until = Date.now() + seconds * 1000;
    const tick = () => setRemaining(Math.max(0, Math.ceil((until - Date.now()) / 1000)));
    tick();
    if (!seconds) return;
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [error]);
  return (
    <View style={styles.section}>
      <Notice tone="error">{errorMessage(error)}</Notice>
      <Button
        secondary
        label={remaining ? `${remaining}秒后可重试` : '重新读取'}
        disabled={remaining > 0}
        onPress={retry}
      />
    </View>
  );
}

function ListFooter({
  error,
  retry,
  loading,
  hasMore,
  loadMore,
}: {
  error: unknown;
  retry: () => void;
  loading: boolean;
  hasMore: boolean;
  loadMore: () => void;
}) {
  return (
    <View style={styles.footer}>
      {!!error && <Failure error={error} retry={retry} />}
      {loading ? (
        <Loading label="正在加载下一页…" />
      ) : hasMore && !error ? (
        <Button secondary label="加载更多" onPress={loadMore} />
      ) : null}
    </View>
  );
}

function KindTabs({
  value,
  onChange,
  all = false,
}: {
  value: Kind | null;
  onChange: (kind: Kind | null) => void;
  all?: boolean;
}) {
  return (
    <View style={styles.chips}>
      {all && <Chip label="全部" selected={value === null} onPress={() => onChange(null)} />}
      {KINDS.map((kind) => (
        <Chip
          key={kind}
          label={KIND_LABEL[kind]}
          selected={value === kind}
          onPress={() => onChange(kind)}
        />
      ))}
    </View>
  );
}

export function ExploreScreen() {
  const { api, city, state, revision } = useApp();
  const navigation = useNavigation<NativeStackNavigationProp<RootRoutes>>();
  const focused = useIsFocused();
  const prompted = useRef(false);
  const theme = useTheme();
  const recommendations = useResource(
    `recommendations:${city?.id}:${state.epoch}:${revision}`,
    (signal) =>
      api.get(
        '/recommendations',
        'RecommendationResultResponse',
        { city_id: city?.id, limit: 8 },
        { signal, auth: !!state.user },
      ),
    !!city,
  );
  useEffect(() => {
    if (focused && !city && !prompted.current) {
      prompted.current = true;
      navigation.navigate('CityPicker');
    }
  }, [focused, city, navigation]);
  return (
    <Screen refreshing={recommendations.refreshing} onRefresh={recommendations.reload}>
      <View style={styles.intro}>
        <Paragraph muted>一人有路 · 按自己的节奏出发</Paragraph>
        <Text accessibilityRole="header" style={[styles.heroTitle, { color: theme.text }]}>
          下一站，慢慢发现
        </Text>
        <Button
          secondary
          label={city ? `${city.name} · 更换城市` : '选择目的地城市'}
          onPress={() => navigation.navigate('CityPicker')}
        />
      </View>
      {!city ? (
        <Empty
          title="先选一座城市"
          description="从城市目录中选择目的地，无需定位授权。"
          action={<Button label="选择城市" onPress={() => navigation.navigate('CityPicker')} />}
        />
      ) : (
        <>
          <Card>
            <Heading title={`探索${city.name}`} subtitle="找一处风景，一晚好眠，一顿合意的饭。" />
            <Button
              secondary
              label="搜索地点、分类或标签"
              onPress={() => navigation.navigate('Catalog', { kind: 'attraction' })}
            />
            <View style={styles.section}>
              {KINDS.map((kind) => (
                <Button
                  key={kind}
                  label={`浏览${KIND_LABEL[kind]}`}
                  secondary
                  onPress={() => navigation.navigate('Catalog', { kind })}
                />
              ))}
            </View>
          </Card>
          <Card>
            <Heading title="把喜欢的地方排进旅程" subtitle="先建一个空行程，再按天安排。" />
            <Button
              label={state.user ? '创建手动行程' : '登录并创建行程'}
              onPress={() => navigation.navigate(state.user ? 'TripForm' : 'Login')}
            />
          </Card>
          <Heading title="发现更多" subtitle="以下候选来自当前城市的推荐接口。" />
          {recommendations.loading && !recommendations.data && <Loading />}
          {!!recommendations.error && (
            <Failure error={recommendations.error} retry={recommendations.reload} />
          )}
          {recommendations.data && (
            <>
              <Notice>{REASONS[recommendations.data.data.reason]}</Notice>
              {recommendations.data.data.items.length === 0 ? (
                <Empty title="暂时没有推荐候选" description="仍可搜索目录，或更换城市。" />
              ) : (
                recommendations.data.data.items.map((place) => (
                  <PlaceRow
                    key={place.id}
                    place={place}
                    onPress={() => navigation.navigate('Place', { id: place.id })}
                  />
                ))
              )}
            </>
          )}
        </>
      )}
    </Screen>
  );
}

export function CityPickerScreen({ navigation }: ScreenProps<'CityPicker'>) {
  const { api, city, setCity } = useApp();
  const [query, setQuery] = useState('');
  const theme = useTheme();
  const cities = usePage(`cities:${query.trim()}`, (page, signal) =>
    api.get(
      '/cities',
      'CityPageResponse',
      { q: query.trim() || undefined, page, page_size: 20 },
      { signal },
    ),
  );
  return (
    <Screen scroll={false}>
      <FlatList
        data={cities.items}
        keyExtractor={(item) => item.id}
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={styles.list}
        refreshing={cities.refreshing}
        onRefresh={cities.reload}
        ListHeaderComponent={
          <View style={styles.section}>
            <Heading title="选择目的地" subtitle="城市来自后端目录，各类地点资料数量可能不同。" />
            {city && <Notice>当前城市：{city.name}。更换城市不影响已有行程。</Notice>}
            <Field
              label="搜索城市"
              value={query}
              onChangeText={(value) => setQuery(value.slice(0, 100))}
              placeholder="输入城市名称"
            />
          </View>
        }
        renderItem={({ item }) => (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`选择${item.name}${city?.id === item.id ? '，当前城市' : ''}`}
            onPress={() => {
              setCity(item);
              navigation.goBack();
            }}
            style={({ pressed }) => [
              styles.city,
              { backgroundColor: pressed ? theme.tint : theme.card, borderColor: theme.border },
            ]}
          >
            <Text style={[styles.rowTitle, { color: theme.text }]}>{item.name}</Text>
            <Text style={{ color: theme.primary }}>
              {city?.id === item.id ? '已选择' : '选择 ›'}
            </Text>
          </Pressable>
        )}
        ListEmptyComponent={
          cities.loading ? (
            <Loading />
          ) : !cities.error ? (
            <Empty
              title="没有找到城市"
              description="试试其他名称或清空搜索。"
              action={<Button secondary label="清空搜索" onPress={() => setQuery('')} />}
            />
          ) : null
        }
        ListFooterComponent={
          <ListFooter
            error={cities.error}
            retry={cities.items.length ? cities.loadMore : cities.reload}
            loading={cities.loadingMore}
            hasMore={cities.hasMore}
            loadMore={cities.loadMore}
          />
        }
      />
    </Screen>
  );
}

export function CatalogScreen(props: ScreenProps<'Catalog'>) {
  const { city } = useApp();
  if (!city)
    return (
      <Screen>
        <Empty
          title="请先选择目的地"
          action={
            <Button label="选择城市" onPress={() => props.navigation.navigate('CityPicker')} />
          }
        />
      </Screen>
    );
  return <CatalogContent key={`${city.id}:${props.route.params.kind}`} {...props} city={city} />;
}

function CatalogContent({
  navigation,
  route,
  city,
}: ScreenProps<'Catalog'> & { city: Model<'City'> }) {
  const { api } = useApp();
  const kind = route.params.kind;
  const [query, setQuery] = useState('');
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const [tags, setTags] = useState<string[]>([]);
  const [priceDraft, setPriceDraft] = useState('');
  const [priceMax, setPriceMax] = useState<number | null>(null);
  const [priceError, setPriceError] = useState('');
  const [filtersOpen, setFiltersOpen] = useState(false);
  const filters = catalogQuery({ cityId: city.id, kind, query, categoryId, tags, priceMax });
  const places = usePage(`places:${JSON.stringify(filters)}`, (page, signal) =>
    api.get('/places', 'PlacePageResponse', { ...filters, page, page_size: 20 }, { signal }),
  );
  const categories = usePage(
    `categories:${kind}`,
    (page, signal) =>
      api.get('/categories', 'NamedEntryPageResponse', { page, page_size: 20 }, { signal }),
    filtersOpen,
  );
  const tagOptions = usePage(
    `tags:${kind}`,
    (page, signal) =>
      api.get('/tags', 'NamedEntryPageResponse', { page, page_size: 20 }, { signal }),
    filtersOpen,
  );
  function clearFilters() {
    setQuery('');
    setCategoryId(null);
    setTags([]);
    setPriceDraft('');
    setPriceMax(null);
    setPriceError('');
  }
  function applyPrice() {
    try {
      const value = money(priceDraft);
      if (value !== null && value > 100000000) throw new Error('价格上限不能超过1,000,000元');
      setPriceMax(value);
      setPriceError('');
    } catch (error) {
      setPriceError(error instanceof Error ? error.message : '请输入合法金额');
    }
  }
  return (
    <Screen scroll={false}>
      <FlatList
        data={places.items}
        keyExtractor={(item) => item.id}
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={styles.list}
        refreshing={places.refreshing}
        onRefresh={places.reload}
        ListHeaderComponent={
          <View style={styles.section}>
            <Heading
              title={`${city.name} · ${KIND_LABEL[kind]}`}
              action={<Chip label="更换城市" onPress={() => navigation.navigate('CityPicker')} />}
            />
            <KindTabs
              value={kind}
              onChange={(value) => {
                if (value) navigation.setParams({ kind: value });
              }}
            />
            <Field
              label="搜索地点"
              value={query}
              onChangeText={(value) => setQuery(value.slice(0, 100))}
              placeholder={`搜索${KIND_LABEL[kind]}名称`}
            />
            <View style={styles.chips}>
              <Chip
                label={filtersOpen ? '收起筛选' : '分类与价格筛选'}
                selected={filtersOpen}
                onPress={() => setFiltersOpen((value) => !value)}
              />
              <Chip label="清空条件" onPress={clearFilters} />
            </View>
            {filtersOpen && (
              <Card>
                <Paragraph>分类（单选）</Paragraph>
                <View style={styles.chips}>
                  <Chip
                    label="全部分类"
                    selected={!categoryId}
                    onPress={() => setCategoryId(null)}
                  />
                  {categories.items.map((item) => (
                    <Chip
                      key={item.id}
                      label={item.name}
                      selected={item.id === categoryId}
                      onPress={() => setCategoryId(item.id)}
                    />
                  ))}
                </View>
                {categories.loading && <Loading label="读取分类…" />}
                <ListFooter
                  error={categories.error}
                  retry={categories.items.length ? categories.loadMore : categories.reload}
                  loading={categories.loadingMore}
                  hasMore={categories.hasMore}
                  loadMore={categories.loadMore}
                />
                <Paragraph>明确标签（同时满足，最多20项）</Paragraph>
                <View style={styles.chips}>
                  {tagOptions.items.map((item) => (
                    <Chip
                      key={item.id}
                      label={item.name}
                      selected={tags.includes(item.id)}
                      onPress={() =>
                        setTags((current) =>
                          current.includes(item.id)
                            ? current.filter((id) => id !== item.id)
                            : current.length < 20
                              ? [...current, item.id]
                              : current,
                        )
                      }
                    />
                  ))}
                </View>
                {tagOptions.loading && <Loading label="读取标签…" />}
                <ListFooter
                  error={tagOptions.error}
                  retry={tagOptions.items.length ? tagOptions.loadMore : tagOptions.reload}
                  loading={tagOptions.loadingMore}
                  hasMore={tagOptions.hasMore}
                  loadMore={tagOptions.loadMore}
                />
                <Field
                  label={`价格上限（元 / ${UNIT_LABEL[kind]}）`}
                  value={priceDraft}
                  onChangeText={setPriceDraft}
                  keyboardType="decimal-pad"
                  placeholder="留空不限价格"
                  error={priceError || undefined}
                />
                <Button secondary label="应用价格上限" onPress={applyPrice} />
                <Paragraph muted>
                  {priceMax === null
                    ? '当前不限价格。'
                    : `已应用：¥${(priceMax / 100).toFixed(2)} / ${UNIT_LABEL[kind]}以内；未知价格不在结果中。`}
                </Paragraph>
              </Card>
            )}
          </View>
        }
        renderItem={({ item }) => (
          <PlaceRow place={item} onPress={() => navigation.navigate('Place', { id: item.id })} />
        )}
        ListEmptyComponent={
          places.loading ? (
            <Loading />
          ) : !places.error ? (
            <Empty
              title="暂时没有符合条件的地点"
              description="可清空条件、更换类型或选择其他城市。"
              action={<Button secondary label="清空条件" onPress={clearFilters} />}
            />
          ) : null
        }
        ListFooterComponent={
          <ListFooter
            error={places.error}
            retry={places.items.length ? places.loadMore : places.reload}
            loading={places.loadingMore}
            hasMore={places.hasMore}
            loadMore={places.loadMore}
          />
        }
      />
    </Screen>
  );
}

/** A session owns each write; a late response cannot update another account's UI. */
function useFavoriteWrite() {
  const { api, state, invalidate } = useApp();
  const active = useRef<{ id: string; controller: AbortController } | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const blockedUntil = useRef(0);
  useEffect(() => {
    return () => {
      active.current?.controller.abort();
      active.current = null;
    };
  }, []);
  async function run(id: string, favorite: boolean) {
    if (!state.user || active.current || Date.now() < blockedUntil.current) return;
    const request = { id, controller: new AbortController() };
    active.current = request;
    setBusyId(id);
    setError(null);
    try {
      await api.send(favorite ? 'PUT' : 'DELETE', `/favorites/${id}`, null, undefined, {
        auth: true,
        signal: request.controller.signal,
      });
      if (!request.controller.signal.aborted) invalidate();
    } catch (failure) {
      if (!request.controller.signal.aborted) {
        if (failure instanceof ApiError && failure.status === 429)
          blockedUntil.current = Date.now() + (failure.retryAfter ?? 1) * 1000;
        setError(failure);
      }
    } finally {
      if (active.current === request) {
        active.current = null;
        setBusyId(null);
      }
    }
  }
  return { busyId, error, run };
}

function PlacePicture({ place }: { place: Model<'PlaceDetail'> }) {
  const theme = useTheme();
  const candidate = place.images.find((image) => safeImageUrl(image.url));
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const url = candidate ? safeImageUrl(candidate.url) : null;
  if (url && failedUrl !== url)
    return (
      <View style={styles.section}>
        <Image
          source={{ uri: url }}
          style={styles.picture}
          resizeMode="cover"
          accessibilityLabel={`${place.name}，图片来源${candidate?.source_name ?? ''}`}
          onError={() => setFailedUrl(url)}
        />
        <Paragraph muted>图片来源：{candidate?.source_name}</Paragraph>
      </View>
    );
  return (
    <View
      style={[styles.placeholder, { backgroundColor: theme.tint, borderColor: theme.border }]}
      accessibilityLabel={`${KIND_LABEL[place.kind]}，暂无可展示图片`}
    >
      <View
        style={[
          styles.geometry,
          {
            borderColor: theme.primary,
            borderRadius: place.kind === 'restaurant' ? 42 : place.kind === 'hotel' ? 12 : 2,
            transform: [{ rotate: place.kind === 'attraction' ? '45deg' : '0deg' }],
          },
        ]}
      />
      <Text style={[styles.placeholderText, { color: theme.primary }]}>
        {KIND_LABEL[place.kind]} · 暂无可展示图片
      </Text>
    </View>
  );
}

function Fact({ label, value }: { label: string; value: string | null | undefined }) {
  const theme = useTheme();
  return (
    <View style={[styles.fact, { borderBottomColor: theme.border }]}>
      <Text style={[styles.factLabel, { color: theme.muted }]}>{label}</Text>
      <Text selectable style={[styles.factValue, { color: theme.text }]}>
        {value || '暂无资料'}
      </Text>
    </View>
  );
}

function observed(value: string | null | undefined): string {
  if (!value) return '暂无资料';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? '暂无资料'
    : parsed.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false });
}

export function PlaceScreen(props: ScreenProps<'Place'>) {
  const { state } = useApp();
  return <PlaceContent key={`${props.route.params.id}:${state.epoch}`} {...props} />;
}

function PlaceContent({ route, navigation }: ScreenProps<'Place'>) {
  const { api, state, revision } = useApp();
  const theme = useTheme();
  const focused = useIsFocused();
  const id = route.params.id;
  const detail = useResource(`place:${id}:${revision}`, (signal) =>
    api.get(`/places/${id}`, 'PlaceDetailResponse', undefined, { signal }),
  );
  const favorite = useResource(
    `favorite:${id}:${state.epoch}:${revision}`,
    (signal) =>
      api.get(`/favorites/${id}`, 'FavoriteStatusResponse', undefined, { auth: true, signal }),
    !!state.user,
  );
  const write = useFavoriteWrite();
  const viewed = useRef(false);
  const [viewError, setViewError] = useState<unknown>(null);
  const inaccessible =
    detail.error instanceof ApiError && [403, 404].includes(detail.error.status ?? 0);
  const place = inaccessible ? undefined : detail.data?.data;
  const viewController = useRef<AbortController | null>(null);
  useEffect(() => () => viewController.current?.abort(), []);
  useEffect(() => {
    if (!focused || !state.user || !place || viewed.current) return;
    viewed.current = true;
    const controller = new AbortController();
    viewController.current = controller;
    const intent: Model<'BehaviorCreate'> = {
      event_id: newId(),
      place_id: place.id,
      type: 'view',
      occurred_at: new Date().toISOString(),
    };
    // This display intent is sent once. Errors never create a fresh event or timestamp.
    void api
      .send('POST', '/behavior-events', 'BehaviorReceiptResponse', intent, {
        auth: true,
        signal: controller.signal,
      })
      .catch((failure) => {
        if (!controller.signal.aborted) setViewError(failure);
      });
  }, [api, focused, place, state.epoch, state.user]);
  function addToTrip() {
    if (!place || place.status !== 'active') return;
    if (!state.user) navigation.navigate('Login');
    else navigation.navigate('ChooseTrip', { placeId: place.id, cityId: place.city.id });
  }
  return (
    <Screen
      refreshing={detail.refreshing}
      onRefresh={() => {
        detail.reload();
        if (state.user) favorite.reload();
      }}
    >
      {detail.loading && !place && <Loading />}
      {!!detail.error && <Failure error={detail.error} retry={detail.reload} />}
      {inaccessible && (
        <Empty
          title="地点暂不可访问"
          description="资料可能已失效或不再开放展示。"
          action={<Button secondary label="返回浏览" onPress={() => navigation.goBack()} />}
        />
      )}
      {place && (
        <>
          <Heading
            title={place.name}
            subtitle={`${place.city.name} · ${KIND_LABEL[place.kind]}${place.category ? ` · ${place.category.name}` : ''}`}
          />
          {place.is_test && <Notice tone="warning">此地点为明确标记的测试资料。</Notice>}
          {place.status !== 'active' && (
            <Notice tone="warning">此地点资料已失效，不能新加入行程。</Notice>
          )}
          <PlacePicture key={place.id} place={place} />
          <View style={styles.chips}>
            {place.tags.map((tag) => (
              <View
                key={tag.id}
                style={[styles.tag, { backgroundColor: theme.tint, borderColor: theme.border }]}
              >
                <Text style={{ color: theme.primary }}>{tag.name}</Text>
              </View>
            ))}
          </View>
          <Card>
            <Fact label="地址" value={place.address} />
            <Fact
              label="坐标"
              value={
                place.coordinates
                  ? `${place.coordinates.longitude}, ${place.coordinates.latitude}（${place.coordinates.crs}）`
                  : null
              }
            />
            <Fact label="简介" value={place.description} />
            <Fact label="参考价格" value={priceFactText(place.price)} />
            {place.price && (
              <>
                <Fact label="价格适用条件" value={place.price.conditions} />
                <Fact label="价格观察时间" value={observed(place.price.observed_at)} />
              </>
            )}
            <Fact label="营业时间" value={place.opening_hours?.raw_text} />
            {place.opening_hours && (
              <Fact label="营业时间观察日期" value={observed(place.opening_hours.observed_at)} />
            )}
            <Fact
              label="评分"
              value={
                place.rating ? `${place.rating.value} / ${place.rating.scale}（来源量表）` : null
              }
            />
            {place.kind === 'hotel' && (
              <Fact
                label="酒店星级"
                value={place.hotel_stars === null ? null : `${place.hotel_stars}星`}
              />
            )}
            {place.kind === 'restaurant' && <Fact label="菜系" value={place.cuisine} />}
            {place.estimate && (
              <>
                <Fact
                  label="费用估算"
                  value={`¥${(place.estimate.amount_minor / 100).toFixed(2)}（估算）`}
                />
                <Fact label="估算依据" value={place.estimate.reason} />
                <Fact label="估算来源" value={place.estimate.source} />
              </>
            )}
          </Card>
          <Card>
            <Heading title="资料来源" />
            <Fact label="来源" value={place.provenance.source_name} />
            <Fact label="来源地址" value={place.provenance.source_url} />
            <Fact label="核验时间" value={observed(place.provenance.checked_at)} />
            <Paragraph muted>价格与营业信息以来源说明为准，参考资料不代表可预订报价。</Paragraph>
          </Card>
          {!state.user ? (
            <Button secondary label="登录后收藏" onPress={() => navigation.navigate('Login')} />
          ) : (
            <>
              <Button
                secondary
                label={
                  favorite.loading
                    ? '读取收藏状态…'
                    : favorite.error || !favorite.data
                      ? '收藏状态未知'
                      : favorite.data.data.is_favorited
                        ? '已收藏 · 取消收藏'
                        : '收藏地点'
                }
                busy={write.busyId === id}
                disabled={favorite.loading || !!favorite.error || !favorite.data || !!write.busyId}
                onPress={() => {
                  if (favorite.data && !favorite.error)
                    void write.run(id, !favorite.data.data.is_favorited);
                }}
              />
              {!!favorite.error && <Failure error={favorite.error} retry={favorite.reload} />}
              {!!write.error && (
                <>
                  <Notice tone="warning">
                    收藏操作未确认成功，保留上次已确认状态。请重新读取后再操作。
                  </Notice>
                  <Failure error={write.error} retry={favorite.reload} />
                </>
              )}
            </>
          )}
          <Button
            label={state.user ? '加入行程' : '登录后加入行程'}
            disabled={place.status !== 'active'}
            onPress={addToTrip}
          />
          {!!viewError && <Paragraph muted>本次浏览记录未确认，详情和手动操作仍可使用。</Paragraph>}
        </>
      )}
    </Screen>
  );
}

export function FavoritesScreen(props: ScreenProps<'Favorites'>) {
  const { state } = useApp();
  return <FavoritesContent key={state.epoch} {...props} />;
}

function FavoritesContent({ navigation }: ScreenProps<'Favorites'>) {
  const { api, state, revision } = useApp();
  const [kind, setKind] = useState<Kind | null>(null);
  const favorites = usePage(
    `favorites:${state.epoch}:${revision}:${kind}`,
    (page, signal) =>
      api.get(
        '/favorites',
        'PlacePageResponse',
        { kind, page, page_size: 20 },
        { auth: true, signal },
      ),
    !!state.user,
  );
  const write = useFavoriteWrite();
  if (!state.user)
    return (
      <Screen>
        <Empty
          title="把喜欢的地方留给自己"
          description="登录后查看与管理本人的收藏。"
          action={<Button label="登录" onPress={() => navigation.navigate('Login')} />}
        />
      </Screen>
    );
  return (
    <Screen scroll={false}>
      <FlatList
        data={favorites.items}
        keyExtractor={(place) => place.id}
        contentContainerStyle={styles.list}
        refreshing={favorites.refreshing}
        onRefresh={favorites.reload}
        ListHeaderComponent={
          <View style={styles.section}>
            <Heading title="我的收藏" subtitle="按收藏时间排列，只展示本人的记录。" />
            <KindTabs value={kind} onChange={setKind} all />
            {!!write.error && (
              <>
                <Notice tone="warning">取消收藏未确认成功，请先重新读取。</Notice>
                <Failure error={write.error} retry={favorites.reload} />
              </>
            )}
          </View>
        }
        renderItem={({ item }) => (
          <Card>
            {item.status === 'active' ? (
              <PlaceRow
                place={item}
                onPress={() => navigation.navigate('Place', { id: item.id })}
              />
            ) : (
              <>
                <Heading
                  title={item.name}
                  subtitle={`${item.city.name} · ${KIND_LABEL[item.kind]}`}
                />
                <Notice tone="warning">资料已失效或不可展示，保留收藏摘要，可取消收藏。</Notice>
              </>
            )}
            <View style={styles.section}>
              {item.status === 'active' && (
                <Button
                  secondary
                  label="加入行程"
                  disabled={!!write.busyId}
                  onPress={() =>
                    navigation.navigate('ChooseTrip', { placeId: item.id, cityId: item.city.id })
                  }
                />
              )}
              <Button
                secondary
                label="取消收藏"
                disabled={!!write.busyId}
                busy={write.busyId === item.id}
                onPress={() => {
                  void write.run(item.id, false);
                }}
              />
            </View>
          </Card>
        )}
        ListEmptyComponent={
          favorites.loading ? (
            <Loading />
          ) : !favorites.error ? (
            <Empty
              title="这里还没有收藏"
              description="浏览地点详情，收藏想去的地方。"
              action={
                <Button
                  secondary
                  label="去探索"
                  onPress={() => navigation.navigate('Catalog', { kind: 'attraction' })}
                />
              }
            />
          ) : null
        }
        ListFooterComponent={
          <ListFooter
            error={favorites.error}
            retry={favorites.items.length ? favorites.loadMore : favorites.reload}
            loading={favorites.loadingMore}
            hasMore={favorites.hasMore}
            loadMore={favorites.loadMore}
          />
        }
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  intro: { gap: 14, paddingTop: 8, paddingBottom: 12 },
  heroTitle: { fontSize: 28, fontWeight: '700', lineHeight: 38 },
  paragraph: { fontSize: 15, lineHeight: 23 },
  section: { gap: 12 },
  loading: { paddingVertical: 24, alignItems: 'center', gap: 10 },
  footer: { paddingTop: 12, paddingBottom: 28, gap: 12 },
  list: { gap: 14, paddingBottom: 24 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  city: {
    minHeight: 64,
    padding: 16,
    borderWidth: 1,
    borderRadius: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  rowTitle: { fontSize: 18, fontWeight: '600', flexShrink: 1 },
  picture: { width: '100%', aspectRatio: 1.55, borderRadius: 16 },
  placeholder: {
    minHeight: 200,
    borderWidth: 1,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 24,
    padding: 24,
  },
  geometry: { width: 62, height: 62, borderWidth: 3 },
  placeholderText: { fontSize: 14, textAlign: 'center' },
  tag: { paddingHorizontal: 12, paddingVertical: 8, borderWidth: 1, borderRadius: 20 },
  fact: { gap: 6, paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth },
  factLabel: { fontSize: 14, lineHeight: 21 },
  factValue: { fontSize: 16, lineHeight: 25 },
});
