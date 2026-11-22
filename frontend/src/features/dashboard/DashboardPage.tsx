import { useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  Baby,
  Bell,
  CalendarCheck,
  ClipboardList,
  HeartPulse,
  Mars,
  PawPrint,
  Venus,
  Wheat,
} from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { api } from '@/api/client';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { LoadingState } from '@/components/LoadingState';
import page from '@/components/Page.module.css';
import { StatCard } from '@/components/StatCard';
import { STATUS_MAP, StatusBadge } from '@/components/StatusBadge';
import { SERIES_COLOURS } from '@/features/reports/api';
import { useSession } from '@/features/session/SessionContext';

import styles from './Dashboard.module.css';

interface Overview {
  total: number;
  completed: number;
  pending: number;
  overdue: number;
  cancelled: number;
  completion_rate: number;
}
interface Summary {
  own: boolean;
  today: string;
  period_label: string;
  tasks_today: number;
  overdue: number;
  unread_alerts: number;
  urgent_alerts: number;
  activity_overview: Overview;
  herd?: Record<'total' | 'males' | 'females' | 'kids' | 'needing_attention' | 'pregnant', number>;
  health_status?: Record<string, number>;
  health?: Record<string, number>;
  low_stock?: number;
}
interface Charts {
  labels: string[];
  herd_size: number[];
  kids_born: number[];
  deaths: number[];
  vaccinations: number[];
  dewormings: number[];
  treatments: number[];
  activities_completed: number[];
}
interface Upcoming {
  id: string;
  title: string;
  date: string;
  status: string;
  priority: string;
  category: { name: string; colour: string } | null;
  assigned_to: string | null;
  animals: string[];
}
interface HealthItem {
  id: string;
  kind: string;
  date: string;
  animal: string;
  animal_pk: string | null;
  title: string;
  status: string;
}

const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });

export default function DashboardPage() {
  const { user, activeFarm } = useSession();
  const summary = useQuery({
    queryKey: ['dashboard', 'summary'],
    queryFn: () => api<Summary>('/dashboard/summary'),
  });
  if (summary.isPending) return <LoadingState />;
  if (summary.isError)
    return <ErrorState message={summary.error.message} onRetry={() => void summary.refetch()} />;
  const s = summary.data;
  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
  return (
    <>
      <div className={page.header}>
        <div>
          <h2>
            {greeting}, {user?.first_name}
          </h2>
          <p>
            {s.own ? 'Your tasks and alerts' : `What is happening at ${activeFarm?.farm.name ?? 'the farm'}`}{' '}
            ·{' '}
            {new Date(`${s.today}T00:00:00`).toLocaleDateString('en-GB', {
              weekday: 'long',
              day: 'numeric',
              month: 'long',
            })}
          </p>
        </div>
      </div>
      {s.own ? <AttendantDashboard s={s} /> : <StaffDashboard s={s} />}
    </>
  );
}

function AttendantDashboard({ s }: { s: Summary }) {
  return (
    <>
      <div className={styles.stats}>
        <StatCard label="My tasks today" value={s.tasks_today} icon={CalendarCheck} />
        <StatCard label="My overdue tasks" value={s.overdue} icon={AlertTriangle} />
        <StatCard
          label="Unread alerts"
          value={s.unread_alerts}
          icon={Bell}
          hint={s.urgent_alerts ? `${s.urgent_alerts} urgent` : undefined}
        />
        <StatCard
          label="Done this month"
          value={`${s.activity_overview.completed} of ${s.activity_overview.total - s.activity_overview.cancelled}`}
          icon={ClipboardList}
        />
      </div>
      <div className={styles.columns}>
        <UpcomingCard title="My next tasks" />
        <section className={page.card}>
          <div className={page.cardBody}>
            <h3>Alerts</h3>
            <p>
              {s.unread_alerts
                ? `You have ${s.unread_alerts} unread alert${s.unread_alerts === 1 ? '' : 's'}.`
                : 'No new alerts.'}
            </p>
            <Link to="/notifications" className="btn btn-secondary">
              Open notifications
            </Link>
          </div>
        </section>
      </div>
    </>
  );
}

function StaffDashboard({ s }: { s: Summary }) {
  const herd = s.herd!;
  const o = s.activity_overview;
  return (
    <>
      <div className={styles.stats}>
        <StatCard label="Total animals" value={herd.total} icon={PawPrint} />
        <StatCard label="Females" value={herd.females} icon={Venus} />
        <StatCard label="Males" value={herd.males} icon={Mars} />
        <StatCard label="Kids (under 6 months)" value={herd.kids} icon={Baby} />
        <StatCard label="Needing attention" value={herd.needing_attention} icon={HeartPulse} />
        <StatCard
          label="Tasks today"
          value={s.tasks_today}
          icon={CalendarCheck}
          hint={s.overdue ? `${s.overdue} overdue` : undefined}
        />
      </div>
      {s.low_stock ? (
        <Link to="/nutrition" className={styles.alert}>
          <Wheat size={18} aria-hidden="true" /> {s.low_stock} feed item{s.low_stock === 1 ? ' is' : 's are'}{' '}
          running low
        </Link>
      ) : null}
      <div className={styles.columns}>
        <section className={page.card} aria-labelledby="health-overview">
          <div className={page.cardBody}>
            <h3 id="health-overview">Health overview</h3>
            <ul className={styles.statusList}>
              {Object.entries(s.health_status ?? {}).map(([status, n]) => (
                <li key={status}>
                  <StatusBadge status={status} />
                  <strong>{n}</strong>
                </li>
              ))}
            </ul>
            <p className={styles.meta}>
              This month: {s.health?.vaccinations ?? 0} vaccinations · {s.health?.treatments ?? 0} treatments
              · {s.health?.kids_born ?? 0} kids born · {s.health?.deaths ?? 0} deaths
            </p>
          </div>
        </section>
        <section className={page.card} aria-labelledby="activity-overview">
          <div className={page.cardBody}>
            <h3 id="activity-overview">Activities this month</h3>
            <div className={styles.progress} role="img" aria-label={`${o.completion_rate}% completed`}>
              <span style={{ width: `${o.completion_rate}%` }} />
            </div>
            <ul className={styles.statusList}>
              <li>
                <StatusBadge status="completed" />
                <strong>{o.completed}</strong>
              </li>
              <li>
                <StatusBadge status="pending" />
                <strong>{o.pending}</strong>
              </li>
              <li>
                <StatusBadge status="overdue" />
                <strong>{o.overdue}</strong>
              </li>
            </ul>
            <p className={styles.meta}>
              {o.completion_rate}% of {o.total - o.cancelled} done · {s.period_label}
            </p>
          </div>
        </section>
      </div>
      <ChartsCard />
      <div className={styles.columns}>
        <UpcomingCard title="Coming up (next 7 days)" />
        <RecentHealthCard />
      </div>
    </>
  );
}

function ChartsCard() {
  const [range, setRange] = useState('6m');
  const charts = useQuery({
    queryKey: ['dashboard', 'charts', range],
    queryFn: () => api<Charts>('/dashboard/charts', { query: { range } }),
    placeholderData: (p) => p,
  });
  const c = charts.data;
  const rows = c?.labels.map((label, i) => ({
    label,
    Herd: c.herd_size[i],
    'Kids born': c.kids_born[i],
    Deaths: c.deaths[i],
    Vaccinations: c.vaccinations[i],
    Dewormings: c.dewormings[i],
    Treatments: c.treatments[i],
  }));
  return (
    <section className={page.card} aria-labelledby="trends">
      <div className={page.cardBody}>
        <div className={styles.cardHead}>
          <h3 id="trends">Trends</h3>
          <div className={page.tabs} role="tablist" aria-label="Range">
            {[
              ['3m', '3 months'],
              ['6m', '6 months'],
              ['12m', '12 months'],
            ].map(([v, l]) => (
              <button
                key={v}
                type="button"
                role="tab"
                aria-selected={range === v}
                className={page.tab}
                onClick={() => setRange(v!)}
              >
                {l}
              </button>
            ))}
          </div>
        </div>
        {charts.isError ? (
          <ErrorState message={charts.error.message} onRetry={() => void charts.refetch()} />
        ) : !rows ? (
          <LoadingState />
        ) : (
          <div className={styles.chartGrid}>
            <figure className={styles.figure}>
              <figcaption>Herd size</figcaption>
              <div className={styles.chartBox}>
                <ResponsiveContainer>
                  <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="label" tick={{ fontSize: 12 }} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                    <Tooltip />
                    <Line type="monotone" dataKey="Herd" stroke={SERIES_COLOURS[0]} strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </figure>
            <figure className={styles.figure}>
              <figcaption>Births and deaths</figcaption>
              <div className={styles.chartBox}>
                <ResponsiveContainer>
                  <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="label" tick={{ fontSize: 12 }} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                    <Tooltip />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="Kids born" fill={SERIES_COLOURS[0]} radius={[4, 4, 0, 0]} />
                    <Bar dataKey="Deaths" fill={SERIES_COLOURS[4]} radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </figure>
            <figure className={styles.figure}>
              <figcaption>Health work</figcaption>
              <div className={styles.chartBox}>
                <ResponsiveContainer>
                  <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="label" tick={{ fontSize: 12 }} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                    <Tooltip />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="Vaccinations" stackId="h" fill={SERIES_COLOURS[0]} />
                    <Bar dataKey="Dewormings" stackId="h" fill={SERIES_COLOURS[3]} />
                    <Bar dataKey="Treatments" stackId="h" fill={SERIES_COLOURS[1]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </figure>
          </div>
        )}
      </div>
    </section>
  );
}

function UpcomingCard({ title }: { title: string }) {
  const list = useQuery({
    queryKey: ['dashboard', 'upcoming'],
    queryFn: () => api<Upcoming[]>('/dashboard/upcoming'),
  });
  return (
    <section className={page.card} aria-label={title}>
      <div className={page.cardBody}>
        <div className={styles.cardHead}>
          <h3>{title}</h3>
          <Link to="/activities">All activities</Link>
        </div>
        {list.isPending ? (
          <LoadingState />
        ) : list.isError ? (
          <ErrorState message={list.error.message} onRetry={() => void list.refetch()} />
        ) : list.data.length === 0 ? (
          <EmptyState title="Nothing coming up" message="No open tasks in the next 7 days." />
        ) : (
          <ul className={styles.list}>
            {list.data.map((a) => (
              <li key={a.id}>
                <span
                  className={styles.dot}
                  style={{ background: a.category?.colour ?? '#9e9e9e' }}
                  aria-hidden="true"
                />
                <Link to={`/activities?activity=${a.id}`} className={styles.itemTitle}>
                  {a.title}
                </Link>
                <span className={styles.meta}>
                  {day(a.date)}
                  {a.assigned_to ? ` · ${a.assigned_to}` : ''}
                </span>
                <StatusBadge status={a.status} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function RecentHealthCard() {
  const list = useQuery({
    queryKey: ['dashboard', 'recent-health'],
    queryFn: () => api<HealthItem[]>('/dashboard/recent-health'),
  });
  return (
    <section className={page.card} aria-label="Recent health events">
      <div className={page.cardBody}>
        <div className={styles.cardHead}>
          <h3>Recent health events</h3>
          <Link to="/health">Animal health</Link>
        </div>
        {list.isPending ? (
          <LoadingState />
        ) : list.isError ? (
          <ErrorState message={list.error.message} onRetry={() => void list.refetch()} />
        ) : list.data.length === 0 ? (
          <EmptyState title="No recent records" message="Health records from the last 60 days appear here." />
        ) : (
          <ul className={styles.list}>
            {list.data.map((h) => (
              <li key={`${h.kind}-${h.id}`}>
                {h.animal_pk ? (
                  <Link to={`/livestock/${h.animal_pk}`} className={styles.itemTitle}>
                    {h.animal}
                  </Link>
                ) : (
                  <span className={styles.itemTitle}>{h.animal}</span>
                )}
                <span className={styles.meta}>
                  {day(h.date)} · {h.title}
                </span>
                {STATUS_MAP[h.status] && <StatusBadge status={h.status} />}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
