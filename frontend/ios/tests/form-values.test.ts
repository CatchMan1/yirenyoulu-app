import { expect, it } from 'vitest';
import { money, dateRange } from '../src/form-values';
it('preserves unknown and zero and converts decimal currency exactly', () => {
  expect(money('')).toBeNull();
  expect(money('0')).toBe(0);
  expect(money('0.29')).toBe(29);
  expect(() => money('1e5')).toThrow();
  expect(() => money('1.001')).toThrow();
  expect(() => money('1000000.01')).toThrow();
});
it('rejects normalized invalid calendar dates and excessive trip length', () => {
  expect(() => dateRange('2027-02-29', '2027-03-01')).toThrow();
  expect(dateRange('2028-02-29', '2028-03-01')).toEqual(['2028-02-29', '2028-03-01']);
  expect(() => dateRange('2027-01-01', '2027-01-15')).toThrow();
});
