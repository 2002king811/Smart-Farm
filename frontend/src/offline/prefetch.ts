import { api } from '@/api/client';

/** Saves what a person needs in the field, so it is there when the connection drops:
 * today's and upcoming tasks, the animal list and the calendar for the next 14 days. */
export async function prefetchForOffline() {
  if (typeof navigator !== 'undefined' && !navigator.onLine) return;
  const today = new Date();
  const iso = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const in14 = new Date(today);
  in14.setDate(today.getDate() + 14);
  const requests = [
    api('/dashboard/summary'),
    api('/dashboard/upcoming'),
    api('/animals', { query: { page_size: 200 } }),
    api('/activities', { query: { from: iso(today), to: iso(in14), page_size: 200 } }),
    api('/activities', { query: { status: 'overdue', page_size: 200 } }),
    api('/activities/calendar', { query: { view: 'agenda', date: iso(today) } }),
    api('/activity-categories'),
    api('/locations'),
    api('/feed-items'),
  ];
  await Promise.allSettled(requests);
}
