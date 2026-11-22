import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { api, ApiError } from '@/api/client';
import { Checkbox, FormError, FormInput, FormSelect } from '@/components/forms';
import { ErrorState } from '@/components/ErrorState';
import { LoadingState } from '@/components/LoadingState';
import page from '@/components/Page.module.css';
import { useToast } from '@/components/Toast';
import { useSession } from '@/features/session/SessionContext';

import {
  CHANNELS,
  useContacts,
  usePreferences,
  useUsage,
  type Contact,
  type Notification,
  type Preferences,
} from './api';
import styles from './Notifications.module.css';

/** Settings → Notifications: which alerts reach you where, quiet hours, contacts, test, usage. */
export default function NotificationSettingsSection() {
  const prefs = usePreferences();
  const { role } = useSession();
  if (prefs.isPending) return <LoadingState />;
  if (prefs.isError) return <ErrorState message={prefs.error.message} onRetry={() => void prefs.refetch()} />;
  return (
    <>
      <PreferencesForm initial={prefs.data} />
      <ContactsCard />
      <TestCard />
      {role === 'administrator' && <UsageCard />}
    </>
  );
}

const hhmm = (t?: string) => (t ?? '').slice(0, 5);

function PreferencesForm({ initial }: { initial: Preferences }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [matrix, setMatrix] = useState(initial.matrix);
  const [settings, setSettings] = useState({
    ...initial.settings,
    quiet_start: hhmm(initial.settings.quiet_start),
    quiet_end: hhmm(initial.settings.quiet_end),
    digest_time: hhmm(initial.settings.digest_time),
  });
  const [error, setError] = useState<string>();
  const save = useMutation({
    mutationFn: () =>
      api<Preferences>('/notification-preferences', {
        method: 'PUT',
        body: { matrix: matrix.map(({ event_type, channels }) => ({ event_type, channels })), settings },
      }),
    onSuccess: (saved) => {
      qc.setQueryData(['notifications', 'preferences'], saved);
      setError(undefined);
      toast.success('Notification settings saved.');
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : 'Could not save your settings.'),
  });
  const toggle = (event: string, channel: string) =>
    setMatrix((rows) =>
      rows.map((r) =>
        r.event_type === event ? { ...r, channels: { ...r.channels, [channel]: !r.channels[channel] } } : r,
      ),
    );

  return (
    <form
      className={page.card}
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
      noValidate
    >
      <div className={page.cardBody}>
        <h3>What you get, and where</h3>
        <p className={page.note}>
          Tick the channels for each kind of alert. This applies to you on this farm.
        </p>
        <FormError message={error} />
        <div className={page.tableWrap}>
          <table className={styles.matrix}>
            <thead>
              <tr>
                <th scope="col">Alert</th>
                {CHANNELS.map(([c, l]) => (
                  <th key={c} scope="col">
                    {l}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {matrix.map((row) => (
                <tr key={row.event_type}>
                  <th scope="row">{row.label}</th>
                  {CHANNELS.map(([c, l]) => (
                    <td key={c}>
                      <input
                        type="checkbox"
                        aria-label={`${row.label}: ${l}`}
                        checked={Boolean(row.channels[c])}
                        onChange={() => toggle(row.event_type, c)}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <h3>Quiet hours and summary</h3>
        <Checkbox
          label="Hold SMS and WhatsApp during quiet hours (urgent health alerts still go out)"
          checked={settings.quiet_hours_enabled ?? true}
          onChange={(e) => setSettings({ ...settings, quiet_hours_enabled: e.target.checked })}
        />
        <div className={styles.times}>
          <FormInput
            label="Quiet from"
            type="time"
            value={settings.quiet_start}
            disabled={!settings.quiet_hours_enabled}
            onChange={(e) => setSettings({ ...settings, quiet_start: e.target.value })}
          />
          <FormInput
            label="Quiet until"
            type="time"
            value={settings.quiet_end}
            disabled={!settings.quiet_hours_enabled}
            onChange={(e) => setSettings({ ...settings, quiet_end: e.target.value })}
          />
          <FormInput
            label="Daily summary at"
            type="time"
            value={settings.digest_time}
            onChange={(e) => setSettings({ ...settings, digest_time: e.target.value })}
          />
          <FormSelect
            label="Message language"
            value={settings.language}
            onChange={(e) => setSettings({ ...settings, language: e.target.value as 'en' | 'sw' })}
          >
            <option value="en">English</option>
            <option value="sw">Kiswahili</option>
          </FormSelect>
        </div>
      </div>
      <div className={page.formActions}>
        <button type="submit" className="btn btn-primary" disabled={save.isPending}>
          {save.isPending ? 'Saving…' : 'Save notification settings'}
        </button>
      </div>
    </form>
  );
}

function ContactsCard() {
  const contacts = useContacts();
  const qc = useQueryClient();
  const toast = useToast();
  const change = useMutation({
    mutationFn: ({ channel, opted_in }: { channel: string; opted_in: boolean }) =>
      api<Contact>(`/channel-contacts/${channel}`, { method: 'PATCH', body: { opted_in } }),
    onSuccess: (saved) => {
      void qc.invalidateQueries({ queryKey: ['notifications', 'contacts'] });
      toast.success(
        saved.opted_in ? `${saved.channel_label} switched on.` : `${saved.channel_label} switched off.`,
      );
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : 'Could not change it.'),
  });

  return (
    <section className={page.card}>
      <div className={page.cardBody}>
        <h3>Where messages go</h3>
        <p className={page.note}>
          Your mobile number and email come from My profile. Confirm them there to receive SMS, WhatsApp and
          email.
        </p>
        {contacts.isPending ? (
          <LoadingState />
        ) : contacts.isError ? (
          <ErrorState message={contacts.error.message} onRetry={() => void contacts.refetch()} />
        ) : contacts.data.length === 0 ? (
          <p>Add a mobile number or email address in My profile first.</p>
        ) : (
          <div className={styles.contacts}>
            {contacts.data.map((c) => (
              <div key={c.channel} className={styles.contact}>
                <div>
                  <strong>{c.channel_label}</strong> · {c.address}
                  <div className={page.sub}>{c.problem || 'Messages can be delivered.'}</div>
                </div>
                {c.verified &&
                  (c.opted_in ? (
                    <button
                      type="button"
                      className="btn btn-secondary"
                      disabled={change.isPending}
                      onClick={() => change.mutate({ channel: c.channel, opted_in: false })}
                    >
                      Switch off {c.channel_label}
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="btn btn-primary"
                      disabled={change.isPending}
                      onClick={() => change.mutate({ channel: c.channel, opted_in: true })}
                    >
                      {c.channel === 'whatsapp'
                        ? 'Yes, send me WhatsApp messages'
                        : `Switch on ${c.channel_label}`}
                    </button>
                  ))}
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function TestCard() {
  const [channel, setChannel] = useState('in_app');
  const [result, setResult] = useState<string>();
  const qc = useQueryClient();
  const toast = useToast();
  const send = useMutation({
    mutationFn: () => api<Notification>('/notifications/test', { method: 'POST', body: { channel } }),
    onSuccess: (n) => {
      void qc.invalidateQueries({ queryKey: ['notifications'] });
      const d = n.deliveries[0];
      if (!d) {
        setResult('Sent to your notifications in the app.');
        toast.success('Test notification sent.');
      } else if (d.status === 'failed') {
        setResult(`Not sent: ${d.error || 'the provider refused it'}.`);
      } else {
        setResult(d.status === 'queued' ? 'Queued – it will be sent shortly.' : `Sent by ${channel}.`);
        if (d.status !== 'queued') toast.success('Test message sent.');
      }
    },
    onError: (e) => setResult(e instanceof ApiError ? e.message : 'Could not send the test.'),
  });
  return (
    <section className={page.card}>
      <div className={page.cardBody}>
        <h3>Send a test</h3>
        <div className={styles.times}>
          <FormSelect label="Channel" value={channel} onChange={(e) => setChannel(e.target.value)}>
            {CHANNELS.map(([c, l]) => (
              <option key={c} value={c}>
                {l}
              </option>
            ))}
          </FormSelect>
        </div>
        {result && (
          <p role="status" className={page.note}>
            {result}
          </p>
        )}
      </div>
      <div className={page.formActions}>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => send.mutate()}
          disabled={send.isPending}
        >
          {send.isPending ? 'Sending…' : 'Send test message'}
        </button>
      </div>
    </section>
  );
}

function UsageCard() {
  const usage = useUsage(true);
  return (
    <section className={page.card}>
      <div className={page.cardBody}>
        <h3>Messages this month</h3>
        {usage.isPending ? (
          <LoadingState />
        ) : usage.isError ? (
          <ErrorState message={usage.error.message} onRetry={() => void usage.refetch()} />
        ) : (
          <div className={styles.contacts}>
            {usage.data.map((u) => {
              const pct = u.allowance ? Math.min(100, Math.round((u.used * 100) / u.allowance)) : 0;
              return (
                <div key={u.channel}>
                  <strong>{u.label}</strong>:{' '}
                  {u.allowance ? `${u.used} of ${u.allowance} (${pct}%)` : `${u.used} sent`}
                  {u.allowance ? (
                    <div className={styles.meter} aria-hidden="true">
                      <span className={pct >= 80 ? styles.warn : ''} style={{ width: `${pct}%` }} />
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
