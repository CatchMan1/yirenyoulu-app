import type { Kind, Model, Query } from '../api/types';

export type CatalogFilters = {
  cityId: string;
  kind: Kind;
  query: string;
  categoryId: string | null;
  tags: string[];
  priceMax: number | null;
};

const PRICE_UNIT: Record<Kind, 'entry' | 'night' | 'person'> = {
  attraction: 'entry',
  hotel: 'night',
  restaurant: 'person',
};
const UNIT_LABEL = { entry: '次', night: '晚', person: '人' };

export function catalogQuery(filters: CatalogFilters): Query {
  const { cityId, kind, query, categoryId, tags, priceMax } = filters;
  if (priceMax !== null && (!Number.isInteger(priceMax) || priceMax < 0 || priceMax > 100000000)) {
    throw new Error('价格上限必须为0至1,000,000元之间的整数分');
  }
  return {
    city_id: cityId,
    kind,
    ...(query.trim() ? { q: query.trim() } : {}),
    ...(categoryId ? { category_id: categoryId } : {}),
    ...(tags.length ? { explicit_tags: tags } : {}),
    ...(priceMax === null ? {} : { price_max_minor: priceMax, price_unit: PRICE_UNIT[kind] }),
  };
}

export function safeImageUrl(value: string): string | null {
  try {
    const url = new URL(value);
    if (
      url.protocol !== 'https:' ||
      url.username ||
      url.password ||
      url.hostname === 'localhost' ||
      url.hostname.endsWith('.localhost')
    )
      return null;
    return url.toString();
  } catch {
    return null;
  }
}

export function priceFactText(price: Model<'PriceFact'> | null): string {
  return price === null
    ? '暂无资料'
    : `¥${(price.amount_minor / 100).toFixed(2)} / ${UNIT_LABEL[price.unit]}`;
}
