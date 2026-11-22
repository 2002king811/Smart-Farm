import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Trash2 } from 'lucide-react';
import { useState } from 'react';
import { Link, Route, Routes } from 'react-router-dom';

import { api, ApiError } from '@/api/client';
import { ErrorState } from '@/components/ErrorState';
import { FormError, FormInput, FormSelect } from '@/components/forms';
import { LoadingState } from '@/components/LoadingState';
import page from '@/components/Page.module.css';
import { StatusBadge } from '@/components/StatusBadge';
import { useToast } from '@/components/Toast';
import { useSession } from '@/features/session/SessionContext';

import { useCatalog, type Schedule } from './api';
import styles from './Reports.module.css';
import ReportView from './ReportView';

export default function ReportsPage() {
  return (
    <Routes>
      <Route index element={<ReportIndex />} />
      <Route path=":key" element={<ReportView />} />
    </Routes>
  );
}

function ReportIndex() {
  const catalog = useCatalog();
  const { role } = useSession();
  const sections = [...new Set((catalog.data ?? []).map((r) => r.section))];
  return (
    <>
      <div className={page.header}>
        <div>
          <h2>Reports</h2>
          <p>Choose a report to preview it, then download it as PDF, Excel or CSV.</p>
        </div>
      </div>
      {catalog.isPending ? (
        <LoadingState />
      ) : catalog.isError ? (
        <ErrorState message={catalog.error.message} onRetry={() => void catalog.refetch()} />
      ) : (
        <div className={styles.sections}>
          {sections.map((section) => (
            <section key={section} className={styles.section}>
              <h3>{section}</h3>
              <div className={styles.grid}>
                {catalog.data
                  .filter((r) => r.section === section)
                  .map((r) => (
                    <Link key={r.key} to={`/reports/${r.key}`} className={styles.reportCard}>
                      <strong>{r.title}</strong>
                      <span>{r.description}</span>
                    </Link>
                  ))}
              </div>
            </section>
          ))}
          <RecentRuns />
          {role === 'administrator' && <Schedules />}
        </div>
      )}
    </>
  );
}

interface Run {
  id: string;
  title: string;
  format: string;
  status: string;
  date_from: string;
  date_to: string;
  created_at: string;
  download_url: string | null;
  error: string;
}

function RecentRuns() {
  const runs = useQuery({
    queryKey: ['reports', 'runs'],
    queryFn: () =>
      api<{ results: Run[] }>('/report-runs', { query: { page_size: 10 } }).then((r) => r.results),
    refetchInterval: (q) =>
      q.state.data?.some((r) => r.status === 'queued' || r.status === 'running') ? 5_000 : false,
  });
  const background = (runs.data ?? []).filter((r) => r.download_url || r.status !== 'done');
  if (!background.length) return null;
  return (
    <section className={page.card}>
      <div className={page.cardBody}>
        <h3>Large reports</h3>
        <p className={page.note}>
          Big exports are prepared in the background. Download links work for 24 hours.
        </p>
      </div>
      <div className={page.tableWrap}>
        <table className={page.table}>
          <thead>
            <tr>
              <th scope="col">Report</th>
              <th scope="col">Period</th>
              <th scope="col">Format</th>
              <th scope="col">Status</th>
              <th scope="col">
                <span className="visually-hidden">Download</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {background.map((r) => (
              <tr key={r.id}>
                <td>{r.title}</td>
                <td>
                  {r.date_from} – {r.date_to}
                </td>
                <td>{r.format.toUpperCase()}</td>
                <td>
                  <StatusBadge
                    status={r.status === 'done' ? 'completed' : r.status === 'failed' ? 'failed' : 'queued'}
                  />
                </td>
                <td>
                  {r.download_url ? (
                    <a href={r.download_url} className="btn btn-secondary">
                      Download
                    </a>
                  ) : (
                    r.error
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

const SCHEDULE_TYPES = [
  ['monthly_activities', 'Monthly Farm Activities – 1st of each month'],
  ['quarterly_health', 'Quarterly Health Report – 1st of each quarter'],
] as const;

function Schedules() {
  const qc = useQueryClient();
  const toast = useToast();
  const list = useQuery({
    queryKey: ['reports', 'schedules'],
    queryFn: () => api<Schedule[]>('/report-schedules'),
  });
  const [type, setType] = useState<string>(SCHEDULE_TYPES[0][0]);
  const [emails, setEmails] = useState('');
  const [error, setError] = useState<string>();
  const create = useMutation({
    mutationFn: () =>
      api<Schedule>('/report-schedules', {
        method: 'POST',
        body: { report_type: type, recipients: emails.split(/[\s,;]+/).filter(Boolean) },
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['reports', 'schedules'] });
      setEmails('');
      setError(undefined);
      toast.success('Report scheduled.');
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : 'Could not save the schedule.'),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/report-schedules/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['reports', 'schedules'] });
      toast.success('Schedule removed.');
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : 'Could not remove it.'),
  });
  return (
    <section className={page.card}>
      <div className={page.cardBody}>
        <h3>Scheduled reports</h3>
        <p className={page.note}>
          Emailed as a PDF to the people you choose, for example the owner and the vet.
        </p>
        {list.isPending ? (
          <LoadingState />
        ) : list.isError ? (
          <ErrorState message={list.error.message} onRetry={() => void list.refetch()} />
        ) : (
          list.data.length > 0 && (
            <ul className={styles.sections} aria-label="Schedules">
              {list.data.map((s) => (
                <li key={s.id} className={styles.card}>
                  <strong>{s.report_label}</strong>
                  <p>To: {s.recipients.join(', ')}</p>
                  <p>
                    {s.last_sent_at
                      ? `Last sent ${new Date(s.last_sent_at).toLocaleDateString('en-GB')}`
                      : 'Not sent yet'}
                  </p>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => remove.mutate(s.id)}
                    disabled={remove.isPending}
                    aria-label={`Remove ${s.report_label}`}
                  >
                    <Trash2 size={16} aria-hidden="true" /> Remove
                  </button>
                </li>
              ))}
            </ul>
          )
        )}
        <form
          className={styles.filters}
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <FormSelect label="Report" value={type} onChange={(e) => setType(e.target.value)}>
            {SCHEDULE_TYPES.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </FormSelect>
          <FormInput
            label="Send to (email addresses)"
            value={emails}
            placeholder="owner@example.com, vet@example.com"
            onChange={(e) => setEmails(e.target.value)}
          />
          <button type="submit" className="btn btn-primary" disabled={create.isPending || !emails.trim()}>
            Schedule
          </button>
        </form>
        <FormError message={error} />
      </div>
    </section>
  );
}
