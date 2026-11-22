import { ArrowLeft, Download, Share2 } from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { api, ApiError } from '@/api/client';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { FormError, FormInput, FormSelect } from '@/components/forms';
import { LoadingState } from '@/components/LoadingState';
import { Modal } from '@/components/Modal';
import page from '@/components/Page.module.css';
import { useToast } from '@/components/Toast';
import { useAssignees, useCategories } from '@/features/calendar/api';
import { useAnimalOptions } from '@/features/health/Records';
import { useLocations } from '@/features/livestock/api';

import {
  cardValue,
  downloadFile,
  formatCell,
  FORMATS,
  useCatalog,
  useReport,
  type FilterDef,
  type ReportInfo,
} from './api';
import { ReportChart } from './ReportChart';
import styles from './Reports.module.css';

export default function ReportView() {
  const { key = '' } = useParams();
  const catalog = useCatalog();
  const info = catalog.data?.find((r) => r.key === key);
  if (catalog.isPending) return <LoadingState />;
  if (catalog.isError)
    return <ErrorState message={catalog.error.message} onRetry={() => void catalog.refetch()} />;
  if (!info) return <EmptyState title="Report not found" message="Choose a report from the list." />;
  return <Report info={info} />;
}

function Report({ info }: { info: ReportInfo }) {
  const [query, setQuery] = useState<Record<string, string>>({});
  const report = useReport(info.key, query);
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const [sharing, setSharing] = useState(false);
  const data = report.data;
  const set = (k: string, v: string) => setQuery((q) => ({ ...q, [k]: v }));

  const download = async (format: string) => {
    setBusy(format);
    try {
      const result = await downloadFile(
        `/reports/${info.key}/export`,
        { ...query, format },
        `${info.key}.${format}`,
      );
      if (result.kind === 'queued') toast.success(result.message);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Export failed.');
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <div className={page.header}>
        <div>
          <Link to="/reports" className={styles.meta}>
            <ArrowLeft size={14} aria-hidden="true" /> All reports
          </Link>
          <h2>{info.title}</h2>
          <p>{info.description}</p>
        </div>
        <div className={styles.actions}>
          {FORMATS.map(([f, label]) => (
            <button
              key={f}
              type="button"
              className={f === 'pdf' ? 'btn btn-primary' : 'btn btn-secondary'}
              onClick={() => void download(f)}
              disabled={busy !== null || !data}
            >
              <Download size={16} aria-hidden="true" /> {busy === f ? 'Preparing…' : label}
            </button>
          ))}
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => setSharing(true)}
            disabled={!data}
          >
            <Share2 size={16} aria-hidden="true" /> Share on WhatsApp
          </button>
        </div>
      </div>

      <section className={page.card}>
        <div className={page.cardBody}>
          <div className={styles.filters}>
            {info.uses_period && (
              <>
                <FormInput
                  label="From"
                  type="date"
                  value={query.from ?? data?.from ?? ''}
                  onChange={(e) => set('from', e.target.value)}
                />
                <FormInput
                  label="To"
                  type="date"
                  value={query.to ?? data?.to ?? ''}
                  onChange={(e) => set('to', e.target.value)}
                />
                <FormSelect
                  label="Group by"
                  value={query.group ?? data?.group ?? ''}
                  onChange={(e) => set('group', e.target.value)}
                >
                  <option value="day">Day</option>
                  <option value="week">Week</option>
                  <option value="month">Month</option>
                </FormSelect>
              </>
            )}
            {info.filters.map((f) => (
              <FilterField
                key={f.key}
                filter={f}
                value={query[f.key] ?? ''}
                onChange={(v) => set(f.key, v)}
              />
            ))}
          </div>
          {report.isError && <FormError message={report.error.message} />}
        </div>
      </section>

      {report.isPending ? (
        <LoadingState />
      ) : !data ? null : (
        <>
          <p className={styles.meta}>
            {info.uses_period ? `Period: ${data.period_label}` : 'The herd as it is today'}
            {report.isFetching ? ' · updating…' : ''}
          </p>
          <div className={styles.cards}>
            {data.summary.map((c) => (
              <div key={c.key} className={styles.card}>
                <p>{c.label}</p>
                <strong>{cardValue(c)}</strong>
              </div>
            ))}
          </div>
          {data.chart && data.chart.labels.length > 0 && <ReportChart chart={data.chart} />}
          {data.tables.map((t) => (
            <section key={t.key} className={page.card}>
              <div className={page.cardBody}>
                <h3 className={styles.tableTitle}>
                  {t.title} <span className={styles.meta}>({t.rows.length})</span>
                </h3>
              </div>
              {t.rows.length === 0 ? (
                <EmptyState title="No records" message="Nothing in this period. Try a longer period." />
              ) : (
                <div className={page.tableWrap}>
                  <table className={page.table}>
                    <thead>
                      <tr>
                        {t.columns.map((c) => (
                          <th
                            key={c.key}
                            scope="col"
                            className={c.type === 'number' || c.type === 'percent' ? styles.num : undefined}
                          >
                            {c.label}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {t.rows.slice(0, 500).map((r, i) => (
                        <tr key={i}>
                          {t.columns.map((c) => (
                            <td
                              key={c.key}
                              className={c.type === 'number' || c.type === 'percent' ? styles.num : undefined}
                            >
                              {formatCell(r[c.key], c.type)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {t.rows.length > 500 && (
                    <p className={styles.meta}>
                      Showing the first 500 of {t.rows.length} rows. Export to see them all.
                    </p>
                  )}
                </div>
              )}
            </section>
          ))}
        </>
      )}
      <ShareDialog open={sharing} onClose={() => setSharing(false)} reportKey={info.key} query={query} />
    </>
  );
}

function FilterField({
  filter,
  value,
  onChange,
}: {
  filter: FilterDef;
  value: string;
  onChange: (v: string) => void;
}) {
  const animals = useAnimalOptions();
  const locations = useLocations();
  const categories = useCategories();
  const members = useAssignees();
  const options: { value: string; label: string }[] =
    filter.type === 'select'
      ? filter.options
      : filter.type === 'animal'
        ? (animals.data ?? []).map((a) => ({ value: a.id, label: `${a.animal_id} ${a.name ?? ''}`.trim() }))
        : filter.type === 'location'
          ? (locations.data ?? []).map((l) => ({ value: l.id, label: l.name }))
          : filter.type === 'category'
            ? (categories.data ?? []).map((c) => ({ value: c.id, label: c.name }))
            : (members.data ?? []).map((m) => ({ value: m.id, label: m.name }));
  return (
    <FormSelect label={filter.label} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">All</option>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </FormSelect>
  );
}

function ShareDialog({
  open,
  onClose,
  reportKey,
  query,
}: {
  open: boolean;
  onClose: () => void;
  reportKey: string;
  query: Record<string, string>;
}) {
  const [phone, setPhone] = useState('+256 ');
  const [error, setError] = useState<string>();
  const [sending, setSending] = useState(false);
  const toast = useToast();
  const send = async () => {
    setSending(true);
    setError(undefined);
    try {
      const res = await api<{ status: string; error: string; to: string }>(`/reports/${reportKey}/share`, {
        method: 'POST',
        query,
        body: { phone },
      });
      if (res.status === 'failed') {
        setError(`Not sent: ${res.error || 'WhatsApp refused it'}.`);
      } else {
        toast.success(res.status === 'queued' ? `Queued for ${res.to}.` : `Sent to ${res.to} on WhatsApp.`);
        onClose();
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not share the report.');
    } finally {
      setSending(false);
    }
  };
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Share on WhatsApp"
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn btn-primary" onClick={() => void send()} disabled={sending}>
            {sending ? 'Sending…' : 'Send'}
          </button>
        </>
      }
    >
      <p className={styles.meta}>
        We send a short summary and a link to the PDF. The link works for 24 hours.
      </p>
      <FormError message={error} />
      <FormInput
        label="WhatsApp number"
        type="tel"
        value={phone}
        onChange={(e) => setPhone(e.target.value)}
      />
    </Modal>
  );
}
