import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, CalendarClock, HeartPulse, Pill, ShieldAlert, Stethoscope } from 'lucide-react';
import { NavLink, Navigate, Route, Routes } from 'react-router-dom';

import { api } from '@/api/client';
import page from '@/components/Page.module.css';
import { StatCard } from '@/components/StatCard';
import styles from '@/features/livestock/Livestock.module.css';

import { recordType, RECORD_TYPES } from './config';
import { RecordList } from './Records';

interface Summary {
  status_counts: Record<string, number>;
  ongoing_treatments: number;
  under_withdrawal: number;
  vaccinations_due_30_days: number;
  overdue_health_activities: number;
  observations_7_days: number;
}

export default function HealthPage() {
  const summary = useQuery({
    queryKey: ['health', 'summary'],
    queryFn: () => api<Summary>('/health/summary'),
  });
  const s = summary.data;
  const n = (v?: number) => (v === undefined ? '—' : v);
  return (
    <>
      <div className={page.header}>
        <div>
          <h2>Animal health</h2>
          <p>
            Vaccinations, deworming, treatments, disease monitoring, vet visits, inspections and parasite
            control.
          </p>
        </div>
      </div>
      <div className={styles.stats}>
        <StatCard
          label="Healthy"
          value={n(s?.status_counts.healthy ?? (s ? 0 : undefined))}
          icon={HeartPulse}
        />
        <StatCard label="Under treatment" value={n(s?.ongoing_treatments)} icon={Pill} />
        <StatCard
          label="Sick or quarantined"
          value={s ? (s.status_counts.sick ?? 0) + (s.status_counts.quarantined ?? 0) : '—'}
          icon={AlertTriangle}
        />
        <StatCard
          label="Vaccinations due (30 days)"
          value={n(s?.vaccinations_due_30_days)}
          icon={CalendarClock}
        />
        <StatCard label="Overdue health tasks" value={n(s?.overdue_health_activities)} icon={ShieldAlert} />
        <StatCard
          label="Under withdrawal"
          value={n(s?.under_withdrawal)}
          icon={Stethoscope}
          hint="Do not sell or milk"
        />
      </div>
      <nav className={page.tabs} aria-label="Health records">
        {RECORD_TYPES.map((t) => (
          <NavLink key={t.key} to={`/health/${t.key}`} className={page.tab}>
            {t.title}
          </NavLink>
        ))}
      </nav>
      <Routes>
        <Route index element={<Navigate to="vaccinations" replace />} />
        {RECORD_TYPES.map((t) => (
          <Route key={t.key} path={t.key} element={<RecordList key={t.key} type={recordType(t.key)} />} />
        ))}
        <Route path="*" element={<Navigate to="/health" replace />} />
      </Routes>
    </>
  );
}
