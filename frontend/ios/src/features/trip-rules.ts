/** 日历日期按目的地解释，不使用设备本地时区。 */
export function visitDays(start: string, end: string): string[] {
  const parse = (value: string) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new Error('日期请使用 YYYY-MM-DD');
    const timestamp = Date.parse(`${value}T00:00:00Z`);
    if (!Number.isFinite(timestamp) || new Date(timestamp).toISOString().slice(0, 10) !== value) {
      throw new Error('请输入真实存在的日期');
    }
    return timestamp;
  };
  const first = parse(start);
  const last = parse(end);
  const count = (last - first) / 86_400_000 + 1;
  if (count < 1 || count > 14) throw new Error('行程需为1—14天，结束日期不能早于开始日期');
  return Array.from({ length: count }, (_, index) =>
    new Date(first + index * 86_400_000).toISOString().slice(0, 10),
  );
}

export function parseTime(value: string, end = false): number {
  if (!/^\d{2}:\d{2}$/.test(value)) throw new Error('时间请使用 HH:mm，例如 09:00');
  const hour = Number(value.slice(0, 2));
  const minute = Number(value.slice(3, 5));
  if (end && hour === 24 && minute === 0) return 1440;
  if (hour > 23 || minute > 59) throw new Error('时间不在有效范围内');
  return hour * 60 + minute;
}

export function datesOutsideTrip<T extends { date: string; snapshot: { kind: string } }>(
  items: readonly T[],
  start: string,
  end: string,
): T[] {
  return items.filter(
    (item) =>
      item.date < start || item.date > end || (item.snapshot.kind === 'hotel' && item.date >= end),
  );
}

export function nextTripIntent(
  previous: { fingerprint: string; key: string } | null,
  fingerprint: string,
  makeKey: () => string,
): { fingerprint: string; key: string } {
  return previous?.fingerprint === fingerprint ? previous : { fingerprint, key: makeKey() };
}
