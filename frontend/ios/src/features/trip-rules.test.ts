import { describe, expect, it } from 'vitest';
import { datesOutsideTrip, nextTripIntent, parseTime, visitDays } from './trip-rules';

describe('目的地日期和按夜住宿', () => {
  it('拒绝不存在的日期及超过14天的行程', () => {
    expect(() => visitDays('2027-02-29', '2027-03-02')).toThrow();
    expect(() => visitDays('2027-01-01', '2027-01-15')).toThrow();
    expect(visitDays('2028-02-28', '2028-03-01')).toEqual([
      '2028-02-28',
      '2028-02-29',
      '2028-03-01',
    ]);
  });
  it('缩短日期先指出越界的白天项目和退房夜，不删除任何安排', () => {
    const items = [
      { date: '2027-01-01', snapshot: { kind: 'attraction' } },
      { date: '2027-01-02', snapshot: { kind: 'hotel' } },
    ];
    expect(datesOutsideTrip(items, '2027-01-01', '2027-01-02')).toEqual([items[1]]);
    expect(items).toHaveLength(2);
    expect(datesOutsideTrip(items, '2027-01-01', '2027-01-03')).toEqual([]);
  });
  it('白天时间保持整数分钟，只允许结束于24:00', () => {
    expect(parseTime('09:05')).toBe(545);
    expect(parseTime('24:00', true)).toBe(1440);
    expect(() => parseTime('24:00')).toThrow();
    expect(() => parseTime('12:60')).toThrow();
    expect(() => parseTime('9:5')).toThrow();
  });
});

describe('手动创建幂等意图', () => {
  it('同一意图重试复用键，输入或账户变化生成新键', () => {
    let sequence = 0;
    const makeKey = () => `key-${++sequence}`;
    const first = nextTripIntent(null, 'epoch1:inputA', makeKey);
    expect(nextTripIntent(first, 'epoch1:inputA', makeKey)).toBe(first);
    const changed = nextTripIntent(first, 'epoch1:inputB', makeKey);
    expect(changed.key).not.toBe(first.key);
    expect(nextTripIntent(changed, 'epoch2:inputB', makeKey).key).not.toBe(changed.key);
  });
});
