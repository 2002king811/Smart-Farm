import { useQuery, useQueryClient } from '@tanstack/react-query';
import { HeartPulse, Plus } from 'lucide-react';
import { useDeferredValue, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';

import { api, ApiError } from '@/api/client';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { applyServerErrors, Checkbox, FormError, FormInput, FormSelect } from '@/components/forms';
import { LoadingState } from '@/components/LoadingState';
import { Modal } from '@/components/Modal';
import page from '@/components/Page.module.css';
import { useToast } from '@/components/Toast';
import { useGroups, useLocations, type AnimalRow } from '@/features/livestock/api';
import styles from '@/features/livestock/Livestock.module.css';
import { useSession } from '@/features/session/SessionContext';
import { useCursorList } from '@/features/users/api';
import { can } from '@/routes/permissions';

import type { Field, RecordType, Row } from './config';

interface Vaccine {
  id: string;
  name: string;
  disease_category: string;
  default_dose: string;
  route: string;
  booster_interval_days: number | null;
}
interface Medicine {
  id: string;
  name: string;
  type: string;
  default_dose: string;
  route: string;
}

const today = () => new Date().toISOString().slice(0, 10);

/** Saving a record can change animals, the calendar, stock and summaries: refresh them all. */
const REFRESH = ['health', 'animals', 'activities', 'calendar', 'breeding', 'nutrition'];

interface FeedItemOption {
  id: string;
  name: string;
  unit: string;
  stock_quantity: string;
}

function addDays(day: string, n: number) {
  const d = new Date(`${day}T12:00:00`);
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

export function useAnimalOptions() {
  return useQuery({
    queryKey: ['animals', 'options'],
    queryFn: () =>
      api<{ results: AnimalRow[] }>('/animals', { query: { page_size: 200 } }).then((r) => r.results),
    staleTime: 60_000,
  });
}

/** Table of one record type, with add / edit / delete (and resolve for treatments). */
export function RecordList({ type, animalId }: { type: RecordType; animalId?: string }) {
  const { role, activeFarm } = useSession();
  const fmt = activeFarm?.farm.date_format ?? 'DD MMM YYYY';
  const qc = useQueryClient();
  const toast = useToast();
  const [search, setSearch] = useState('');
  const q = useDeferredValue(search);
  const query: Record<string, string> = animalId
    ? { [type.animalParam ?? 'animal']: animalId }
    : { search: q };
  const list = useCursorList<Row>(['health', type.key], type.path, query);
  const [editing, setEditing] = useState<Row | 'new' | null>(null);
  const rows = list.data?.pages.flatMap((p) => p.results) ?? [];
  const mod = type.module ?? 'health';
  const columns = type.columns.filter((c) => !(animalId && c.subject));

  const remove = async (row: Row) => {
    if (!window.confirm(`Delete this ${type.singular}? Any calendar reminder it created is removed too.`))
      return;
    try {
      await api(`${type.path}/${row.id}`, { method: 'DELETE' });
      await Promise.all(REFRESH.map((k) => qc.invalidateQueries({ queryKey: [k] })));
      toast.success(`The ${type.singular} was deleted.`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not delete.');
    }
  };
  const resolve = async (row: Row) => {
    try {
      await api(`/treatments/${row.id}/resolve`, { method: 'POST', body: {} });
      await qc.invalidateQueries({ queryKey: ['health'] });
      await qc.invalidateQueries({ queryKey: ['animals'] });
      toast.success('Treatment resolved.');
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not resolve.');
    }
  };

  return (
    <section className={page.card}>
      <div className={page.toolbar} style={{ alignItems: 'end' }}>
        {!animalId && (
          <div className={page.search}>
            <FormInput
              label="Search"
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        )}
        {animalId && <h3 style={{ alignSelf: 'center' }}>{type.title}</h3>}
        {can(role, mod, type.createAction ?? 'create') && (
          <div style={{ flex: '0 0 auto' }}>
            <button type="button" className="btn btn-primary" onClick={() => setEditing('new')}>
              <Plus size={18} aria-hidden="true" /> Record {type.singular}
            </button>
          </div>
        )}
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
          <EmptyState icon={HeartPulse} title="Nothing recorded" message={type.empty} />
        </div>
      ) : (
        <>
          <div className={page.tableWrap}>
            <table className={page.table}>
              <thead>
                <tr>
                  {columns.map((c) => (
                    <th key={c.label} scope="col">
                      {c.label}
                    </th>
                  ))}
                  <th scope="col">
                    <span className="visually-hidden">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    {columns.map((c) => (
                      <td key={c.label}>{c.render(r, fmt)}</td>
                    ))}
                    <td>
                      <div className={page.rowActions}>
                        {type.key === 'treatments' && r.status === 'ongoing' && can(role, mod, 'update') && (
                          <button type="button" className={page.small} onClick={() => void resolve(r)}>
                            Resolve
                          </button>
                        )}
                        {can(role, mod, 'update') && (
                          <button type="button" className={page.small} onClick={() => setEditing(r)}>
                            Edit
                          </button>
                        )}
                        {can(role, mod, 'delete') && (
                          <button
                            type="button"
                            className={`${page.small} ${page.danger}`}
                            onClick={() => void remove(r)}
                          >
                            Delete
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {list.hasNextPage && (
            <div className={page.footer}>
              <span />
              <button type="button" className="btn btn-secondary" onClick={() => void list.fetchNextPage()}>
                Load more
              </button>
            </div>
          )}
        </>
      )}
      {editing && (
        <RecordForm
          type={type}
          row={editing === 'new' ? undefined : editing}
          animalId={animalId}
          onClose={() => setEditing(null)}
        />
      )}
    </section>
  );
}

type Values = Record<string, string | string[] | boolean>;

function initialValues(type: RecordType, row?: Row, animalId?: string): Values {
  const v: Values = {};
  for (const f of type.fields) {
    const raw = row?.[f.name];
    if (f.type === 'checkbox')
      v[f.name] = raw === undefined || raw === null ? f.initial !== 'false' : Boolean(raw);
    else if (f.type === 'animals') v[f.name] = (raw as string[] | undefined) ?? (animalId ? [animalId] : []);
    else if (f.type === 'money') v[f.name] = raw ? String(Number(raw) / 100) : '';
    else if (raw !== undefined && raw !== null) v[f.name] = String(raw);
    else if (f.name === 'animal' && animalId) v[f.name] = animalId;
    else if (f.type === 'date' && f.name === 'date') v[f.name] = today();
    else v[f.name] = f.initial ?? '';
  }
  return v;
}

function toBody(type: RecordType, values: Values, creating: boolean) {
  const body: Record<string, unknown> = {};
  for (const f of type.fields) {
    const v = values[f.name];
    // On a new record, leave empty fields out so the server's defaults apply (e.g. the
    // withdrawal date from the medicine); on an edit, empty means "clear it".
    if (creating && (v === '' || v === undefined)) continue;
    if (f.type === 'checkbox') body[f.name] = Boolean(v);
    else if (f.type === 'animals') body[f.name] = v;
    else if (f.type === 'money') body[f.name] = v ? Math.round(Number(v) * 100) : null;
    else if (
      ['animal', 'group', 'vaccine', 'medicine', 'feed', 'location', 'date', 'number'].includes(f.type) ||
      (f.type === 'select' && f.name === 'score')
    )
      body[f.name] = v === '' ? null : v;
    else body[f.name] = v ?? '';
  }
  return body;
}

export function RecordForm(props: { type: RecordType; row?: Row; animalId?: string; onClose: () => void }) {
  // Dropdowns must have their options before the form sets a pre-selected value.
  const animals = useAnimalOptions();
  const needsAnimals = props.type.fields.some((f) => f.type === 'animal' || f.type === 'animals');
  if (needsAnimals && animals.isPending)
    return (
      <Modal title={`Record ${props.type.singular}`} open onClose={props.onClose}>
        <LoadingState />
      </Modal>
    );
  return <RecordFormBody {...props} />;
}

function RecordFormBody({
  type,
  row,
  animalId,
  onClose,
}: {
  type: RecordType;
  row?: Row;
  animalId?: string;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const { activeFarm } = useSession();
  const currency = activeFarm?.farm.currency ?? 'KES';
  const form = useForm<Values>({ defaultValues: initialValues(type, row, animalId) });
  const { errors, isSubmitting } = form.formState;
  const needs = (t: string) => type.fields.some((f) => f.type === t);
  const animals = useAnimalOptions();
  const groups = useGroups();
  const vaccines = useQuery({
    queryKey: ['vaccines'],
    queryFn: () => api<Vaccine[]>('/vaccines'),
    enabled: needs('vaccine'),
    staleTime: 300_000,
  });
  const medicines = useQuery({
    queryKey: ['medicines'],
    queryFn: () => api<Medicine[]>('/medicines'),
    enabled: needs('medicine'),
    staleTime: 300_000,
  });
  const feedItems = useQuery({
    queryKey: ['nutrition', 'feed-items'],
    queryFn: () => api<FeedItemOption[]>('/feed-items'),
    enabled: needs('feed'),
  });
  const locations = useLocations();
  const vaccineById = useMemo(() => new Map((vaccines.data ?? []).map((v) => [v.id, v])), [vaccines.data]);

  const onVaccine = (id: string) => {
    const v = vaccineById.get(id);
    if (!v) return;
    form.setValue('disease_category', v.disease_category);
    if (!form.getValues('dosage')) form.setValue('dosage', v.default_dose);
    if (!form.getValues('route')) form.setValue('route', v.route);
    if (v.booster_interval_days && !form.getValues('next_due_date'))
      form.setValue(
        'next_due_date',
        addDays(String(form.getValues('date') || today()), v.booster_interval_days),
      );
  };

  const onSubmit = form.handleSubmit(async (values) => {
    for (const f of type.fields) {
      if (f.required && !values[f.name]) {
        form.setError(f.name, { message: `${f.label} is required.` });
        return;
      }
    }
    try {
      await api(row ? `${type.path}/${row.id}` : type.path, {
        method: row ? 'PATCH' : 'POST',
        body: toBody(type, values, !row),
      });
      await Promise.all(REFRESH.map((k) => qc.invalidateQueries({ queryKey: [k] })));
      toast.success(row ? `The ${type.singular} was updated.` : `The ${type.singular} was recorded.`);
      onClose();
    } catch (err) {
      applyServerErrors(
        err,
        form.setError,
        type.fields.map((f) => f.name),
      );
    }
  });

  const control = (f: Field) => {
    const err = errors[f.name]?.message as string | undefined;
    const label = f.required ? `${f.label} *` : f.label;
    const reg = form.register(f.name);
    switch (f.type) {
      case 'textarea':
        return (
          <div key={f.name}>
            <label htmlFor={`f-${f.name}`} style={{ fontWeight: 600, fontSize: 'var(--text-sm)' }}>
              {label}
            </label>
            <textarea id={`f-${f.name}`} className={styles.textarea} {...reg} />
            {err && (
              <p style={{ margin: 0, color: 'var(--tone-red-fg)', fontSize: 'var(--text-sm)' }}>{err}</p>
            )}
          </div>
        );
      case 'date':
        return (
          <FormInput
            key={f.name}
            label={label}
            type="date"
            hint={f.hint}
            error={err}
            {...reg}
            max={f.name === 'date' ? today() : undefined}
          />
        );
      case 'number':
        return (
          <FormInput
            key={f.name}
            label={label}
            type="number"
            step="any"
            inputMode="decimal"
            hint={f.hint}
            error={err}
            {...reg}
          />
        );
      case 'money':
        return (
          <FormInput
            key={f.name}
            label={`${label} (${currency})`}
            type="number"
            step="0.01"
            min="0"
            error={err}
            {...reg}
          />
        );
      case 'select':
        return (
          <FormSelect key={f.name} label={label} hint={f.hint} error={err} {...reg}>
            <option value="">Choose…</option>
            {f.options?.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </FormSelect>
        );
      case 'animal':
        return (
          <FormSelect key={f.name} label={label} hint={f.hint} error={err} {...reg}>
            <option value="">{f.required ? 'Choose…' : 'None'}</option>
            {animals.data
              ?.filter((a) => !type.animalSex || a.sex === type.animalSex)
              .map((a) => (
                <option key={a.id} value={a.id}>
                  {a.animal_id} {a.name}
                </option>
              ))}
          </FormSelect>
        );
      case 'group':
        return (
          <FormSelect key={f.name} label={label} error={err} {...reg}>
            <option value="">None</option>
            {groups.data?.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </FormSelect>
        );
      case 'animals':
        return (
          <FormSelect
            key={f.name}
            label={`${label} (hold Ctrl to pick several)`}
            multiple
            size={5}
            error={err}
            {...reg}
          >
            {animals.data?.map((a) => (
              <option key={a.id} value={a.id}>
                {a.animal_id} {a.name}
              </option>
            ))}
          </FormSelect>
        );
      case 'vaccine':
        return (
          <FormSelect
            key={f.name}
            label={label}
            error={err}
            {...reg}
            onChange={(e) => (void reg.onChange(e), onVaccine(e.target.value))}
          >
            <option value="">Choose…</option>
            {vaccines.data?.map((v) => (
              <option key={v.id} value={v.id}>
                {v.name}
              </option>
            ))}
          </FormSelect>
        );
      case 'medicine':
        return (
          <FormSelect key={f.name} label={label} error={err} {...reg}>
            <option value="">Choose…</option>
            {medicines.data
              ?.filter((m) => !f.medicineTypes || f.medicineTypes.includes(m.type))
              .map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
          </FormSelect>
        );
      case 'feed':
        return (
          <FormSelect key={f.name} label={label} hint={f.hint} error={err} {...reg}>
            <option value="">{f.required ? 'Choose…' : 'Not from stock'}</option>
            {feedItems.data?.map((i) => (
              <option key={i.id} value={i.id}>
                {i.name} ({Number(i.stock_quantity)} {i.unit} in stock)
              </option>
            ))}
          </FormSelect>
        );
      case 'location':
        return (
          <FormSelect key={f.name} label={label} error={err} {...reg}>
            <option value="">None</option>
            {locations.data?.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </FormSelect>
        );
      case 'checkbox':
        return <Checkbox key={f.name} label={f.label} {...reg} />;
      default:
        return <FormInput key={f.name} label={label} hint={f.hint} error={err} {...reg} />;
    }
  };

  return (
    <Modal
      title={row ? `Edit ${type.singular}` : `Record ${type.singular}`}
      open
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" form={`form-${type.key}`} className="btn btn-primary" disabled={isSubmitting}>
            {isSubmitting ? 'Saving…' : 'Save'}
          </button>
        </>
      }
    >
      <form
        id={`form-${type.key}`}
        onSubmit={onSubmit}
        noValidate
        style={{ display: 'grid', gap: 'var(--space-4)' }}
      >
        <FormError message={errors.root?.server?.message} />
        <div className={page.grid2}>{type.fields.filter((f) => f.type !== 'textarea').map(control)}</div>
        {type.fields.filter((f) => f.type === 'textarea').map(control)}
      </form>
    </Modal>
  );
}
