import { useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, BellOff } from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { api, ApiError } from '@/api/client';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { LoadingState } from '@/components/LoadingState';
import page from '@/components/Page.module.css';
import { StatusBadge } from '@/components/StatusBadge';
import { useToast } from '@/components/Toast';
import { useCursorList } from '@/features/users/api';

import { CHANNEL_LABEL, markRead, timeAgo, type Notification } from './api';
import styles from './Notifications.module.css';

const FILTERS = [
  ['all', 'All'],
  ['unread', 'Unread'],
  ['urgent', 'Urgent'],
] as const;

export default function NotificationsPage() {
  const [filter, setFilter] = useState<string>('all');
  const query: Record<string, string> = filter === 'all' ? {} : { [filter]: 'true' };
  const list = useCursorList<Notification>(['notifications', 'list'], '/notifications', query);
  const queryClient = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();

  const readAll = useMutation({
    mutationFn: () => api('/notifications/read-all', { method: 'POST' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['notifications'] });
      toast.success('All notifications marked as read.');
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : 'Could not mark them as read.'),
  });

  const open = async (n: Notification) => {
    if (!n.read) {
      try {
        await markRead(n.id);
        void queryClient.invalidateQueries({ queryKey: ['notifications'] });
      } catch {
        /* opening the link still works */
      }
    }
    if (n.link) navigate(n.link);
  };

  const rows = list.data?.pages.flatMap((p) => p.results) ?? [];
  const total = list.data?.pages[0]?.count ?? 0;

  return (
    <>
      <div className={page.header}>
        <div>
          <h2>Notifications</h2>
          <p>Reminders, alerts and task updates for you on this farm.</p>
        </div>
        <div className={page.rowActions}>
          <Link to="/settings/notifications" className="btn btn-secondary">
            Notification settings
          </Link>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => readAll.mutate()}
            disabled={readAll.isPending || rows.every((r) => r.read)}
          >
            Mark all as read
          </button>
        </div>
      </div>
      <div className={page.tabs} role="tablist" aria-label="Show">
        {FILTERS.map(([v, l]) => (
          <button
            key={v}
            type="button"
            role="tab"
            aria-selected={filter === v}
            className={page.tab}
            onClick={() => setFilter(v)}
          >
            {l}
          </button>
        ))}
      </div>
      <section className={page.card}>
        {list.isLoading ? (
          <LoadingState />
        ) : list.isError ? (
          <ErrorState message="Could not load notifications." onRetry={() => void list.refetch()} />
        ) : rows.length === 0 ? (
          <EmptyState
            icon={BellOff}
            title={filter === 'all' ? 'No notifications yet' : 'Nothing here'}
            message="Reminders, health alerts and task updates will show up here."
          />
        ) : (
          <ul className={styles.list} aria-label={`${total} notifications`}>
            {rows.map((n) => (
              <li key={n.id} className={`${styles.item} ${n.read ? '' : styles.unread}`}>
                <button type="button" className={styles.open} onClick={() => void open(n)}>
                  <span className={styles.titleRow}>
                    {!n.read && <span className={styles.dot} aria-label="Unread" />}
                    {n.urgent && <AlertTriangle size={16} className={styles.urgent} aria-label="Urgent" />}
                    <strong>{n.title}</strong>
                  </span>
                  <span className={styles.message}>{n.message}</span>
                  <span className={styles.meta}>
                    {n.event_label} · {timeAgo(n.created_at)}
                  </span>
                </button>
                {n.deliveries.length > 0 && (
                  <ul className={styles.deliveries} aria-label="Delivery">
                    {n.deliveries.map((d) => (
                      <li key={d.id} title={d.error || undefined}>
                        <span className={styles.channel}>{CHANNEL_LABEL[d.channel] ?? d.channel}</span>
                        <StatusBadge status={d.status ?? 'queued'} />
                        {d.status === 'queued' && d.send_after && (
                          <span className={styles.hint}>after quiet hours</span>
                        )}
                        {d.status === 'failed' && d.error && <span className={styles.hint}>{d.error}</span>}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        )}
        {list.hasNextPage && (
          <div className={page.footer}>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void list.fetchNextPage()}
              disabled={list.isFetchingNextPage}
            >
              Load more
            </button>
          </div>
        )}
      </section>
    </>
  );
}
