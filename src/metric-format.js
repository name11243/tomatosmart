const ecNumberFormat = new Intl.NumberFormat('zh-CN', {
  maximumFractionDigits: 3,
  useGrouping: false,
});

export function formatMetricValue(metric, value, emptyText = '—') {
  if (value === null || value === undefined || value === '') return emptyText;
  if (metric !== 'ec') return value;
  const number = Number(value);
  return Number.isFinite(number) ? ecNumberFormat.format(number) : emptyText;
}
