import { useQuery } from '@tanstack/react-query';

import { accessTokenForDownload, api, API_BASE, getActiveFarmId, refreshSession } from '@/api/client';

export interface FilterDef {
  key: string;
  label: string;
  type: 'select' | 'animal' | 'location' | 'category' | 'member';
  options: { value: string; label: string }[];
}
export interface ReportInfo {
  key: string;
  title: string;
  description: string;
  section: string;
  default_period: string;
  uses_period: boolean;
  filters: FilterDef[];
}
export interface Column {
  key: string;
  label: string;
  type: 'text' | 'date' | 'number' | 'percent';
}
export interface ReportTable {
  key: string;
  title: string;
  columns: Column[];
  rows: Record<string, string | number | null>[];
}
export interface Card {
  key: string;
  label: string;
  value: number | string;
  unit: string;
}
export interface Chart {
  type: 'bar' | 'line';
  title: string;
  labels: string[];
  series: { name: string; values: number[] }[];
  stacked: boolean;
}
export interface ReportData {
  key: string;
  title: string;
  from: string;
  to: string;
  period_label: string;
  group: string;
  filters: Record<string, string>;
  summary: Card[];
  chart: Chart | null;
  tables: ReportTable[];
  row_count: number;
}
export interface Schedule {
  id: string;
  report_type: 'monthly_activities' | 'quarterly_health';
  report_label: string;
  recipients: string[];
  format: 'pdf' | 'xlsx' | 'csv';
  enabled: boolean;
  last_period: string;
  last_sent_at: string | null;
}

export function useCatalog() {
  return useQuery({
    queryKey: ['reports', 'catalog'],
    queryFn: () => api<ReportInfo[]>('/reports'),
    staleTime: 600_000,
  });
}

export function useReport(key: string, query: Record<string, string>) {
  return useQuery({
    queryKey: ['reports', key, query],
    queryFn: () => api<ReportData>(`/reports/${key}`, { query }),
    placeholderData: (prev) => prev,
  });
}

/** Series colours: farm greens and neutral tones that stay apart in print. */
export const SERIES_COLOURS = ['#2e7d32', '#ef6c00', '#1565c0', '#6a1b9a', '#c62828', '#00838f'];

export const FORMATS = [
  ['pdf', 'PDF'],
  ['xlsx', 'Excel'],
  ['csv', 'CSV'],
] as const;

export type DownloadResult = { kind: 'file' } | { kind: 'queued'; message: string };

/** Downloads with the session token; a large report answers 202 and is built in the background. */
export async function downloadFile(
  path: string,
  query: Record<string, string>,
  fallback: string,
): Promise<DownloadResult> {
  const url = new URL(`${API_BASE}${path}`, window.location.origin);
  Object.entries(query).forEach(([k, v]) => v && url.searchParams.set(k, v));
  const send = () =>
    fetch(url, {
      headers: { Authorization: `Bearer ${accessTokenForDownload()}`, 'X-Farm-ID': getActiveFarmId() ?? '' },
      credentials: 'include',
    });
  let res = await send();
  if (res.status === 401 && (await refreshSession())) res = await send();
  if (res.status === 202) {
    const body = (await res.json()) as { message?: string };
    return { kind: 'queued', message: body.message ?? "We'll notify you when the file is ready." };
  }
  if (!res.ok) {
    let message = 'The file could not be downloaded.';
    try {
      const body = (await res.json()) as { errors?: Record<string, string[]> };
      const first = body.errors && Object.values(body.errors)[0]?.[0];
      if (first) message = first;
    } catch {
      /* not JSON */
    }
    throw new Error(message);
  }
  const blob = await res.blob();
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = res.headers.get('Content-Disposition')?.match(/filename="(.+)"/)?.[1] ?? fallback;
  link.click();
  URL.revokeObjectURL(link.href);
  return { kind: 'file' };
}

export function formatCell(value: string | number | null | undefined, type: Column['type']) {
  if (value === null || value === undefined || value === '') return '—';
  if (type === 'date' && typeof value === 'string') {
    const d = new Date(`${value}T00:00:00`);
    return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
  }
  if (type === 'percent') return `${value}%`;
  return String(value);
}

export function cardValue(c: Card) {
  return c.unit === '%' ? `${c.value}%` : `${c.value}${c.unit ? ` ${c.unit}` : ''}`;
}
