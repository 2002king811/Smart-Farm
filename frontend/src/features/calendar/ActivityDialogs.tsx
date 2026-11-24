import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Repeat } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { api, ApiError, isQueued } from '@/api/client';
import {
  applyServerErrors,
  Checkbox,
  CheckboxGroup,
  FormError,
  FormInput,
  FormSelect,
} from '@/components/forms';
import { LoadingState } from '@/components/LoadingState';
import { Modal } from '@/components/Modal';
import page from '@/components/Page.module.css';
import { StatusBadge } from '@/components/StatusBadge';
import { useToast } from '@/components/Toast';
import { useAnimalOptions } from '@/features/health/Records';
import { useGroups } from '@/features/livestock/api';
import { formatDate } from '@/features/livestock/format';
import styles from '@/features/livestock/Livestock.module.css';
import { useSession } from '@/features/session/SessionContext';
import { can } from '@/routes/permissions';

import {
  PRIORITIES,
  REPEATS,
  repeatOf,
  timeLabel,
  todayIso,
  useAssignees,
  useCategories,
  type Activity,
  type HistoryRow,
  type Note,
} from './api';
import cal from './Calendar.module.css';

function useRefresh() {
  const qc = useQueryClient();
  return () =>
    Promise.all(['activities', 'calendar', 'health'].map((k) => qc.invalidateQueries({ queryKey: [k] })));
}

export function CategoryChip({ category }: { category: Activity['category'] }) {
  if (!category) return null;
  return (
    <span className={cal.chipLabel}>
      <span className={cal.swatch} style={{ background: category.colour }} aria-hidden="true" />
      {category.name}
    </span>
  );
}

// --- Detail ---------------------------------------------------------------------------------------------

export function ActivityDetail({ id, onClose }: { id: string; onClose: () => void }) {
  const { role, user, activeFarm } = useSession();
  const { t } = useTranslation();
  const fmt = activeFarm?.farm.date_format ?? 'DD MMM YYYY';
  const toast = useToast();
  const refresh = useRefresh();
  const [editing, setEditing] = useState(false);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const activity = useQuery({
    queryKey: ['activities', id],
    queryFn: () => api<Activity>(`/activities/${id}`),
  });
  const notes = useQuery({
    queryKey: ['activities', id, 'notes'],
    queryFn: () => api<Note[]>(`/activities/${id}/notes`),
  });
  const history = useQuery({
    queryKey: ['activities', id, 'history'],
    queryFn: () => api<HistoryRow[]>(`/activities/${id}/history`),
  });

  if (editing && activity.data)
    return <ActivityForm activity={activity.data} onClose={() => setEditing(false)} />;

  const a = activity.data;
  const mine = a?.assigned_to?.id === user?.id;
  const may = (action: string) =>
    can(role, 'activities', action) && (mine || can(role, 'activities', 'update'));
  const open = a && ['pending', 'in_progress', 'overdue'].includes(a.status ?? '');

  const act = async (action: 'start' | 'complete' | 'cancel' | 'reopen') => {
    setBusy(true);
    try {
      await api(`/activities/${id}/${action}`, {
        method: 'POST',
        body: action === 'complete' || action === 'cancel' ? { note } : {},
      });
      setNote('');
      await refresh();
      toast.success(
        { start: 'Started.', complete: 'Marked as completed.', cancel: 'Cancelled.', reopen: 'Reopened.' }[
          action
        ],
      );
    } catch (err) {
      if (isQueued(err)) {
        setNote('');
        await refresh();
      }
      toast.error(err instanceof ApiError ? err.message : 'Something went wrong.');
    } finally {
      setBusy(false);
    }
  };
  const addNote = async () => {
    if (!note.trim()) return;
    try {
      await api(`/activities/${id}/notes`, { method: 'POST', body: { text: note } });
      setNote('');
      await refresh();
      toast.success('Note added.');
    } catch (err) {
      if (isQueued(err)) setNote('');
      toast.error(err instanceof ApiError ? err.message : 'Could not add the note.');
    }
  };
  const remove = async () => {
    let scope = 'this';
    if (a?.is_recurring) {
      const all = window.confirm(
        'This activity repeats. Delete this one AND all the following ones?\n\nOK = this and following, Cancel = only this one.',
      );
      scope = all ? 'following' : 'this';
    } else if (!window.confirm('Delete this activity?')) return;
    try {
      await api(`/activities/${id}?scope=${scope}`, { method: 'DELETE' });
      await refresh();
      toast.success('Deleted.');
      onClose();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not delete.');
    }
  };

  return (
    <Modal
      title={a?.title ?? 'Activity'}
      open
      onClose={onClose}
      footer={
        a && (
          <>
            {can(role, 'activities', 'delete') && (
              <button
                type="button"
                className="btn btn-secondary"
                style={{ marginRight: 'auto', color: 'var(--tone-red-fg)' }}
                onClick={() => void remove()}
              >
                {t('tasks.delete')}
              </button>
            )}
            {can(role, 'activities', 'update') && (
              <button type="button" className="btn btn-secondary" onClick={() => setEditing(true)}>
                {t('tasks.edit')}
              </button>
            )}
            {open && (a.status === 'pending' || a.status === 'overdue') && may('start') && (
              <button
                type="button"
                className="btn btn-secondary"
                disabled={busy}
                onClick={() => void act('start')}
              >
                {t('tasks.start')}
              </button>
            )}
            {open && may('cancel') && (
              <button
                type="button"
                className="btn btn-secondary"
                disabled={busy}
                onClick={() => void act('cancel')}
              >
                {t('tasks.cancelActivity')}
              </button>
            )}
            {open && may('complete') && (
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy}
                onClick={() => void act('complete')}
              >
                {t('tasks.markComplete')}
              </button>
            )}
            {!open && can(role, 'activities', 'update') && (
              <button
                type="button"
                className="btn btn-secondary"
                disabled={busy}
                onClick={() => void act('reopen')}
              >
                {t('tasks.reopen')}
              </button>
            )}
          </>
        )
      }
    >
      {activity.isPending || !a ? (
        <LoadingState />
      ) : (
        <>
          <div className={styles.badges}>
            <StatusBadge status={a.status} />
            <StatusBadge
              status={a.priority}
              label={t('tasks.priorityLabel', {
                level: t(`tasks.${a.priority === 'high' ? 'high' : a.priority === 'low' ? 'low' : 'medium'}`),
              })}
            />
            <CategoryChip category={a.category} />
            {a.is_recurring && (
              <span className={cal.chipLabel}>
                <Repeat size={14} aria-hidden="true" /> Repeats
              </span>
            )}
          </div>
          <dl className={styles.facts}>
            <div>
              <dt>{t('tasks.date')}</dt>
              <dd>
                {formatDate(a.date, fmt)} · {timeLabel(a)}
              </dd>
            </div>
            <div>
              <dt>{t('tasks.assignedTo')}</dt>
              <dd>{a.assigned_to?.name ?? t('tasks.nobodyYet')}</dd>
            </div>
            {a.animals.length > 0 && (
              <div>
                <dt>{t('tasks.animals')}</dt>
                <dd>
                  {a.animals.map((x, i) => (
                    <span key={x.id}>
                      {i > 0 && ', '}
                      <Link to={`/livestock/${x.id}`}>{x.animal_id}</Link>
                    </span>
                  ))}
                </dd>
              </div>
            )}
            {a.group && (
              <div>
                <dt>{t('tasks.group')}</dt>
                <dd>{a.group.name}</dd>
              </div>
            )}
            <div>
              <dt>{t('tasks.createdFrom')}</dt>
              <dd>{a.source_label}</dd>
            </div>
            {a.completed_at && (
              <div>
                <dt>{t('tasks.completedLabel')}</dt>
                <dd>
                  {formatDate(a.completed_at, fmt)}
                  {a.completed_by_name ? ` by ${a.completed_by_name}` : ''}
                </dd>
              </div>
            )}
          </dl>
          {a.description && <p style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{a.description}</p>}

          <section>
            <h3 style={{ fontSize: 'var(--text-md)', marginBottom: 8 }}>{t('tasks.notes')}</h3>
            {notes.data?.length ? (
              <ul className={cal.notes}>
                {notes.data.map((n) => (
                  <li key={n.id}>
                    {n.text}
                    <span className={page.sub}>
                      {n.author} · {formatDate(n.created_at, fmt)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className={page.sub}>{t('tasks.noNotes')}</p>
            )}
            {can(role, 'activities', 'add_note') && (mine || can(role, 'activities', 'update')) && (
              <div style={{ display: 'flex', gap: 8, alignItems: 'end', marginTop: 8 }}>
                <div style={{ flex: 1 }}>
                  <FormInput
                    label={t('tasks.addNoteLabel')}
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                  />
                </div>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => void addNote()}
                  disabled={!note.trim()}
                >
                  {t('tasks.addNote')}
                </button>
              </div>
            )}
          </section>
          <section>
            <h3 style={{ fontSize: 'var(--text-md)', marginBottom: 8 }}>{t('tasks.history')}</h3>
            {history.data?.length ? (
              <ul className={cal.notes}>
                {history.data.map((h) => (
                  <li key={h.id}>
                    <StatusBadge status={h.from_status || 'pending'} /> → <StatusBadge status={h.to_status} />
                    {h.note && ` ${h.note}`}
                    <span className={page.sub}>
                      {h.by} · {formatDate(h.created_at, fmt)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className={page.sub}>{t('tasks.noHistory')}</p>
            )}
          </section>
        </>
      )}
    </Modal>
  );
}

// --- Create / edit ----------------------------------------------------------------------------------------

type Values = {
  title: string;
  category: string;
  date: string;
  all_day: boolean;
  start_time: string;
  end_time: string;
  assigned_to: string;
  animals: string[];
  group: string;
  priority: string;
  description: string;
  repeat: string;
  repeat_until: string;
  reminder_days: string[];
  scope: 'this' | 'following';
};

export function ActivityForm({
  activity,
  defaultDate,
  onClose,
}: {
  activity?: Activity;
  defaultDate?: string;
  onClose: () => void;
}) {
  const toast = useToast();
  const refresh = useRefresh();
  const categories = useCategories();
  const assignees = useAssignees();
  const animals = useAnimalOptions();
  const groups = useGroups();
  const form = useForm<Values>({
    defaultValues: {
      title: activity?.title ?? '',
      category: activity?.category?.id ?? '',
      date: activity?.date ?? defaultDate ?? todayIso(),
      all_day: activity ? (activity.all_day ?? true) : true,
      start_time: activity?.start_time?.slice(0, 5) ?? '',
      end_time: activity?.end_time?.slice(0, 5) ?? '',
      assigned_to: activity?.assigned_to?.id ?? '',
      animals: activity?.animals.map((a) => a.id) ?? [],
      group: activity?.group?.id ?? '',
      priority: activity?.priority ?? 'medium',
      description: activity?.description ?? '',
      repeat: repeatOf(activity?.recurrence_rule),
      repeat_until: '',
      reminder_days: (activity?.reminder_days ?? [1]).map(String),
      scope: 'this',
    },
  });
  const { errors, isSubmitting } = form.formState;
  const allDay = form.watch('all_day');
  const repeat = form.watch('repeat');
  const recurring = !!activity?.is_recurring;

  const onSubmit = form.handleSubmit(async (v) => {
    if (!v.title.trim()) return form.setError('title', { message: 'Enter a title.' });
    const body: Record<string, unknown> = {
      title: v.title,
      category: v.category || null,
      date: v.date,
      all_day: v.all_day,
      start_time: v.all_day ? null : v.start_time || null,
      end_time: v.all_day ? null : v.end_time || null,
      assigned_to: v.assigned_to || null,
      animals: v.animals,
      group: v.group || null,
      priority: v.priority,
      description: v.description,
      reminder_days: v.reminder_days.map(Number).sort((x, y) => y - x),
    };
    const repeatChanged = repeat !== repeatOf(activity?.recurrence_rule);
    if (!activity || repeatChanged) {
      body.repeat = v.repeat;
      if (v.repeat && v.repeat_until) body.repeat_until = v.repeat_until;
    }
    if (activity && recurring) body.scope = repeatChanged ? 'following' : v.scope;
    try {
      await api(activity ? `/activities/${activity.id}` : '/activities', {
        method: activity ? 'PATCH' : 'POST',
        body,
      });
      await refresh();
      toast.success(
        activity ? 'Activity updated.' : v.repeat ? 'Repeating activity created.' : 'Activity created.',
      );
      onClose();
    } catch (err) {
      applyServerErrors(err, form.setError, [
        'title',
        'category',
        'date',
        'start_time',
        'end_time',
        'assigned_to',
        'animals',
        'group',
        'priority',
        'reminder_days',
      ]);
    }
  });

  return (
    <Modal
      title={activity ? 'Edit activity' : 'New activity'}
      open
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" form="activity-form" className="btn btn-primary" disabled={isSubmitting}>
            {isSubmitting ? 'Saving…' : 'Save'}
          </button>
        </>
      }
    >
      <form
        id="activity-form"
        onSubmit={onSubmit}
        noValidate
        style={{ display: 'grid', gap: 'var(--space-4)' }}
      >
        <FormError message={errors.root?.server?.message} />
        <FormInput label="Title *" error={errors.title?.message} {...form.register('title')} />
        <div className={page.grid2}>
          <FormSelect label="Category" {...form.register('category')}>
            <option value="">None</option>
            {categories.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </FormSelect>
          <FormSelect label="Priority" {...form.register('priority')}>
            {PRIORITIES.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </FormSelect>
        </div>
        <div className={page.grid2}>
          <FormInput label="Date *" type="date" error={errors.date?.message} {...form.register('date')} />
          <Checkbox label="All day" {...form.register('all_day')} />
        </div>
        {!allDay && (
          <div className={page.grid2}>
            <FormInput
              label="Start time"
              type="time"
              error={errors.start_time?.message}
              {...form.register('start_time')}
            />
            <FormInput
              label="End time"
              type="time"
              error={errors.end_time?.message}
              {...form.register('end_time')}
            />
          </div>
        )}
        <div className={page.grid2}>
          <FormSelect label="Assign to" error={errors.assigned_to?.message} {...form.register('assigned_to')}>
            <option value="">Nobody yet</option>
            {assignees.data?.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name} ({u.role_label})
              </option>
            ))}
          </FormSelect>
          <FormSelect label="Group" {...form.register('group')}>
            <option value="">None</option>
            {groups.data?.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </FormSelect>
        </div>
        <FormSelect
          label="Animals (hold Ctrl to pick several)"
          multiple
          size={4}
          {...form.register('animals')}
        >
          {animals.data?.map((a) => (
            <option key={a.id} value={a.id}>
              {a.animal_id} {a.name}
            </option>
          ))}
        </FormSelect>
        <div className={page.grid2}>
          <FormSelect label="Repeat" error={errors.repeat?.message} {...form.register('repeat')}>
            {REPEATS.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </FormSelect>
          {repeat && <FormInput label="Until (optional)" type="date" {...form.register('repeat_until')} />}
        </div>
        <CheckboxGroup legend="Remind before">
          {[
            ['7', '7 days'],
            ['3', '3 days'],
            ['1', '1 day'],
            ['0', 'On the day'],
          ].map(([v, l]) => (
            <Checkbox key={v} label={l} value={v} {...form.register('reminder_days')} />
          ))}
        </CheckboxGroup>
        <div>
          <label htmlFor="activity-description" style={{ fontWeight: 600, fontSize: 'var(--text-sm)' }}>
            Description
          </label>
          <textarea id="activity-description" className={styles.textarea} {...form.register('description')} />
        </div>
        {recurring && (
          <CheckboxGroup legend="This activity repeats. Apply changes to:">
            <label className={cal.radio}>
              <input type="radio" value="this" {...form.register('scope')} /> This one only
            </label>
            <label className={cal.radio}>
              <input type="radio" value="following" {...form.register('scope')} /> This and following
            </label>
          </CheckboxGroup>
        )}
      </form>
    </Modal>
  );
}
