import { useQuery } from '@tanstack/react-query';

import { api, type Schemas } from '@/api/client';

export type Activity = Schemas['Activity'];
export type Category = Schemas['Category'];
export interface Assignee {
  id: string;
  name: string;
  role: string;
  role_label: string;
}
export interface Note {
  id: string;
  text: string;
  author: string | null;
  created_at: string;
}
export interface HistoryRow {
  id: string;
  from_status: string;
  to_status: string;
  note: string;
  by: string | null;
  created_at: string;
}

export function useCategories() {
  return useQuery({
    queryKey: ['activity-categories'],
    queryFn: () => api<Category[]>('/activity-categories'),
    staleTime: 300_000,
  });
}

export function useAssignees(enabled = true) {
  return useQuery({
    queryKey: ['activities', 'assignees'],
    queryFn: () => api<Assignee[]>('/activities/assignees'),
    staleTime: 300_000,
    enabled,
  });
}

export const PRIORITIES = [
  ['high', 'High'],
  ['medium', 'Medium'],
  ['low', 'Low'],
] as const;

export const REPEATS = [
  ['', 'Does not repeat'],
  ['weekly', 'Every week'],
  ['monthly', 'Every month'],
  ['quarterly', 'Every 3 months'],
  ['yearly', 'Every year'],
] as const;

/** Local calendar date helpers (YYYY-MM-DD, no time zone surprises). */
export const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
export const parse = (s: string) => {
  const [y, m, d] = s.split('-').map(Number) as [number, number, number];
  return new Date(y, m - 1, d);
};
export const addDays = (s: string, n: number) => {
  const d = parse(s);
  d.setDate(d.getDate() + n);
  return iso(d);
};
export const todayIso = () => iso(new Date());

export function repeatOf(rule?: string | null): string {
  if (!rule) return '';
  const base = rule
    .split(';')
    .filter((p) => !p.startsWith('UNTIL=') && !p.startsWith('COUNT='))
    .join(';');
  return (
    {
      'FREQ=WEEKLY': 'weekly',
      'FREQ=MONTHLY': 'monthly',
      'FREQ=MONTHLY;INTERVAL=3': 'quarterly',
      'FREQ=YEARLY': 'yearly',
    }[base] ?? ''
  );
}

export function timeLabel(a: Pick<Activity, 'all_day' | 'start_time' | 'end_time'>) {
  if (a.all_day || !a.start_time) return 'All day';
  const short = (t: string) => t.slice(0, 5);
  return a.end_time ? `${short(a.start_time)}–${short(a.end_time)}` : short(a.start_time);
}
