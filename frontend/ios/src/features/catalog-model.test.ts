import { describe, expect, it } from 'vitest';
import { catalogQuery, priceFactText, safeImageUrl } from './catalog-model';

describe('目录硬筛选契约', () => {
  it.each([
    ['attraction', 'entry'],
    ['hotel', 'night'],
    ['restaurant', 'person'],
  ] as const)('%s 使用正确价格单位，明确0元仍发送上限', (kind, unit) => {
    expect(
      catalogQuery({
        cityId: 'city',
        kind,
        query: '  湖  ',
        categoryId: null,
        tags: ['tag-a', 'tag-b'],
        priceMax: 0,
      }),
    ).toEqual({
      city_id: 'city',
      kind,
      q: '湖',
      explicit_tags: ['tag-a', 'tag-b'],
      price_max_minor: 0,
      price_unit: unit,
    });
  });
  it('未设上限时不发送价格和计价单位，空文本和空标签不变成硬条件', () => {
    expect(
      catalogQuery({
        cityId: 'city',
        kind: 'hotel',
        query: '  ',
        categoryId: 'category',
        tags: [],
        priceMax: null,
      }),
    ).toEqual({
      city_id: 'city',
      kind: 'hotel',
      category_id: 'category',
    });
  });
  it('拒绝超出契约或不为整数分的价格', () => {
    for (const priceMax of [-1, 0.1, 100000001, Number.NaN]) {
      expect(() =>
        catalogQuery({
          cityId: 'city',
          kind: 'hotel',
          query: '',
          categoryId: null,
          tags: [],
          priceMax,
        }),
      ).toThrow();
    }
  });
});

describe('详情真实事实', () => {
  it('区分未知与已知0元，并显示实际单位', () => {
    expect(priceFactText(null)).toBe('暂无资料');
    expect(
      priceFactText({
        amount_minor: 0,
        currency: 'CNY',
        unit: 'night',
        observed_at: null,
        conditions: null,
      }),
    ).toBe('¥0.00 / 晚');
    expect(
      priceFactText({
        amount_minor: 1234,
        currency: 'CNY',
        unit: 'person',
        observed_at: null,
        conditions: null,
      }),
    ).toBe('¥12.34 / 人');
  });
  it('只允许无凭据的HTTPS图片，其他来源采用占位', () => {
    expect(safeImageUrl('https://images.example.org/a.jpg')).toBe(
      'https://images.example.org/a.jpg',
    );
    for (const url of [
      'http://images.example.org/a.jpg',
      'file:///secret',
      'data:image/png;base64,abc',
      'https://user:pass@example.org/a',
      'https://localhost/a',
      'bad url',
    ]) {
      expect(safeImageUrl(url)).toBeNull();
    }
  });
});
