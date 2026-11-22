import { zodResolver } from '@hookform/resolvers/zod';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Camera } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { z } from 'zod';

import { api, ApiError } from '@/api/client';
import { ErrorState } from '@/components/ErrorState';
import { applyServerErrors, FormError, FormInput, FormSelect } from '@/components/forms';
import { LoadingState } from '@/components/LoadingState';
import page from '@/components/Page.module.css';
import { useToast } from '@/components/Toast';

import { keys, uploadPhoto, useAnimal, useGroups, useLocations, useParents, type Animal } from './api';
import { BREEDING_STATUSES, BREEDS, HEALTH_STATUSES, SOURCES, SPECIES } from './format';
import styles from './Livestock.module.css';

const today = () => new Date().toISOString().slice(0, 10);

const schema = z
  .object({
    animal_id: z.string().trim().min(1, 'Enter an animal ID.').max(30),
    ear_tag: z.string().trim().max(30),
    name: z.string().trim().max(80),
    species: z.string(),
    breed: z.string().trim().max(60),
    sex: z.enum(['female', 'male'], { errorMap: () => ({ message: 'Choose female or male.' }) }),
    age_mode: z.enum(['dob', 'estimate', 'unknown']),
    date_of_birth: z.string(),
    estimated_age_months: z.string(),
    acquisition_source: z.string(),
    acquisition_date: z.string(),
    acquisition_details: z.string().max(200),
    dam: z.string(),
    sire: z.string(),
    sire_details: z.string().max(120),
    location: z.string(),
    group: z.string(),
    health_status: z.string(),
    breeding_status: z.string(),
    colour_markings: z.string().max(120),
    current_condition: z.string(),
    previous_history: z.string(),
    remarks: z.string(),
  })
  .superRefine((v, ctx) => {
    if (v.age_mode === 'dob') {
      if (!v.date_of_birth)
        ctx.addIssue({ path: ['date_of_birth'], code: 'custom', message: 'Enter the birth date.' });
      else if (v.date_of_birth > today())
        ctx.addIssue({
          path: ['date_of_birth'],
          code: 'custom',
          message: 'The birth date cannot be in the future.',
        });
    }
    if (v.age_mode === 'estimate') {
      const n = Number(v.estimated_age_months);
      if (!v.estimated_age_months || !Number.isInteger(n) || n < 0 || n > 360)
        ctx.addIssue({
          path: ['estimated_age_months'],
          code: 'custom',
          message: 'Enter the age in whole months (0–360).',
        });
    }
    if (v.acquisition_date && v.acquisition_date > today())
      ctx.addIssue({
        path: ['acquisition_date'],
        code: 'custom',
        message: 'The date cannot be in the future.',
      });
  });
type Values = z.infer<typeof schema>;

const FIELDS = Object.keys(schema._def.schema.shape);

function toValues(a?: Animal, nextId = ''): Values {
  return {
    animal_id: a?.animal_id ?? nextId,
    ear_tag: a?.ear_tag ?? '',
    name: a?.name ?? '',
    species: a?.species ?? 'goat',
    breed: a?.breed ?? '',
    sex: (a?.sex as Values['sex']) ?? ('' as Values['sex']),
    age_mode: a ? (a.date_of_birth ? 'dob' : 'unknown') : 'dob',
    date_of_birth: a?.date_of_birth ?? '',
    estimated_age_months: '',
    acquisition_source: a?.acquisition_source ?? 'born_on_farm',
    acquisition_date: a?.acquisition_date ?? '',
    acquisition_details: a?.acquisition_details ?? '',
    dam: a?.dam?.id ?? '',
    sire: a?.sire?.id ?? '',
    sire_details: a?.sire_details ?? '',
    location: a?.location?.id ?? '',
    group: a?.group?.id ?? '',
    health_status: a?.health_status ?? 'healthy',
    breeding_status: a?.breeding_status ?? 'open',
    colour_markings: a?.colour_markings ?? '',
    current_condition: a?.current_condition ?? '',
    previous_history: a?.previous_history ?? '',
    remarks: a?.remarks ?? '',
  };
}

function toPayload(v: Values, editing: boolean) {
  const { age_mode, estimated_age_months, date_of_birth, ...rest } = v;
  const payload: Record<string, unknown> = {
    ...rest,
    acquisition_date: v.acquisition_date || null,
    dam: v.dam || null,
    sire: v.sire || null,
    location: v.location || null,
    group: v.group || null,
  };
  if (age_mode === 'dob') payload.date_of_birth = date_of_birth;
  else if (age_mode === 'estimate') payload.estimated_age_months = Number(estimated_age_months);
  else if (!editing) payload.date_of_birth = null;
  return payload;
}

export default function AnimalFormPage() {
  const { id } = useParams();
  if (id) return <EditAnimal id={id} />;
  return <NewAnimal />;
}

function NewAnimal() {
  const nextId = useQuery({
    queryKey: ['animals', 'next-id'],
    queryFn: () => api<{ animal_id: string }>('/animals/next-id'),
    staleTime: 0,
  });
  if (nextId.isPending) return <LoadingState />;
  return <AnimalForm initial={toValues(undefined, nextId.data?.animal_id ?? '')} />;
}

function EditAnimal({ id }: { id: string }) {
  const animal = useAnimal(id);
  if (animal.isPending) return <LoadingState />;
  if (animal.isError)
    return <ErrorState message={animal.error.message} onRetry={() => void animal.refetch()} />;
  return <AnimalForm animal={animal.data} initial={toValues(animal.data)} />;
}

function AnimalForm({ animal, initial }: { animal?: Animal; initial: Values }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const [photo, setPhoto] = useState<File | null>(null);
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: initial, mode: 'onTouched' });
  const { register, watch, setValue, formState } = form;
  const { errors, isSubmitting } = formState;
  const species = watch('species');
  const sex = watch('sex');
  const ageMode = watch('age_mode');
  const source = watch('acquisition_source');
  const locations = useLocations();
  const groups = useGroups();
  const dams = useParents('female', species);
  const sires = useParents('male', species);

  useEffect(() => {
    if (
      sex === 'male' &&
      ['open', 'served', 'pregnant', 'lactating', 'dry'].includes(form.getValues('breeding_status'))
    )
      setValue('breeding_status', 'breeding_male');
  }, [sex, form, setValue]);

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      const saved = animal
        ? await api<Animal>(`/animals/${animal.id}`, { method: 'PATCH', body: toPayload(values, true) })
        : await api<Animal>('/animals', { method: 'POST', body: toPayload(values, false) });
      let photoFailed = '';
      if (photo) {
        try {
          await uploadPhoto(saved.id, photo, true);
        } catch (err) {
          photoFailed =
            err instanceof ApiError
              ? (err.field('file')[0] ?? err.message)
              : 'The photo could not be uploaded.';
        }
      }
      await qc.invalidateQueries({ queryKey: keys.all });
      toast.success(animal ? `${saved.animal_id} is updated.` : `${saved.animal_id} is registered.`);
      if (photoFailed) toast.error(`Photo not saved: ${photoFailed}`);
      navigate(`/livestock/${saved.id}`, { replace: true });
    } catch (err) {
      applyServerErrors(err, form.setError, FIELDS);
    }
  });

  const opt = (list: readonly (readonly [string, string])[]) =>
    list.map(([v, l]) => (
      <option key={v} value={v}>
        {l}
      </option>
    ));
  const others = (rows: { id: string; animal_id: string; name?: string }[] | undefined) =>
    (rows ?? [])
      .filter((r) => r.id !== animal?.id)
      .map((r) => (
        <option key={r.id} value={r.id}>
          {r.animal_id}
          {r.name ? ` ${r.name}` : ''}
        </option>
      ));

  return (
    <form onSubmit={onSubmit} noValidate>
      <div className={page.header}>
        <div>
          <h2>{animal ? `Edit ${animal.animal_id}` : 'Register an animal'}</h2>
          <p>Fields marked * are required. Everything else can be added later.</p>
        </div>
      </div>
      <FormError message={errors.root?.server?.message} />

      <div style={{ display: 'grid', gap: 'var(--space-5)' }}>
        <section className={page.card}>
          <div className={page.cardBody}>
            <h3>Identification</h3>
            <div className={styles.grid3}>
              <FormInput
                label="Animal ID *"
                hint={animal ? undefined : 'Suggested from the farm prefix.'}
                error={errors.animal_id?.message}
                {...register('animal_id')}
              />
              <FormInput label="Ear tag" error={errors.ear_tag?.message} {...register('ear_tag')} />
              <FormInput
                label="Name"
                placeholder="e.g. Simba"
                error={errors.name?.message}
                {...register('name')}
              />
            </div>
            <div className={styles.grid3}>
              <FormSelect label="Species" {...register('species')}>
                {opt(SPECIES)}
              </FormSelect>
              <FormInput
                label="Breed"
                list="breed-options"
                error={errors.breed?.message}
                {...register('breed')}
              />
              <datalist id="breed-options">
                {(BREEDS[species] ?? []).map((b) => (
                  <option key={b} value={b} />
                ))}
              </datalist>
              <FormInput label="Colour / markings" {...register('colour_markings')} />
            </div>
            <fieldset
              className={styles.radioRow}
              style={{ border: 0, padding: 0, margin: 0 }}
              aria-invalid={errors.sex ? true : undefined}
            >
              <legend style={{ fontWeight: 600, fontSize: 'var(--text-sm)', marginBottom: 4 }}>Sex *</legend>
              <label>
                <input type="radio" value="female" {...register('sex')} /> Female
              </label>
              <label>
                <input type="radio" value="male" {...register('sex')} /> Male
              </label>
            </fieldset>
            {errors.sex && (
              <p style={{ margin: 0, color: 'var(--tone-red-fg)', fontSize: 'var(--text-sm)' }}>
                {errors.sex.message}
              </p>
            )}
          </div>
        </section>

        <section className={page.card}>
          <div className={page.cardBody}>
            <h3>Age and origin</h3>
            <fieldset className={styles.radioRow} style={{ border: 0, padding: 0, margin: 0 }}>
              <legend className="visually-hidden">How old is the animal?</legend>
              <label>
                <input type="radio" value="dob" {...register('age_mode')} /> I know the birth date
              </label>
              <label>
                <input type="radio" value="estimate" {...register('age_mode')} /> Estimate the age
              </label>
              {animal && (
                <label>
                  <input type="radio" value="unknown" {...register('age_mode')} /> Keep as it is
                </label>
              )}
            </fieldset>
            <div className={styles.grid3}>
              {ageMode === 'dob' && (
                <FormInput
                  label="Date of birth *"
                  type="date"
                  max={today()}
                  error={errors.date_of_birth?.message}
                  {...register('date_of_birth')}
                />
              )}
              {ageMode === 'estimate' && (
                <FormInput
                  label="Estimated age (months) *"
                  type="number"
                  inputMode="numeric"
                  min={0}
                  max={360}
                  hint="The age keeps counting from today."
                  error={errors.estimated_age_months?.message}
                  {...register('estimated_age_months')}
                />
              )}
              <FormSelect label="Source" {...register('acquisition_source')}>
                {opt(SOURCES)}
              </FormSelect>
              <FormInput
                label={source === 'born_on_farm' ? 'Date recorded' : 'Date acquired'}
                type="date"
                max={today()}
                error={errors.acquisition_date?.message}
                {...register('acquisition_date')}
              />
            </div>
            {source !== 'born_on_farm' && (
              <FormInput
                label="Where from"
                placeholder="Seller, market, price…"
                {...register('acquisition_details')}
              />
            )}
            <div className={styles.grid3}>
              <FormSelect label="Dam (mother)" error={errors.dam?.message} {...register('dam')}>
                <option value="">Unknown / not on this farm</option>
                {others(dams.data)}
              </FormSelect>
              <FormSelect label="Sire (father)" error={errors.sire?.message} {...register('sire')}>
                <option value="">Unknown / AI / outside buck</option>
                {others(sires.data)}
              </FormSelect>
              <FormInput
                label="Sire details"
                placeholder="AI straw code or owner"
                {...register('sire_details')}
              />
            </div>
          </div>
        </section>

        <section className={page.card}>
          <div className={page.cardBody}>
            <h3>Location and status</h3>
            <div className={styles.grid3}>
              <FormSelect label="Location" error={errors.location?.message} {...register('location')}>
                <option value="">Not set</option>
                {locations.data?.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name}
                  </option>
                ))}
              </FormSelect>
              <FormSelect label="Group" error={errors.group?.message} {...register('group')}>
                <option value="">Not set</option>
                {groups.data?.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                  </option>
                ))}
              </FormSelect>
              <span />
            </div>
            <div className={styles.grid3}>
              <FormSelect label="Health status" {...register('health_status')}>
                {opt(HEALTH_STATUSES)}
              </FormSelect>
              <FormSelect label="Breeding status" {...register('breeding_status')}>
                {opt(BREEDING_STATUSES)}
              </FormSelect>
              <span />
            </div>
          </div>
        </section>

        <section className={page.card}>
          <div className={page.cardBody}>
            <h3>Notes</h3>
            {(['current_condition', 'previous_history', 'remarks'] as const).map((f) => (
              <div key={f}>
                <label htmlFor={f} style={{ fontWeight: 600, fontSize: 'var(--text-sm)' }}>
                  {
                    {
                      current_condition: 'Current condition',
                      previous_history: 'Previous history',
                      remarks: 'Remarks',
                    }[f]
                  }
                </label>
                <textarea id={f} className={styles.textarea} {...register(f)} />
              </div>
            ))}
          </div>
        </section>

        {!animal && (
          <section className={page.card}>
            <div className={page.cardBody}>
              <h3>Photo</h3>
              <label className="btn btn-secondary" style={{ justifySelf: 'start' }}>
                <Camera size={18} aria-hidden="true" /> {photo ? 'Change photo' : 'Take or choose a photo'}
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  capture="environment"
                  className="visually-hidden"
                  onChange={(e) => setPhoto(e.target.files?.[0] ?? null)}
                />
              </label>
              {photo && <p className={page.sub}>{photo.name}</p>}
            </div>
          </section>
        )}
      </div>

      <div className={styles.formFooter}>
        <Link to={animal ? `/livestock/${animal.id}` : '/livestock'} className="btn btn-secondary">
          Cancel
        </Link>
        <button type="submit" className="btn btn-primary" disabled={isSubmitting}>
          {isSubmitting ? 'Saving…' : animal ? 'Save changes' : 'Register animal'}
        </button>
      </div>
    </form>
  );
}
