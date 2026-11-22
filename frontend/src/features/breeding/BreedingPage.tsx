import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Baby, HeartHandshake, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { useFieldArray, useForm } from 'react-hook-form';
import { Link, NavLink, Navigate, Route, Routes } from 'react-router-dom';

import { api, ApiError } from '@/api/client';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { applyServerErrors, Checkbox, FormError, FormInput, FormSelect } from '@/components/forms';
import { LoadingState } from '@/components/LoadingState';
import { Modal } from '@/components/Modal';
import page from '@/components/Page.module.css';
import { StatusBadge } from '@/components/StatusBadge';
import { useToast } from '@/components/Toast';
import { RecordList, useAnimalOptions } from '@/features/health/Records';
import type { Row } from '@/features/health/config';
import { formatDate, formatWeight } from '@/features/livestock/format';
import styles from '@/features/livestock/Livestock.module.css';
import { useSession } from '@/features/session/SessionContext';
import { useCursorList } from '@/features/users/api';
import { can } from '@/routes/permissions';

import { MATING_STATUS, MORTALITY } from './config';
import b from './Breeding.module.css';

const REFRESH = ['breeding', 'animals', 'activities', 'calendar', 'health'];
const TABS = [
  ['pregnancies', 'Pregnancies'],
  ['matings', 'Matings'],
  ['births', 'Births'],
  ['kids', 'Kids'],
  ['mortality', 'Mortality'],
] as const;

interface Pregnancy {
  mating_id: string;
  doe: string;
  doe_label: string;
  buck_label: string;
  mating_date: string;
  pregnancy_status: string;
  expected_kidding_date: string;
  days_pregnant: number;
  days_remaining: number;
  progress_percent: number;
  trimester: number;
}

function useRefresh() {
  const qc = useQueryClient();
  return () => Promise.all(REFRESH.map((k) => qc.invalidateQueries({ queryKey: [k] })));
}

export default function BreedingPage() {
  const { role } = useSession();
  const [birthFor, setBirthFor] = useState<{ dam?: string; mating?: string } | null>(null);
  const [mating, setMating] = useState(false);
  return (
    <>
      <div className={page.header}>
        <div>
          <h2>Breeding &amp; kids</h2>
          <p>Matings, pregnancy checks, births and kid growth. Expected kidding is 150 days after mating.</p>
        </div>
        <div className={styles.headerActions}>
          {can(role, 'breeding', 'create') && (
            <button type="button" className="btn btn-secondary" onClick={() => setMating(true)}>
              <HeartHandshake size={18} aria-hidden="true" /> Record mating
            </button>
          )}
          {can(role, 'breeding', 'record_birth') && (
            <button type="button" className="btn btn-primary" onClick={() => setBirthFor({})}>
              <Baby size={18} aria-hidden="true" /> Register birth
            </button>
          )}
        </div>
      </div>
      <nav className={page.tabs} aria-label="Breeding sections">
        {TABS.map(([k, l]) => (
          <NavLink key={k} to={`/breeding/${k}`} className={page.tab}>
            {l}
          </NavLink>
        ))}
      </nav>
      <Routes>
        <Route index element={<Navigate to="pregnancies" replace />} />
        <Route
          path="pregnancies"
          element={<Pregnancies onBirth={(dam, m) => setBirthFor({ dam, mating: m })} />}
        />
        <Route path="matings" element={<Matings onBirth={(dam, m) => setBirthFor({ dam, mating: m })} />} />
        <Route path="births" element={<Births />} />
        <Route path="kids" element={<Kids />} />
        <Route path="mortality" element={<RecordList type={MORTALITY} />} />
        <Route path="*" element={<Navigate to="/breeding" replace />} />
      </Routes>
      {mating && <MatingForm onClose={() => setMating(false)} />}
      {birthFor && (
        <BirthForm dam={birthFor.dam} mating={birthFor.mating} onClose={() => setBirthFor(null)} />
      )}
    </>
  );
}

// --- Pregnancies ---------------------------------------------------------------------------------------

function Pregnancies({ onBirth }: { onBirth: (dam: string, mating: string) => void }) {
  const { role, activeFarm } = useSession();
  const fmt = activeFarm?.farm.date_format ?? 'DD MMM YYYY';
  const list = useQuery({
    queryKey: ['breeding', 'pregnancies'],
    queryFn: () => api<Pregnancy[]>('/pregnancies'),
  });
  if (list.isPending) return <LoadingState />;
  if (list.isError) return <ErrorState message={list.error.message} onRetry={() => void list.refetch()} />;
  if (!list.data.length)
    return (
      <EmptyState
        icon={HeartHandshake}
        title="No pregnancies being monitored"
        message="Record a mating to start tracking the expected kidding date."
      />
    );
  return (
    <div className={b.cards}>
      {list.data.map((p) => (
        <article key={p.mating_id} className={page.card}>
          <div className={page.cardBody}>
            <div className={b.cardHead}>
              <Link to={`/livestock/${p.doe}`} className={styles.animalLink}>
                {p.doe_label}
              </Link>
              <StatusBadge status={p.pregnancy_status} />
            </div>
            <p className={page.sub}>
              Mated {formatDate(p.mating_date, fmt)} with {p.buck_label}
            </p>
            <div
              className={b.progress}
              role="progressbar"
              aria-valuenow={p.progress_percent}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={`${p.progress_percent}% of gestation`}
            >
              <span style={{ width: `${p.progress_percent}%` }} />
            </div>
            <dl className={b.numbers}>
              <div>
                <dt>Expected kidding</dt>
                <dd>{formatDate(p.expected_kidding_date, fmt)}</dd>
              </div>
              <div>
                <dt>{p.days_remaining >= 0 ? 'Days to go' : 'Days overdue'}</dt>
                <dd className={p.days_remaining < 0 ? b.late : undefined}>{Math.abs(p.days_remaining)}</dd>
              </div>
              <div>
                <dt>Day of pregnancy</dt>
                <dd>
                  {p.days_pregnant} (trimester {p.trimester})
                </dd>
              </div>
            </dl>
            {can(role, 'breeding', 'record_birth') && (
              <button type="button" className="btn btn-secondary" onClick={() => onBirth(p.doe, p.mating_id)}>
                <Baby size={18} aria-hidden="true" /> Register birth
              </button>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}

// --- Matings -------------------------------------------------------------------------------------------

function Matings({ onBirth }: { onBirth: (dam: string, mating: string) => void }) {
  const { role, activeFarm } = useSession();
  const fmt = activeFarm?.farm.date_format ?? 'DD MMM YYYY';
  const toast = useToast();
  const refresh = useRefresh();
  const list = useCursorList<Row>(['breeding', 'matings'], '/matings', {});
  const rows = list.data?.pages.flatMap((p) => p.results) ?? [];

  const act = async (r: Row, path: string, body: object, done: string) => {
    try {
      await api(`/matings/${r.id}/${path}`, { method: 'POST', body });
      await refresh();
      toast.success(done);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Something went wrong.');
    }
  };

  if (list.isPending) return <LoadingState />;
  if (list.isError) return <ErrorState message={list.error.message} onRetry={() => void list.refetch()} />;
  if (!rows.length)
    return (
      <EmptyState
        icon={HeartHandshake}
        title="No matings yet"
        message="Use “Record mating” when a doe is served."
      />
    );
  return (
    <section className={page.card}>
      <div className={page.tableWrap}>
        <table className={page.table}>
          <thead>
            <tr>
              <th scope="col">Date</th>
              <th scope="col">Doe</th>
              <th scope="col">Buck / AI</th>
              <th scope="col">Status</th>
              <th scope="col">Expected kidding</th>
              <th scope="col">Kids</th>
              <th scope="col">
                <span className="visually-hidden">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{formatDate(r.date as string, fmt)}</td>
                <td>{String(r.doe_label)}</td>
                <td>{String(r.buck_label)}</td>
                <td>{MATING_STATUS(r)}</td>
                <td>{formatDate(r.expected_kidding_date as string, fmt)}</td>
                <td>{r.kids_count === null ? '—' : String(r.kids_count)}</td>
                <td>
                  {r.status === 'active' && (
                    <div className={page.rowActions}>
                      {r.pregnancy_status === 'awaiting_scan' && can(role, 'breeding', 'update') && (
                        <>
                          <button
                            type="button"
                            className={page.small}
                            onClick={() =>
                              void act(r, 'scan', { result: 'confirmed' }, 'Pregnancy confirmed.')
                            }
                          >
                            Pregnant
                          </button>
                          <button
                            type="button"
                            className={page.small}
                            onClick={() =>
                              void act(r, 'scan', { result: 'not_pregnant' }, 'Recorded as not pregnant.')
                            }
                          >
                            Not pregnant
                          </button>
                        </>
                      )}
                      {can(role, 'breeding', 'record_birth') && (
                        <button
                          type="button"
                          className={page.small}
                          onClick={() => onBirth(r.doe as string, r.id)}
                        >
                          Birth
                        </button>
                      )}
                      {r.pregnancy_status === 'confirmed' && can(role, 'breeding', 'update') && (
                        <button
                          type="button"
                          className={`${page.small} ${page.danger}`}
                          onClick={() =>
                            window.confirm('Record that this pregnancy was lost?') &&
                            void act(r, 'abort', {}, 'Recorded as aborted.')
                          }
                        >
                          Aborted
                        </button>
                      )}
                    </div>
                  )}
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
    </section>
  );
}

function MatingForm({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const refresh = useRefresh();
  const animals = useAnimalOptions();
  const form = useForm({
    defaultValues: {
      doe: '',
      buck: '',
      method: 'natural',
      ai_straw: '',
      date: new Date().toISOString().slice(0, 10),
      notes: '',
    },
  });
  const method = form.watch('method');
  const { errors, isSubmitting } = form.formState;
  const onSubmit = form.handleSubmit(async (v) => {
    try {
      const res = await api<{ expected_kidding_date: string }>('/matings', {
        method: 'POST',
        body: {
          ...v,
          buck: v.method === 'ai' ? null : v.buck || null,
          ai_straw: v.method === 'ai' ? v.ai_straw : '',
        },
      });
      await refresh();
      toast.success(`Mating recorded. Expected kidding ${formatDate(res.expected_kidding_date)}.`);
      onClose();
    } catch (err) {
      applyServerErrors(err, form.setError, ['doe', 'buck', 'ai_straw', 'date', 'method']);
    }
  });
  const opts = (sex: string) =>
    animals.data
      ?.filter((a) => a.sex === sex)
      .map((a) => (
        <option key={a.id} value={a.id}>
          {a.animal_id} {a.name}
        </option>
      ));
  return (
    <Modal
      title="Record mating"
      open
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" form="mating-form" className="btn btn-primary" disabled={isSubmitting}>
            Save
          </button>
        </>
      }
    >
      <form
        id="mating-form"
        onSubmit={onSubmit}
        noValidate
        style={{ display: 'grid', gap: 'var(--space-4)' }}
      >
        <FormError message={errors.root?.server?.message} />
        <div className={page.grid2}>
          <FormSelect label="Doe *" error={errors.doe?.message} {...form.register('doe')}>
            <option value="">Choose…</option>
            {opts('female')}
          </FormSelect>
          <FormInput label="Date *" type="date" error={errors.date?.message} {...form.register('date')} />
        </div>
        <FormSelect label="Method" {...form.register('method')}>
          <option value="natural">Natural (buck)</option>
          <option value="ai">Artificial insemination</option>
        </FormSelect>
        {method === 'ai' ? (
          <FormInput
            label="AI straw / sire details *"
            error={errors.ai_straw?.message ?? errors.buck?.message}
            {...form.register('ai_straw')}
          />
        ) : (
          <FormSelect label="Buck *" error={errors.buck?.message} {...form.register('buck')}>
            <option value="">Choose…</option>
            {opts('male')}
          </FormSelect>
        )}
        <FormInput label="Notes" {...form.register('notes')} />
        <p className={page.sub}>
          Expected kidding is set to 150 days later. A pregnancy scan task is added after 35 days.
        </p>
      </form>
    </Modal>
  );
}

// --- Births --------------------------------------------------------------------------------------------

function Births() {
  const { activeFarm } = useSession();
  const fmt = activeFarm?.farm.date_format ?? 'DD MMM YYYY';
  const list = useCursorList<Row>(['breeding', 'births'], '/births', {});
  const rows = list.data?.pages.flatMap((p) => p.results) ?? [];
  if (list.isPending) return <LoadingState />;
  if (list.isError) return <ErrorState message={list.error.message} onRetry={() => void list.refetch()} />;
  if (!rows.length)
    return (
      <EmptyState
        icon={Baby}
        title="No births yet"
        message="Use “Register birth”. Each live kid is added to the register."
      />
    );
  return (
    <section className={page.card}>
      <div className={page.tableWrap}>
        <table className={page.table}>
          <thead>
            <tr>
              <th scope="col">Date</th>
              <th scope="col">Dam</th>
              <th scope="col">Sire</th>
              <th scope="col">Type</th>
              <th scope="col">Kids</th>
              <th scope="col">Condition</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{formatDate(r.date as string, fmt)}</td>
                <td>{String(r.dam_label)}</td>
                <td>{String(r.sire_label ?? '—')}</td>
                <td style={{ textTransform: 'capitalize' }}>{String(r.birth_type)}</td>
                <td>
                  {(r.kids as { id: string; animal_id: string }[]).map((k, i) => (
                    <span key={k.id}>
                      {i > 0 && ', '}
                      <Link to={`/livestock/${k.id}`}>{k.animal_id}</Link>
                    </span>
                  ))}
                  {Number(r.stillborn_count) > 0 && (
                    <span className={page.sub}>{String(r.stillborn_count)} stillborn</span>
                  )}
                </td>
                <td style={{ textTransform: 'capitalize' }}>{String(r.condition)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

interface KidLine {
  sex: string;
  name: string;
  ear_tag: string;
  birth_weight_kg: string;
  alive: boolean;
}

function BirthForm(props: { dam?: string; mating?: string; onClose: () => void }) {
  // Wait for the animal list so a pre-selected dam is kept by the dropdown.
  const animals = useAnimalOptions();
  if (animals.isPending)
    return (
      <Modal title="Register birth" open onClose={props.onClose}>
        <LoadingState />
      </Modal>
    );
  return <BirthFormBody {...props} />;
}

function BirthFormBody({ dam, mating, onClose }: { dam?: string; mating?: string; onClose: () => void }) {
  const toast = useToast();
  const refresh = useRefresh();
  const animals = useAnimalOptions();
  const form = useForm<{ dam: string; date: string; condition: string; notes: string; kids: KidLine[] }>({
    defaultValues: {
      dam: dam ?? '',
      date: new Date().toISOString().slice(0, 10),
      condition: 'normal',
      notes: '',
      kids: [{ sex: '', name: '', ear_tag: '', birth_weight_kg: '', alive: true }],
    },
  });
  const kids = useFieldArray({ control: form.control, name: 'kids' });
  const { errors, isSubmitting } = form.formState;

  const onSubmit = form.handleSubmit(async (v) => {
    const missing = v.kids.findIndex((k) => !k.sex);
    if (missing >= 0) return form.setError(`kids.${missing}.sex`, { message: 'Choose female or male.' });
    try {
      const res = await api<{ kids: { animal_id: string }[] }>('/births', {
        method: 'POST',
        body: {
          dam: v.dam,
          mating: mating ?? null,
          date: v.date,
          condition: v.condition,
          notes: v.notes,
          kids: v.kids.map((k) => ({ ...k, birth_weight_kg: k.birth_weight_kg || null })),
        },
      });
      await refresh();
      toast.success(
        res.kids.length
          ? `Birth registered. ${res.kids.map((k) => k.animal_id).join(', ')} added to the register.`
          : 'Birth registered.',
      );
      onClose();
    } catch (err) {
      applyServerErrors(err, form.setError, ['dam', 'date', 'condition', 'mating']);
      if (err instanceof ApiError && err.errors.kids)
        form.setError('root.server', { message: err.errors.kids.join(' ') });
    }
  });

  return (
    <Modal
      title="Register birth"
      open
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" form="birth-form" className="btn btn-primary" disabled={isSubmitting}>
            {isSubmitting ? 'Saving…' : 'Register birth'}
          </button>
        </>
      }
    >
      <form id="birth-form" onSubmit={onSubmit} noValidate style={{ display: 'grid', gap: 'var(--space-4)' }}>
        <FormError message={errors.root?.server?.message} />
        <div className={page.grid2}>
          <FormSelect
            label="Dam (mother) *"
            error={errors.dam?.message}
            {...form.register('dam', { required: 'Choose the dam.' })}
          >
            <option value="">Choose…</option>
            {animals.data
              ?.filter((a) => a.sex === 'female')
              .map((a) => (
                <option key={a.id} value={a.id}>
                  {a.animal_id} {a.name}
                </option>
              ))}
          </FormSelect>
          <FormInput label="Date *" type="date" error={errors.date?.message} {...form.register('date')} />
        </div>
        <FormSelect label="Birth" {...form.register('condition')}>
          <option value="normal">Normal</option>
          <option value="assisted">Assisted</option>
          <option value="difficult">Difficult (dystocia)</option>
        </FormSelect>
        <fieldset className={b.kids}>
          <legend>Kids</legend>
          {kids.fields.map((field, i) => (
            <div key={field.id} className={b.kidRow}>
              <strong className={b.kidNo}>Kid {i + 1}</strong>
              <FormSelect
                label="Sex *"
                error={errors.kids?.[i]?.sex?.message}
                {...form.register(`kids.${i}.sex`)}
              >
                <option value="">Choose…</option>
                <option value="female">Female</option>
                <option value="male">Male</option>
              </FormSelect>
              <FormInput label="Name" {...form.register(`kids.${i}.name`)} />
              <FormInput label="Ear tag" {...form.register(`kids.${i}.ear_tag`)} />
              <FormInput
                label="Birth weight (kg)"
                type="number"
                step="0.1"
                min="0"
                inputMode="decimal"
                {...form.register(`kids.${i}.birth_weight_kg`)}
              />
              <Checkbox label="Alive" {...form.register(`kids.${i}.alive`)} />
              {kids.fields.length > 1 && (
                <button
                  type="button"
                  className={page.small}
                  onClick={() => kids.remove(i)}
                  aria-label={`Remove kid ${i + 1}`}
                >
                  <Trash2 size={16} aria-hidden="true" />
                </button>
              )}
            </div>
          ))}
          {kids.fields.length < 6 && (
            <button
              type="button"
              className="btn btn-secondary"
              style={{ justifySelf: 'start' }}
              onClick={() =>
                kids.append({ sex: '', name: '', ear_tag: '', birth_weight_kg: '', alive: true })
              }
            >
              <Plus size={16} aria-hidden="true" /> Add another kid
            </button>
          )}
        </fieldset>
        <FormInput label="Notes" {...form.register('notes')} />
        <p className={page.sub}>
          Each live kid gets the next animal ID and its birth weight. The open mating is closed as Kidded.
        </p>
      </form>
    </Modal>
  );
}

// --- Kids ----------------------------------------------------------------------------------------------

interface Kid {
  id: string;
  animal_id: string;
  name: string;
  sex: string;
  date_of_birth: string;
  age_days: number;
  dam: string | null;
  dam_label: string | null;
  health_status: string;
  growth: {
    birth_weight_kg: string | null;
    latest_weight_kg: string | null;
    average_daily_gain_g: number | null;
  };
}

function Kids() {
  const { activeFarm } = useSession();
  const unit = activeFarm?.farm.weight_unit ?? 'kg';
  const list = useCursorList<Kid>(['breeding', 'kids'], '/kids', {});
  const rows = list.data?.pages.flatMap((p) => p.results) ?? [];
  if (list.isPending) return <LoadingState />;
  if (list.isError) return <ErrorState message={list.error.message} onRetry={() => void list.refetch()} />;
  if (!rows.length) return <EmptyState icon={Baby} title="No kids under 6 months" />;
  return (
    <section className={page.card}>
      <div className={page.tableWrap}>
        <table className={page.table}>
          <thead>
            <tr>
              <th scope="col">Kid</th>
              <th scope="col">Sex</th>
              <th scope="col">Age</th>
              <th scope="col">Dam</th>
              <th scope="col">Birth weight</th>
              <th scope="col">Latest weight</th>
              <th scope="col">Daily gain</th>
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((k) => (
              <tr key={k.id}>
                <td>
                  <Link to={`/livestock/${k.id}`} className={styles.animalLink}>
                    {k.animal_id} {k.name}
                  </Link>
                </td>
                <td>{k.sex === 'female' ? 'Female' : 'Male'}</td>
                <td>{k.age_days} days</td>
                <td>{k.dam_label ?? '—'}</td>
                <td>{formatWeight(k.growth.birth_weight_kg, unit)}</td>
                <td>{formatWeight(k.growth.latest_weight_kg, unit)}</td>
                <td>
                  {k.growth.average_daily_gain_g === null ? '—' : `${k.growth.average_daily_gain_g} g/day`}
                </td>
                <td>
                  <StatusBadge status={k.health_status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
