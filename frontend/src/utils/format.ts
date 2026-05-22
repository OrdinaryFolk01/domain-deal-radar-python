export function parseJson<T>(value: string, fallback: T): T {
  try {
    const parsed = JSON.parse(value || '');
    return (parsed ?? fallback) as T;
  } catch {
    return fallback;
  }
}

export function formatDateTime(value?: string | null): string {
  if (!value) return '-';
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?/);
  if (!match) return String(value);
  const [, year, month, day, hour = '00', minute = '00', second = '00'] = match;
  return `${year}-${month}-${day} ${hour}:${minute}:${second}`;
}

export function splitPipe(value: string): string[] {
  return (value || '')
    .replaceAll('；', '|')
    .replaceAll(';', '|')
    .replaceAll(',', '|')
    .split('|')
    .map((item) => item.trim())
    .filter(Boolean);
}

export function numberText(value: number | null | undefined): string {
  return Number(value || 0).toLocaleString();
}
