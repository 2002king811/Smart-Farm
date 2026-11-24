import { useQuery, useQueryClient } from '@tanstack/react-query';
import { CalendarDays, ChevronLeft, ChevronRight, Plus } from 'lucide-react';
import { useMemo, useState } from 'react';

import { api, ApiError } from '@/api/client';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { FormSelect } from '@/components/forms';
import { LoadingState } from '@/components/LoadingState';
import page from '@/components/Page.module.css';
import { StatusBadge } from '@/components/StatusBadge';
import { useToast } from '@/components/Toast';
import { useSession } from '@/features/session/SessionContext';
import { can } from '@/routes/permissions';

import { ActivityDetail, ActivityForm } from './ActivityDialogs';
import { addDays, iso, parse, timeLabel, todayIso, useCategories, type Activity } from './api';
import cal from './Calendar.module.css';

type View = 'month' | 'week' | 'day' | 'agenda';
const VIEWS: [View, string][] = [
  ['month', 'Month'],
  ['week', 'Week'],
  ['day', 'Day'],
  ['agenda', 'Agenda'],
];
const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];

interface CalendarResponse {
  view: View;
  start: string;
  end: string;
  activities: Activity[];
}
interface Template {
  key: string;
  name: string;
  description: string;
  count: number;
  applied: number;
}

function shift(view: View, date: string, dir: 1 | -1): string {
  const d = parse(date);
  if (view === 'month') {
    d.setDate(1);
    d.setMonth(d.getMonth() + dir);
    return iso(d);
  }
  return addDays(date, dir * (view === 'week' ? 7 : view === 'agenda' ? 30 : 1));
}

function titleFor(view: View, date: string, start?: string, end?: string): string {
  const d = parse(date);
  if (view === 'month') return `${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
  if (view === 'day')
    return `${DOW[(d.getDay() + 6) % 7]} ${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
  if (!start || !end) return '';
  const s = parse(start);
  const e = parse(end);
  return `${s.getDate()} ${MONTHS[s.getMonth()]!.slice(0, 3)} – ${e.getDate()} ${MONTHS[e.getMonth()]!.slice(0, 3)} ${e.getFullYear()}`;
}

export default function CalendarPage() {
  const { activeFarm, role } = useSession();
  const narrow = typeof window !== 'undefined' && window.matchMedia?.('(max-width: 720px)').matches;
  const [view, setView] = useState<View>(
    narrow ? 'agenda' : ((activeFarm?.farm.default_calendar_view as View) ?? 'month'),
  );
  const [date, setDate] = useState(todayIso());
  const [category, setCategory] = useState('');
  const [openId, setOpenId] = useState<string | null>(null);
  const [creating, setCreating] = useState<string | null>(null);
  const categories = useCategories();
  const data = useQuery({
    queryKey: ['calendar', view, date, category],
    queryFn: () => api<CalendarResponse>('/activities/calendar', { query: { view, date, category } }),
  });
  const byDay = useMemo(() => {
    const m = new Map<string, Activity[]>();
    for (const a of data.data?.activities ?? []) m.set(a.date, [...(m.get(a.date) ?? []), a]);
    return m;
  }, [data.data]);
  const canCreate = can(role, 'activities', 'create');

  const open = (a: Activity) => setOpenId(a.id);
  const goDay = (d: string) => {
    setDate(d);
    setView('day');
  };

  return (
    <>
      <div className={page.header}>
        <div>
          <h2>Health calendar</h2>
          <p>Planned health work, reminders from health records, and farm tasks.</p>
        </div>
        {canCreate && (
          <button type="button" className="btn btn-primary" onClick={() => setCreating(date)}>
            <Plus size={18} aria-hidden="true" /> New activity
          </button>
        )}
      </div>
      {can(role, 'calendar', 'create') && <TemplateBanner />}
      <section className={page.card}>
        <div className={cal.toolbar}>
          <div className={cal.nav}>
            <button
              type="button"
              className={cal.iconBtn}
              aria-label="Previous"
              onClick={() => setDate(shift(view, date, -1))}
            >
              <ChevronLeft size={20} aria-hidden="true" />
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => setDate(todayIso())}>
              Today
            </button>
            <button
              type="button"
              className={cal.iconBtn}
              aria-label="Next"
              onClick={() => setDate(shift(view, date, 1))}
            >
              <ChevronRight size={20} aria-hidden="true" />
            </button>
          </div>
          <h3 className={cal.title} aria-live="polite">
            {titleFor(view, date, data.data?.start, data.data?.end)}
          </h3>
          <div style={{ minWidth: 180 }}>
            <FormSelect label="Category" value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">All categories</option>
              {categories.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </FormSelect>
          </div>
          <div className={cal.views} role="group" aria-label="Calendar view">
            {VIEWS.map(([v, l]) => (
              <button key={v} type="button" aria-pressed={view === v} onClick={() => setView(v)}>
                {l}
              </button>
            ))}
          </div>
        </div>
        {data.isPending ? (
          <div className={page.cardBody}>
            <LoadingState />
          </div>
        ) : data.isError ? (
          <div className={page.cardBody}>
            <ErrorState message={data.error.message} onRetry={() => void data.refetch()} />
          </div>
        ) : view === 'month' ? (
          <MonthGrid
            start={data.data.start}
            end={data.data.end}
            focus={date}
            byDay={byDay}
            onOpen={open}
            onDay={goDay}
          />
        ) : view === 'week' ? (
          <WeekGrid start={data.data.start} byDay={byDay} onOpen={open} onDay={goDay} />
        ) : (
          <AgendaList
            activities={data.data.activities}
            showDates={view === 'agenda'}
            onOpen={open}
            empty={view === 'day' ? 'Nothing planned for this day.' : 'Nothing planned in the next 30 days.'}
          />
        )}
        <div className={cal.legend} aria-label="Category colours">
          {categories.data?.map((c) => (
            <span key={c.id}>
              <span className={cal.swatch} style={{ background: c.colour }} aria-hidden="true" /> {c.name}
            </span>
          ))}
        </div>
      </section>
      {openId && <ActivityDetail id={openId} onClose={() => setOpenId(null)} />}
      {creating && <ActivityForm defaultDate={creating} onClose={() => setCreating(null)} />}
    </>
  );
}

function Chip({ a, onOpen }: { a: Activity; onOpen: (a: Activity) => void }) {
  const cls = `${cal.chip} ${a.status === 'completed' || a.status === 'cancelled' ? cal.chipDone : ''} ${a.status === 'overdue' ? cal.chipOverdue : ''}`;
  return (
    <button
      type="button"
      className={cls}
      style={{ borderLeftColor: a.category?.colour ?? 'var(--color-primary-400)' }}
      onClick={() => onOpen(a)}
      title={`${a.title} (${a.status})`}
      aria-label={`${a.title}, ${a.status?.replace('_', ' ')}`}
    >
      {!a.all_day && a.start_time ? `${a.start_time.slice(0, 5)} ` : ''}
      {a.title}
    </button>
  );
}

function MonthGrid({
  start,
  end,
  focus,
  byDay,
  onOpen,
  onDay,
}: {
  start: string;
  end: string;
  focus: string;
  byDay: Map<string, Activity[]>;
  onOpen: (a: Activity) => void;
  onDay: (d: string) => void;
}) {
  const days: string[] = [];
  for (let d = start; d <= end; d = addDays(d, 1)) days.push(d);
  const month = parse(focus).getMonth();
  const today = todayIso();
  return (
    <div className={cal.month} role="grid" aria-label="Month">
      <div role="row" className={cal.row}>
        {DOW.map((d) => (
          <div key={d} className={cal.dow} role="columnheader">
            {d}
          </div>
        ))}
      </div>
      {Array.from({ length: Math.ceil(days.length / 7) }, (_, w) => days.slice(w * 7, w * 7 + 7)).map(
        (week) => (
          <div role="row" key={week[0]} className={cal.row}>
            {week.map((d) => {
              const items = byDay.get(d) ?? [];
              const other = parse(d).getMonth() !== month;
              return (
                <div
                  key={d}
                  role="gridcell"
                  className={`${cal.cell} ${other ? cal.cellOther : ''} ${d === today ? cal.today : ''}`}
                >
                  <button
                    type="button"
                    className={cal.dayNum}
                    onClick={() => onDay(d)}
                    aria-label={`${d}, ${items.length} activities`}
                  >
                    {parse(d).getDate()}
                  </button>
                  {items.slice(0, 3).map((a) => (
                    <Chip key={a.id} a={a} onOpen={onOpen} />
                  ))}
                  {items.length > 3 && (
                    <button type="button" className={cal.more} onClick={() => onDay(d)}>
                      +{items.length - 3} more
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        ),
      )}
    </div>
  );
}

function WeekGrid({
  start,
  byDay,
  onOpen,
  onDay,
}: {
  start: string;
  byDay: Map<string, Activity[]>;
  onOpen: (a: Activity) => void;
  onDay: (d: string) => void;
}) {
  const days = Array.from({ length: 7 }, (_, i) => addDays(start, i));
  const today = todayIso();
  return (
    <div className={cal.week}>
      {days.map((d, i) => (
        <div key={d} className={`${cal.weekCol} ${d === today ? cal.today : ''}`}>
          <div className={cal.weekHead}>
            <button type="button" className={cal.dayNum} onClick={() => onDay(d)}>
              {DOW[i]} {parse(d).getDate()}
            </button>
          </div>
          {(byDay.get(d) ?? []).map((a) => (
            <Chip key={a.id} a={a} onOpen={onOpen} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function AgendaList({
  activities,
  showDates,
  onOpen,
  empty,
}: {
  activities: Activity[];
  showDates: boolean;
  onOpen: (a: Activity) => void;
  empty: string;
}) {
  if (!activities.length) return <EmptyState icon={CalendarDays} title="Nothing here" message={empty} />;
  let last = '';
  return (
    <ul className={cal.list}>
      {activities.map((a) => {
        const heading = showDates && a.date !== last;
        last = a.date;
        const d = parse(a.date);
        return (
          <li key={a.id}>
            {heading && (
              <div className={cal.agendaDay}>
                {DOW[(d.getDay() + 6) % 7]} {d.getDate()} {MONTHS[d.getMonth()]}
                {a.date === todayIso() ? ' · Today' : ''}
              </div>
            )}
            <button type="button" className={cal.item} onClick={() => onOpen(a)}>
              <span className={cal.time}>{timeLabel(a)}</span>
              <span
                className={cal.swatch}
                style={{ background: a.category?.colour ?? 'var(--color-primary-400)' }}
                aria-hidden="true"
              />
              <span className={cal.itemMain}>
                <strong>{a.title}</strong>
                <span className={page.sub}>
                  {[a.category?.name, a.assigned_to?.name, a.animals.map((x) => x.animal_id).join(', ')]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              </span>
              <StatusBadge status={a.status} />
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function TemplateBanner() {
  const qc = useQueryClient();
  const toast = useToast();
  const templates = useQuery({
    queryKey: ['calendar', 'templates'],
    queryFn: () => api<Template[]>('/activity-templates'),
  });
  const [busy, setBusy] = useState(false);
  const t = templates.data?.[0];
  if (!t || t.applied >= t.count) return null;
  const apply = async () => {
    setBusy(true);
    try {
      const res = await api<{ created: number }>(`/activity-templates/${t.key}/apply`, { method: 'POST' });
      await qc.invalidateQueries({ queryKey: ['calendar'] });
      await qc.invalidateQueries({ queryKey: ['activities'] });
      toast.success(`${res.created} planned activities added to the calendar.`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not add the plan.');
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className={cal.template}>
      <span>
        <strong>{t.name}</strong>: {t.description}
      </span>
      <button type="button" className="btn btn-primary" onClick={() => void apply()} disabled={busy}>
        {busy ? 'Adding…' : `Add the ${t.count} activities`}
      </button>
    </div>
  );
}
