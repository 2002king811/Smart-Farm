import { useQueryClient } from '@tanstack/react-query';
import { ClipboardList, Plus } from 'lucide-react';
import { useDeferredValue, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';

import { api, ApiError, isQueued } from '@/api/client';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { FormInput, FormSelect } from '@/components/forms';
import { LoadingState } from '@/components/LoadingState';
import page from '@/components/Page.module.css';
import { StatusBadge } from '@/components/StatusBadge';
import { useToast } from '@/components/Toast';
import { formatDate } from '@/features/livestock/format';
import { useSession } from '@/features/session/SessionContext';
import { useCursorList } from '@/features/users/api';
import { can, scopeOf } from '@/routes/permissions';

import { ActivityDetail, ActivityForm, CategoryChip } from './ActivityDialogs';
import { PRIORITIES, timeLabel, todayIso, useAssignees, useCategories, type Activity } from './api';
import cal from './Calendar.module.css';

const STATUS_TABS = [
  ['pending,in_progress,overdue', 'open'],
  ['overdue', 'overdue'],
  ['completed', 'completed'],
  ['cancelled', 'cancelled'],
  ['', 'all'],
] as const;

export default function ActivitiesPage() {
  const { role, activeFarm } = useSession();
  const { t } = useTranslation();
  const fmt = activeFarm?.farm.date_format ?? 'DD MMM YYYY';
  const own = scopeOf(role, 'activities') === 'own';
  const toast = useToast();
  const qc = useQueryClient();
  const [status, setStatus] = useState<string>(STATUS_TABS[0][0]);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [assignee, setAssignee] = useState('');
  const [priority, setPriority] = useState('');
  const [params, setParams] = useSearchParams();
  // Links from notifications open the activity: /activities?activity=<id>
  const [openId, setOpenIdState] = useState<string | null>(params.get('activity'));
  const setOpenId = (id: string | null) => {
    setOpenIdState(id);
    if (!id && params.has('activity')) {
      params.delete('activity');
      setParams(params, { replace: true });
    }
  };
  const linked = params.get('activity');
  useEffect(() => {
    if (linked) setOpenIdState(linked);
  }, [linked]);
  const [creating, setCreating] = useState(false);
  const q = useDeferredValue(search);
  const categories = useCategories();
  const assignees = useAssignees(!own);
  const list = useCursorList<Activity>(['activities', 'list'], '/activities', {
    status,
    search: q,
    category,
    assignee,
    priority,
    ordering: status === 'completed' ? '-date' : 'date',
  });
  const rows = list.data?.pages.flatMap((p) => p.results) ?? [];

  const quick = async (a: Activity, action: 'start' | 'complete') => {
    try {
      await api(`/activities/${a.id}/${action}`, { method: 'POST', body: {} });
      await Promise.all(
        ['activities', 'calendar', 'health'].map((k) => qc.invalidateQueries({ queryKey: [k] })),
      );
      toast.success(t(action === 'start' ? 'tasks.started' : 'tasks.done', { title: a.title }));
    } catch (err) {
      if (isQueued(err))
        await Promise.all(['activities', 'calendar'].map((k) => qc.invalidateQueries({ queryKey: [k] })));
      toast.error(err instanceof ApiError ? err.message : t('tasks.error'));
    }
  };

  return (
    <>
      <div className={page.header}>
        <div>
          <h2>{own ? t('tasks.myTasks') : t('tasks.farmActivities')}</h2>
          <p>{own ? t('tasks.myTasksIntro') : t('tasks.farmIntro')}</p>
        </div>
        {can(role, 'activities', 'create') && (
          <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>
            <Plus size={18} aria-hidden="true" /> New activity
          </button>
        )}
      </div>
      <div className={page.tabs} role="tablist" aria-label={t('tasks.status')}>
        {STATUS_TABS.map(([v, l]) => (
          <button
            key={l}
            type="button"
            role="tab"
            aria-selected={status === v}
            className={page.tab}
            onClick={() => setStatus(v)}
          >
            {t(`tasks.${l}`)}
          </button>
        ))}
      </div>
      <section className={page.card}>
        <div className={page.toolbar}>
          <div className={page.search}>
            <FormInput
              label={t('tasks.search')}
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <FormSelect
            label={t('tasks.category')}
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            <option value="">{t('tasks.all')}</option>
            {categories.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </FormSelect>
          {!own && (
            <FormSelect
              label={t('tasks.assignedTo')}
              value={assignee}
              onChange={(e) => setAssignee(e.target.value)}
            >
              <option value="">{t('tasks.anyone')}</option>
              <option value="me">{t('tasks.me')}</option>
              <option value="none">{t('tasks.nobody')}</option>
              {assignees.data?.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
            </FormSelect>
          )}
          <FormSelect
            label={t('tasks.priority')}
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
          >
            <option value="">{t('tasks.all')}</option>
            {PRIORITIES.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </FormSelect>
        </div>
        {list.isPending ? (
          <div className={page.cardBody}>
            <LoadingState />
          </div>
        ) : list.isError ? (
          <div className={page.cardBody}>
            <ErrorState message={list.error.message} onRetry={() => void list.refetch()} />
          </div>
        ) : rows.length === 0 ? (
          <div className={page.cardBody}>
            <EmptyState
              icon={ClipboardList}
              title={t('tasks.noActivities')}
              message={own ? t('tasks.nothingAssigned') : t('tasks.nothingMatches')}
            />
          </div>
        ) : (
          <>
            <ul className={cal.list}>
              {rows.map((a) => {
                const isOpen = ['pending', 'in_progress', 'overdue'].includes(a.status ?? '');
                const late = a.status === 'overdue' || (isOpen && a.date < todayIso());
                return (
                  <li key={a.id} className={cal.taskCard}>
                    <div className={cal.taskMain}>
                      <button type="button" className={cal.taskTitle} onClick={() => setOpenId(a.id)}>
                        {a.title}
                      </button>
                      <div className={cal.taskMeta}>
                        <span style={late ? { color: 'var(--tone-red-fg)', fontWeight: 600 } : undefined}>
                          {formatDate(a.date, fmt)} · {timeLabel(a)}
                        </span>
                        <CategoryChip category={a.category} />
                        {!own && <span>{a.assigned_to?.name ?? t('tasks.unassigned')}</span>}
                        {a.animals.length > 0 && <span>{a.animals.map((x) => x.animal_id).join(', ')}</span>}
                      </div>
                    </div>
                    <StatusBadge
                      status={a.priority}
                      label={t(
                        `tasks.${a.priority === 'high' ? 'high' : a.priority === 'low' ? 'low' : 'medium'}`,
                      )}
                    />
                    <StatusBadge status={a.status} />
                    {isOpen && (
                      <div className={cal.taskActions}>
                        {a.status !== 'in_progress' && can(role, 'activities', 'start') && (
                          <button
                            type="button"
                            className="btn btn-secondary"
                            onClick={() => void quick(a, 'start')}
                          >
                            {t('tasks.start')}
                          </button>
                        )}
                        {can(role, 'activities', 'complete') && (
                          <button
                            type="button"
                            className="btn btn-primary"
                            onClick={() => void quick(a, 'complete')}
                          >
                            {t('tasks.complete')}
                          </button>
                        )}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
            {list.hasNextPage && (
              <div className={page.footer}>
                <span>{t('tasks.showing', { shown: rows.length, total: list.data?.pages[0]?.count })}</span>
                <button type="button" className="btn btn-secondary" onClick={() => void list.fetchNextPage()}>
                  {t('tasks.loadMore')}
                </button>
              </div>
            )}
          </>
        )}
      </section>
      {openId && <ActivityDetail id={openId} onClose={() => setOpenId(null)} />}
      {creating && <ActivityForm onClose={() => setCreating(false)} />}
    </>
  );
}
