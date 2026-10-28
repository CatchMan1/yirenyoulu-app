export function money(value: string): number | null {
  const text = value.trim();
  if (!text) return null;
  if (!/^\d{1,7}(\.\d{1,2})?$/.test(text)) throw new Error('请输入最多两位小数的非负金额');
  const [major = '0', minor = ''] = text.split('.');
  const amount = Number(major) * 100 + Number(minor.padEnd(2, '0'));
  if (amount > 100000000) throw new Error('金额不能超过 1,000,000 元');
  return amount;
}
export const moneyText = (value: number | null | undefined) =>
  value == null ? '暂无资料' : `¥${(value / 100).toFixed(2)}`;
export function today() {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date());
}
export function dateRange(start: string, end: string) {
  const first = Date.parse(start + 'T00:00:00Z'),
    last = Date.parse(end + 'T00:00:00Z');
  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(start) ||
    !/^\d{4}-\d{2}-\d{2}$/.test(end) ||
    !Number.isFinite(first) ||
    !Number.isFinite(last) ||
    new Date(first).toISOString().slice(0, 10) !== start ||
    new Date(last).toISOString().slice(0, 10) !== end ||
    last < first ||
    last - first > 13 * 86400000
  )
    throw new Error('请选择有效的 1—14 天日期范围');
  return Array.from({ length: (last - first) / 86400000 + 1 }, (_, i) =>
    new Date(first + i * 86400000).toISOString().slice(0, 10),
  );
}
export const timeText = (minute: number | null) =>
  minute == null
    ? '当晚住宿'
    : `${String(Math.floor(minute / 60)).padStart(2, '0')}:${String(minute % 60).padStart(2, '0')}`;
