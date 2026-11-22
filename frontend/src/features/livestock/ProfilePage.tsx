import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Baby, Camera, HeartPulse, PawPrint, Scale, ShieldAlert, Wheat } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { z } from 'zod';

import { api, ApiError } from '@/api/client';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { applyServerErrors, FormError, FormInput, FormSelect } from '@/components/forms';
import { LoadingState } from '@/components/LoadingState';
import { Modal } from '@/components/Modal';
import page from '@/components/Page.module.css';
import { StatusBadge } from '@/components/StatusBadge';
import { useToast } from '@/components/Toast';
import { useSession } from '@/features/session/SessionContext';
import { recordType } from '@/features/health/config';
import { RecordList } from '@/features/health/Records';
import { can } from '@/routes/permissions';

import {
  keys,
  uploadPhoto,
  useAnimal,
  type Animal,
  type Photo,
  type TimelineEvent,
  type Weight,
} from './api';
import { EXIT_REASONS, formatAge, formatDate, formatWeight, labelOf, SOURCES, SPECIES } from './format';
import styles from './Livestock.module.css';

const TABS = [
  ['overview', 'Overview'],
  ['health', 'Health'],
  ['vaccinations', 'Vaccinations'],
  ['breeding', 'Breeding'],
  ['weights', 'Weight & Growth'],
  ['feeding', 'Feeding'],
  ['photos', 'Photos'],
  ['timeline', 'Timeline'],
] as const;
type Tab = (typeof TABS)[number][0];

export default function ProfilePage() {
  const { id = '' } = useParams();
  const animal = useAnimal(id);
  const [tab, setTab] = useState<Tab>('overview');
  const [weighing, setWeighing] = useState(false);

  if (animal.isPending) return <LoadingState />;
  if (animal.isError) {
    if (animal.error instanceof ApiError && animal.error.status === 404)
      return (
        <EmptyState
          title="Animal not found"
          message="It may have been removed, or it belongs to another farm."
        />
      );
    return <ErrorState message={animal.error.message} onRetry={() => void animal.refetch()} />;
  }
  const a = animal.data;

  return (
    <>
      <Hero animal={a} onWeigh={() => setWeighing(true)} />
      <div className={page.tabs} role="tablist" aria-label="Animal profile">
        {TABS.map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            id={`tab-${key}`}
            aria-selected={tab === key}
            aria-controls={`panel-${key}`}
            className={page.tab}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === 'overview' && <Overview animal={a} />}
        {tab === 'health' && (
          <div style={{ display: 'grid', gap: 'var(--space-5)' }}>
            <RecordList type={recordType('treatments')} animalId={a.id} />
            <RecordList type={recordType('observations')} animalId={a.id} />
            <RecordList type={recordType('vet-visits')} animalId={a.id} />
          </div>
        )}
        {tab === 'vaccinations' && (
          <div style={{ display: 'grid', gap: 'var(--space-5)' }}>
            <RecordList type={recordType('vaccinations')} animalId={a.id} />
            <RecordList type={recordType('dewormings')} animalId={a.id} />
          </div>
        )}
        {tab === 'breeding' && <BreedingTab animal={a} />}
        {tab === 'weights' && <WeightsTab animal={a} onWeigh={() => setWeighing(true)} />}
        {tab === 'feeding' && (
          <Later icon={Wheat} what="Feeding, supplements and nutrition assessments" phase={5} />
        )}
        {tab === 'photos' && <PhotosTab animal={a} />}
        {tab === 'timeline' && <TimelineTab animal={a} />}
      </div>
      <RecordWeightModal animal={a} open={weighing} onClose={() => setWeighing(false)} />
    </>
  );
}

function Later({ icon, what, phase }: { icon: typeof HeartPulse; what: string; phase: number }) {
  return (
    <EmptyState
      icon={icon}
      title="Nothing recorded yet"
      message={`${what} will appear here once that module is built (phase ${phase}).`}
    />
  );
}

// --- Header --------------------------------------------------------------------------------------------

function Hero({ animal: a, onWeigh }: { animal: Animal; onWeigh: () => void }) {
  const { role, activeFarm } = useSession();
  const qc = useQueryClient();
  const toast = useToast();
  const [exiting, setExiting] = useState(false);
  const photos = useQuery({
    queryKey: keys.photos(a.id),
    queryFn: () => api<Photo[]>(`/animals/${a.id}/photos`),
  });
  const primary = photos.data?.find((p) => p.is_primary) ?? photos.data?.[0];
  const unit = activeFarm?.farm.weight_unit ?? 'kg';
  const fmt = activeFarm?.farm.date_format ?? 'DD MMM YYYY';

  const reactivate = useMutation({
    mutationFn: () => api<Animal>(`/animals/${a.id}/reactivate`, { method: 'POST' }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: keys.all });
      toast.success(`${a.animal_id} is back in the herd.`);
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : 'Could not update.'),
  });

  return (
    <>
      {!a.is_active && (
        <div className={styles.banner} role="status">
          <span>
            <strong>Left the herd:</strong> {labelOf(EXIT_REASONS, a.exit_reason)} on{' '}
            {formatDate(a.exit_date, fmt)}
            {a.exit_notes ? `. ${a.exit_notes}` : ''}
          </span>
          {can(role, 'livestock', 'update') && (
            <button type="button" className={page.small} onClick={() => reactivate.mutate()}>
              Undo
            </button>
          )}
        </div>
      )}
      {a.withdrawal_until && (
        <div
          className={styles.banner}
          role="alert"
          style={{ background: 'var(--tone-red-bg)', color: 'var(--tone-red-fg)' }}
        >
          <span>
            <ShieldAlert size={18} aria-hidden="true" style={{ verticalAlign: 'middle' }} />{' '}
            <strong>Do not sell or milk until {formatDate(a.withdrawal_until, fmt)}</strong> (medicine
            withdrawal period).
          </span>
        </div>
      )}
      <section className={page.card} style={{ marginBottom: 'var(--space-5)' }}>
        <div className={styles.hero}>
          {primary ? (
            <img className={styles.heroPhoto} src={primary.file ?? ''} alt={`${a.animal_id} ${a.name}`} />
          ) : (
            <span className={styles.heroPhoto} aria-hidden="true">
              <PawPrint size={48} />
            </span>
          )}
          <div className={styles.heroMain}>
            <div className={styles.heroTitle}>
              <h2>
                {a.animal_id}
                {a.name ? ` · ${a.name}` : ''}
              </h2>
              <div className={styles.badges}>
                <StatusBadge status={a.health_status} />
                <StatusBadge status={a.breeding_status} />
                {a.is_kid && <StatusBadge status="kid" label="Kid" />}
              </div>
            </div>
            <dl className={styles.facts}>
              <Fact label="Ear tag" value={a.ear_tag || '—'} />
              <Fact
                label="Species / breed"
                value={`${labelOf(SPECIES, a.species)}${a.breed ? ` · ${a.breed}` : ''}`}
              />
              <Fact label="Sex" value={a.sex === 'female' ? 'Female' : 'Male'} />
              <Fact label="Age" value={formatAge(a.date_of_birth, a.dob_estimated)} />
              <Fact label="Location" value={a.location?.name ?? '—'} />
              <Fact label="Group" value={a.group?.name ?? '—'} />
              <Fact
                label="Latest weight"
                value={
                  a.latest_weight_kg
                    ? `${formatWeight(a.latest_weight_kg, unit)} (${formatDate(a.latest_weight_date, fmt)})`
                    : '—'
                }
              />
            </dl>
          </div>
          <div className={styles.heroActions}>
            {a.is_active && can(role, 'livestock', 'record_weight') && (
              <button type="button" className="btn btn-primary" onClick={onWeigh}>
                <Scale size={18} aria-hidden="true" /> Record weight
              </button>
            )}
            {can(role, 'livestock', 'update') && (
              <Link className="btn btn-secondary" to={`/livestock/${a.id}/edit`}>
                Edit
              </Link>
            )}
            {a.is_active && can(role, 'livestock', 'update') && (
              <button type="button" className="btn btn-secondary" onClick={() => setExiting(true)}>
                Sold / died / culled
              </button>
            )}
          </div>
        </div>
      </section>
      <ExitModal animal={a} open={exiting} onClose={() => setExiting(false)} />
    </>
  );
}

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

// --- Overview ------------------------------------------------------------------------------------------

function Overview({ animal: a }: { animal: Animal }) {
  const { activeFarm } = useSession();
  const fmt = activeFarm?.farm.date_format ?? 'DD MMM YYYY';
  const parent = (p: Animal['dam'], extra = '') =>
    p ? (
      <Link to={`/livestock/${p.id}`}>{`${p.animal_id}${p.name ? ` ${p.name}` : ''}`}</Link>
    ) : (
      extra || 'Unknown'
    );
  return (
    <div style={{ display: 'grid', gap: 'var(--space-5)' }}>
      <section className={page.card}>
        <div className={page.cardBody}>
          <h3>Details</h3>
          <dl className={styles.facts}>
            <Fact
              label="Date of birth"
              value={
                a.date_of_birth
                  ? `${formatDate(a.date_of_birth, fmt)}${a.dob_estimated ? ' (estimated)' : ''}`
                  : 'Unknown'
              }
            />
            <Fact label="Source" value={labelOf(SOURCES, a.acquisition_source)} />
            <Fact label="Date acquired / recorded" value={formatDate(a.acquisition_date, fmt)} />
            <Fact label="Where from" value={a.acquisition_details || '—'} />
            <Fact label="Dam (mother)" value={parent(a.dam)} />
            <Fact label="Sire (father)" value={parent(a.sire, a.sire_details)} />
            <Fact label="Colour / markings" value={a.colour_markings || '—'} />
            <Fact label="Offspring" value={a.offspring_count} />
            <Fact
              label="Registered"
              value={`${formatDate(a.created_at, fmt)}${a.created_by_name ? ` by ${a.created_by_name}` : ''}`}
            />
          </dl>
        </div>
      </section>
      <section className={page.card}>
        <div className={`${page.cardBody} ${styles.notes}`}>
          <h3>Notes</h3>
          {[
            ['Current condition', a.current_condition],
            ['Previous history', a.previous_history],
            ['Remarks', a.remarks],
          ].map(([label, text]) => (
            <div key={label}>
              <h4>{label}</h4>
              <p>{text || '—'}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function BreedingTab({ animal: a }: { animal: Animal }) {
  return (
    <section className={page.card}>
      <div className={page.cardBody}>
        <dl className={styles.facts}>
          <Fact label="Breeding status" value={<StatusBadge status={a.breeding_status} />} />
          <Fact label="Offspring on record" value={a.offspring_count} />
        </dl>
        <EmptyState
          icon={Baby}
          title="No matings recorded yet"
          message="Matings, pregnancy checks and births are added in phase 5."
        />
      </div>
    </section>
  );
}

// --- Weights -------------------------------------------------------------------------------------------

function WeightsTab({ animal, onWeigh }: { animal: Animal; onWeigh: () => void }) {
  const { activeFarm, role } = useSession();
  const qc = useQueryClient();
  const toast = useToast();
  const unit = activeFarm?.farm.weight_unit ?? 'kg';
  const fmt = activeFarm?.farm.date_format ?? 'DD MMM YYYY';
  const weights = useQuery({
    queryKey: keys.weights(animal.id),
    queryFn: () => api<Weight[]>(`/animals/${animal.id}/weights`),
  });

  const remove = async (w: Weight) => {
    try {
      await api(`/weights/${w.id}`, { method: 'DELETE' });
      await qc.invalidateQueries({ queryKey: keys.all });
      toast.success('Weight removed.');
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not remove.');
    }
  };

  if (weights.isPending) return <LoadingState />;
  if (weights.isError)
    return <ErrorState message={weights.error.message} onRetry={() => void weights.refetch()} />;
  if (weights.data.length === 0)
    return (
      <EmptyState
        icon={Scale}
        title="No weights yet"
        message="Record a weight to start the growth chart."
        action={
          animal.is_active && can(role, 'livestock', 'record_weight') ? (
            <button type="button" className="btn btn-primary" onClick={onWeigh}>
              Record weight
            </button>
          ) : undefined
        }
      />
    );

  const factor = unit === 'lb' ? 2.20462 : 1;
  const series = [...weights.data].reverse().map((w) => ({
    date: formatDate(w.date, fmt),
    weight: Number((Number(w.weight_kg) * factor).toFixed(1)),
  }));

  return (
    <div style={{ display: 'grid', gap: 'var(--space-5)' }}>
      <section className={page.card}>
        <div className={page.cardBody}>
          <h3>Growth</h3>
          <div className={styles.chart} role="img" aria-label={`Weight chart with ${series.length} records`}>
            <ResponsiveContainer>
              <LineChart data={series} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                <CartesianGrid stroke="#e2e8e2" strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                <YAxis unit={` ${unit}`} width={64} tick={{ fontSize: 12 }} />
                <Tooltip formatter={(v) => [`${v} ${unit}`, 'Weight']} />
                <Line type="monotone" dataKey="weight" stroke="#2E7D32" strokeWidth={3} dot={{ r: 4 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </section>
      <section className={page.card}>
        <div className={page.tableWrap}>
          <table className={page.table}>
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col">Weight</th>
                <th scope="col">Change</th>
                <th scope="col">Body condition</th>
                <th scope="col">Recorded by</th>
                <th scope="col">
                  <span className="visually-hidden">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {weights.data.map((w) => (
                <tr key={w.id}>
                  <td>{formatDate(w.date, fmt)}</td>
                  <td>{formatWeight(w.weight_kg, unit)}</td>
                  <td>
                    {w.gain_kg === null
                      ? '—'
                      : `${Number(w.gain_kg) >= 0 ? '+' : ''}${formatWeight(w.gain_kg, unit)}`}
                  </td>
                  <td>{w.body_condition_score ?? '—'}</td>
                  <td>{w.recorded_by ?? '—'}</td>
                  <td>
                    {can(role, 'livestock', 'delete') && (
                      <button
                        type="button"
                        className={`${page.small} ${page.danger}`}
                        onClick={() => void remove(w)}
                        aria-label={`Remove weight of ${formatDate(w.date, fmt)}`}
                      >
                        Remove
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

const weightSchema = z.object({
  weight_kg: z.coerce
    .number({ invalid_type_error: 'Enter the weight.' })
    .positive('Enter the weight.')
    .max(2000),
  date: z.string().min(1, 'Enter the date.'),
  body_condition_score: z.string(),
  notes: z.string().max(200),
});
type WeightValues = z.infer<typeof weightSchema>;

export function RecordWeightModal({
  animal,
  open,
  onClose,
}: {
  animal: Pick<Animal, 'id' | 'animal_id'>;
  open: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const { activeFarm } = useSession();
  const lb = activeFarm?.farm.weight_unit === 'lb';
  const form = useForm<WeightValues>({
    resolver: zodResolver(weightSchema),
    defaultValues: {
      weight_kg: '' as unknown as number,
      date: new Date().toISOString().slice(0, 10),
      body_condition_score: '',
      notes: '',
    },
  });
  const close = () => {
    form.reset();
    onClose();
  };
  const onSubmit = form.handleSubmit(async (v) => {
    try {
      const kg = lb ? v.weight_kg / 2.20462 : v.weight_kg;
      await api(`/animals/${animal.id}/weights`, {
        method: 'POST',
        body: {
          weight_kg: kg.toFixed(2),
          date: v.date,
          body_condition_score: v.body_condition_score || null,
          notes: v.notes,
        },
      });
      await qc.invalidateQueries({ queryKey: keys.all });
      toast.success(`Weight saved for ${animal.animal_id}.`);
      close();
    } catch (err) {
      applyServerErrors(err, form.setError, ['weight_kg', 'date', 'body_condition_score', 'notes']);
    }
  });
  return (
    <Modal
      title={`Record weight · ${animal.animal_id}`}
      open={open}
      onClose={close}
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={close}>
            Cancel
          </button>
          <button
            type="submit"
            form="weight-form"
            className="btn btn-primary"
            disabled={form.formState.isSubmitting}
          >
            Save weight
          </button>
        </>
      }
    >
      <form
        id="weight-form"
        onSubmit={onSubmit}
        noValidate
        style={{ display: 'grid', gap: 'var(--space-4)' }}
      >
        <FormError message={form.formState.errors.root?.server?.message} />
        <div className={page.grid2}>
          <FormInput
            label={`Weight (${lb ? 'lb' : 'kg'})`}
            type="number"
            inputMode="decimal"
            step="0.1"
            min="0"
            error={form.formState.errors.weight_kg?.message}
            {...form.register('weight_kg')}
          />
          <FormInput
            label="Date"
            type="date"
            max={new Date().toISOString().slice(0, 10)}
            error={form.formState.errors.date?.message}
            {...form.register('date')}
          />
        </div>
        <FormSelect
          label="Body condition score (optional)"
          error={form.formState.errors.body_condition_score?.message}
          {...form.register('body_condition_score')}
        >
          <option value="">Not scored</option>
          {['1', '1.5', '2', '2.5', '3', '3.5', '4', '4.5', '5'].map((s) => (
            <option key={s} value={s}>
              {s}
              {s === '1' ? ' (very thin)' : s === '3' ? ' (ideal)' : s === '5' ? ' (very fat)' : ''}
            </option>
          ))}
        </FormSelect>
        <FormInput label="Notes (optional)" {...form.register('notes')} />
      </form>
    </Modal>
  );
}

// --- Exit ----------------------------------------------------------------------------------------------

function ExitModal({ animal, open, onClose }: { animal: Animal; open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const [reason, setReason] = useState('sold');
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [notes, setNotes] = useState('');
  const [error, setError] = useState<string>();
  const save = useMutation({
    mutationFn: () =>
      api<Animal>(`/animals/${animal.id}/exit`, { method: 'POST', body: { reason, date, notes } }),
    onSuccess: async (a) => {
      await qc.invalidateQueries({ queryKey: keys.all });
      toast.success(`${a.animal_id} recorded as ${labelOf(EXIT_REASONS, a.exit_reason).toLowerCase()}.`);
      onClose();
      navigate(`/livestock/${a.id}`);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : 'Could not save.'),
  });
  return (
    <Modal
      title={`${animal.animal_id} left the herd`}
      open={open}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => save.mutate()}
            disabled={save.isPending}
          >
            Save
          </button>
        </>
      }
    >
      <FormError message={error} />
      <p style={{ margin: 0 }}>The animal leaves the register, but its records and history stay.</p>
      <div className={page.grid2}>
        <FormSelect label="What happened" value={reason} onChange={(e) => setReason(e.target.value)}>
          {EXIT_REASONS.map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </FormSelect>
        <FormInput
          label="Date"
          type="date"
          max={new Date().toISOString().slice(0, 10)}
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
      </div>
      <FormInput
        label="Notes"
        placeholder={reason === 'sold' ? 'Buyer, price…' : 'Cause…'}
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />
    </Modal>
  );
}

// --- Photos --------------------------------------------------------------------------------------------

function PhotosTab({ animal }: { animal: Animal }) {
  const { role } = useSession();
  const qc = useQueryClient();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const photos = useQuery({
    queryKey: keys.photos(animal.id),
    queryFn: () => api<Photo[]>(`/animals/${animal.id}/photos`),
  });
  const refresh = () => qc.invalidateQueries({ queryKey: keys.all });

  const add = async (file: File) => {
    setBusy(true);
    try {
      await uploadPhoto(animal.id, file);
      await refresh();
      toast.success('Photo added.');
    } catch (err) {
      toast.error(err instanceof ApiError ? (err.field('file')[0] ?? err.message) : 'Upload failed.');
    } finally {
      setBusy(false);
    }
  };
  const act = async (photo: Photo, action: 'primary' | 'delete') => {
    try {
      await api(action === 'primary' ? `/animal-photos/${photo.id}/primary` : `/animal-photos/${photo.id}`, {
        method: action === 'primary' ? 'POST' : 'DELETE',
      });
      await refresh();
      toast.success(action === 'primary' ? 'Profile photo changed.' : 'Photo removed.');
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Something went wrong.');
    }
  };

  if (photos.isPending) return <LoadingState />;
  if (photos.isError)
    return <ErrorState message={photos.error.message} onRetry={() => void photos.refetch()} />;
  return (
    <section className={page.card}>
      <div className={page.cardBody}>
        {can(role, 'livestock', 'create') && (
          <label className="btn btn-primary" style={{ justifySelf: 'start' }} aria-disabled={busy}>
            <Camera size={18} aria-hidden="true" /> {busy ? 'Uploading…' : 'Add photo'}
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              capture="environment"
              className="visually-hidden"
              disabled={busy}
              onChange={(e) => {
                const f = e.target.files?.[0];
                e.target.value = '';
                if (f) void add(f);
              }}
            />
          </label>
        )}
        {photos.data.length === 0 ? (
          <EmptyState
            icon={Camera}
            title="No photos yet"
            message="Photos help staff recognise the animal in the field."
          />
        ) : (
          <div className={styles.gallery}>
            {photos.data.map((p) => (
              <figure key={p.id} className={styles.photoCard} style={{ margin: 0 }}>
                <a href={p.file ?? '#'} target="_blank" rel="noreferrer">
                  <img
                    src={p.thumbnail ?? ''}
                    alt={p.caption || `Photo of ${animal.animal_id}`}
                    loading="lazy"
                  />
                </a>
                <div>
                  {p.is_primary ? <StatusBadge status="active" label="Profile photo" /> : null}
                  {!p.is_primary && can(role, 'livestock', 'update') && (
                    <button type="button" className={page.small} onClick={() => void act(p, 'primary')}>
                      Use as profile
                    </button>
                  )}
                  {can(role, 'livestock', 'delete') && (
                    <button
                      type="button"
                      className={`${page.small} ${page.danger}`}
                      onClick={() => void act(p, 'delete')}
                    >
                      Remove
                    </button>
                  )}
                </div>
              </figure>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

// --- Timeline ------------------------------------------------------------------------------------------

function TimelineTab({ animal }: { animal: Animal }) {
  const { activeFarm } = useSession();
  const fmt = activeFarm?.farm.date_format ?? 'DD MMM YYYY';
  const events = useQuery({
    queryKey: keys.timeline(animal.id),
    queryFn: () => api<TimelineEvent[]>(`/animals/${animal.id}/timeline`),
  });
  if (events.isPending) return <LoadingState />;
  if (events.isError)
    return <ErrorState message={events.error.message} onRetry={() => void events.refetch()} />;
  return (
    <section className={page.card}>
      <div className={page.cardBody}>
        <ol className={styles.timeline}>
          {events.data.map((e, i) => (
            <li key={`${e.at}-${i}`}>
              <span className={styles.dot} aria-hidden="true" />
              <div>
                <strong>{e.title}</strong>
                {e.detail && <div className={page.sub}>{e.detail}</div>}
                <div className={styles.when}>
                  {formatDate(e.at, fmt)}
                  {e.by ? ` · ${e.by}` : ''}
                </div>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
