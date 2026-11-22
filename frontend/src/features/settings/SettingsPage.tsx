import { zodResolver } from '@hookform/resolvers/zod';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { lazy, Suspense, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { NavLink, Navigate, Route, Routes } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';

import { api, ApiError, type Schemas, type Session } from '@/api/client';
import { ErrorState } from '@/components/ErrorState';
import {
  applyServerErrors,
  Checkbox,
  CheckboxGroup,
  FormError,
  FormInput,
  FormSelect,
  PasswordInput,
  PasswordStrength,
} from '@/components/forms';
import { LoadingState } from '@/components/LoadingState';
import page from '@/components/Page.module.css';
import { useToast } from '@/components/Toast';
import { CountrySelect, RegionField, useCountries } from '@/features/auth/countries';
import { HERD_SIZES, LIVESTOCK } from '@/features/auth/SignupPage';
import { optionalEmail, optionalPhone, password } from '@/features/auth/schemas';
import { downloadFile } from '@/features/reports/api';
import { useSession } from '@/features/session/SessionContext';
import { VerifyPhoneModal } from '@/features/session/VerifyPhoneModal';
import { can } from '@/routes/permissions';

type Farm = Schemas['Farm'];
const NotificationSettingsSection = lazy(() => import('@/features/notifications/NotificationSettings'));

export default function SettingsPage() {
  const { role } = useSession();
  const isAdmin = can(role, 'settings');
  const tabs = [
    ...(isAdmin ? [['farm', 'Farm profile']] : []),
    ['profile', 'My profile'],
    ['notifications', 'Notifications'],
    ...(isAdmin ? [['system', 'System']] : []),
  ] as const;

  return (
    <>
      <div className={page.header}>
        <div>
          <h2>Settings</h2>
          <p>
            {isAdmin ? 'Your farm, your profile and how the system behaves.' : 'Your profile and password.'}
          </p>
        </div>
      </div>
      <nav className={page.tabs} aria-label="Settings sections">
        {tabs.map(([path, label]) => (
          <NavLink key={path} to={`/settings/${path}`} className={page.tab}>
            {label}
          </NavLink>
        ))}
      </nav>
      <Routes>
        <Route index element={<Navigate to={isAdmin ? 'farm' : 'profile'} replace />} />
        <Route path="profile" element={<ProfileSection />} />
        <Route
          path="notifications"
          element={
            <Suspense fallback={<LoadingState />}>
              <NotificationSettingsSection />
            </Suspense>
          }
        />
        {isAdmin && <Route path="farm" element={<FarmSection />} />}
        {isAdmin && <Route path="system" element={<SystemSection />} />}
        <Route path="*" element={<Navigate to="/settings/profile" replace />} />
      </Routes>
    </>
  );
}

function useFarm() {
  return useQuery({ queryKey: ['farm'], queryFn: () => api<Farm>('/farm') });
}

async function uploadImage(path: string, file: File) {
  const body = new FormData();
  body.append('file', file);
  return api<unknown>(path, { method: 'POST', body });
}

function ImagePicker({
  label,
  current,
  onPick,
}: {
  label: string;
  current?: string | null;
  onPick: (f: File) => Promise<void>;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
      <span
        style={{
          width: 72,
          height: 72,
          borderRadius: 'var(--radius-md)',
          background: 'var(--color-primary-50)',
          overflow: 'hidden',
          display: 'grid',
          placeItems: 'center',
          flexShrink: 0,
        }}
      >
        {current ? (
          <img src={current} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        ) : null}
      </span>
      <div>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={busy}
          onClick={() => input.current?.click()}
        >
          {busy ? 'Uploading…' : label}
        </button>
        <p className={page.sub}>JPG, PNG or WebP, up to 10 MB. Location data is removed.</p>
        <input
          ref={input}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          capture="environment"
          hidden
          onChange={async (e) => {
            const file = e.target.files?.[0];
            e.target.value = '';
            if (!file) return;
            setBusy(true);
            try {
              await onPick(file);
            } finally {
              setBusy(false);
            }
          }}
        />
      </div>
    </div>
  );
}

// --- Farm profile -----------------------------------------------------------------------------------

const farmSchema = z.object({
  name: z.string().trim().min(2, 'Enter the farm name.'),
  location: z.string(),
  country: z.string(),
  county: z.string(),
  phone: optionalPhone,
  email: optionalEmail,
  description: z.string(),
  herd_size_band: z.string(),
  livestock_types: z.array(z.string()),
  animal_id_prefix: z.string().trim().min(1, 'Enter a prefix, e.g. YPA.').max(10),
});
type FarmValues = z.infer<typeof farmSchema>;

function FarmSection() {
  const farm = useFarm();
  if (farm.isPending) return <LoadingState />;
  if (farm.isError) return <ErrorState message={farm.error.message} onRetry={() => void farm.refetch()} />;
  return <FarmForm farm={farm.data} />;
}

function FarmForm({ farm }: { farm: Farm }) {
  const countries = useCountries();
  const qc = useQueryClient();
  const toast = useToast();
  const { refetchFarms } = useSession();
  const form = useForm<FarmValues>({
    resolver: zodResolver(farmSchema),
    defaultValues: {
      name: farm.name,
      location: farm.location ?? '',
      country: farm.country ?? 'UG',
      county: farm.county ?? '',
      phone: farm.phone ?? '',
      email: farm.email ?? '',
      description: farm.description ?? '',
      herd_size_band: farm.herd_size_band ?? '',
      livestock_types: farm.livestock_types ?? [],
      animal_id_prefix: farm.animal_id_prefix ?? '',
    },
  });
  const { errors, isSubmitting, isDirty } = form.formState;

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      const saved = await api<Farm>('/farm', { method: 'PATCH', body: values });
      qc.setQueryData(['farm'], saved);
      refetchFarms();
      form.reset(form.getValues());
      toast.success('Farm profile saved.');
    } catch (err) {
      applyServerErrors(err, form.setError, Object.keys(farmSchema.shape));
    }
  });

  return (
    <form className={page.card} onSubmit={onSubmit} noValidate>
      <div className={page.cardBody}>
        <FormError message={errors.root?.server?.message} />
        <ImagePicker
          label="Change logo"
          current={farm.logo}
          onPick={async (file) => {
            try {
              await uploadImage('/farm/logo', file);
              await qc.invalidateQueries({ queryKey: ['farm'] });
              refetchFarms();
              toast.success('Logo updated.');
            } catch (err) {
              toast.error(err instanceof ApiError ? (err.field('file')[0] ?? err.message) : 'Upload failed.');
            }
          }}
        />
        <div className={page.grid2}>
          <FormInput label="Farm name" error={errors.name?.message} {...form.register('name')} />
          <FormInput
            label="Animal ID prefix"
            hint="New animals get IDs like YPA-021."
            error={errors.animal_id_prefix?.message}
            {...form.register('animal_id_prefix')}
          />
        </div>
        <div className={page.grid2}>
          <FormInput label="Location" placeholder="Town or village" {...form.register('location')} />
        </div>
        <div className={page.grid2}>
          {countries.data && (
            <CountrySelect
              countries={countries.data}
              value={form.watch('country')}
              onChange={(code) => {
                form.setValue('country', code, { shouldDirty: true });
                form.setValue('county', '', { shouldDirty: true });
              }}
              error={errors.country?.message}
            />
          )}
          {countries.data && (
            <RegionField
              country={form.watch('country')}
              countries={countries.data}
              value={form.watch('county')}
              onChange={(v) => form.setValue('county', v, { shouldDirty: true })}
              error={errors.county?.message}
            />
          )}
        </div>
        <div className={page.grid2}>
          <FormInput
            label="Farm phone"
            type="tel"
            error={errors.phone?.message}
            {...form.register('phone')}
          />
          <FormInput
            label="Farm email"
            type="email"
            error={errors.email?.message}
            {...form.register('email')}
          />
        </div>
        <FormSelect label="Herd size" {...form.register('herd_size_band')}>
          <option value="">Not set</option>
          {HERD_SIZES.map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </FormSelect>
        <CheckboxGroup legend="Livestock kept" error={errors.livestock_types?.message}>
          {LIVESTOCK.map(([v, l]) => (
            <Checkbox key={v} label={l} value={v} {...form.register('livestock_types')} />
          ))}
        </CheckboxGroup>
        <div>
          <label htmlFor="farm-description" style={{ fontWeight: 600, fontSize: 'var(--text-sm)' }}>
            Description
          </label>
          <textarea
            id="farm-description"
            rows={3}
            style={{
              width: '100%',
              marginTop: 4,
              padding: 8,
              borderRadius: 10,
              border: '1px solid #c9d3c9',
              font: 'inherit',
            }}
            {...form.register('description')}
          />
        </div>
        <div className={page.formActions}>
          <button type="submit" className="btn btn-primary" disabled={isSubmitting || !isDirty}>
            Save changes
          </button>
        </div>
      </div>
    </form>
  );
}

// --- System -----------------------------------------------------------------------------------------

const TIMEZONES = [
  'Africa/Kampala',
  'Africa/Nairobi',
  'Africa/Dar_es_Salaam',
  'Africa/Kigali',
  'Africa/Addis_Ababa',
  'Africa/Lagos',
  'Africa/Johannesburg',
  'UTC',
];
const DATE_FORMATS = ['DD MMM YYYY', 'DD/MM/YYYY', 'MM/DD/YYYY', 'YYYY-MM-DD'];
const CURRENCIES = ['UGX', 'KES', 'TZS', 'RWF', 'ETB', 'USD'];
const MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];

const systemSchema = z.object({
  timezone: z.string(),
  date_format: z.string(),
  currency: z.string(),
  weight_unit: z.string(),
  language: z.string(),
  default_calendar_view: z.string(),
  financial_year_start: z.coerce.number(),
});
type SystemValues = z.infer<typeof systemSchema>;

function SystemSection() {
  const farm = useFarm();
  if (farm.isPending) return <LoadingState />;
  if (farm.isError) return <ErrorState message={farm.error.message} onRetry={() => void farm.refetch()} />;
  return (
    <>
      <SystemForm farm={farm.data} />
      <DataExportCard />
    </>
  );
}

function DataExportCard() {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try {
      await downloadFile('/farm/export', {}, 'farm-data.zip');
      toast.success('Farm data downloaded.');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Export failed.');
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className={page.card}>
      <div className={page.cardBody}>
        <h3>Export all farm data</h3>
        <p className={page.note}>
          A ZIP file with one spreadsheet (CSV) per kind of record: animals, health, breeding, feeding, tasks
          and users. Keep it as a backup or to move your data elsewhere.
        </p>
      </div>
      <div className={page.formActions}>
        <button type="button" className="btn btn-secondary" onClick={() => void run()} disabled={busy}>
          {busy ? 'Preparing…' : 'Export all farm data'}
        </button>
      </div>
    </section>
  );
}

function SystemForm({ farm }: { farm: Farm }) {
  const qc = useQueryClient();
  const toast = useToast();
  const { refetchFarms } = useSession();
  const form = useForm<SystemValues>({
    resolver: zodResolver(systemSchema),
    defaultValues: {
      timezone: farm.timezone ?? 'Africa/Kampala',
      date_format: farm.date_format ?? 'DD MMM YYYY',
      currency: farm.currency ?? 'UGX',
      weight_unit: farm.weight_unit ?? 'kg',
      language: farm.language ?? 'en',
      default_calendar_view: farm.default_calendar_view ?? 'month',
      financial_year_start: farm.financial_year_start ?? 1,
    },
  });
  const { errors, isSubmitting, isDirty } = form.formState;
  const onSubmit = form.handleSubmit(async (values) => {
    try {
      const saved = await api<Farm>('/farm', { method: 'PATCH', body: values });
      qc.setQueryData(['farm'], saved);
      refetchFarms();
      form.reset(form.getValues());
      toast.success('System settings saved.');
    } catch (err) {
      applyServerErrors(err, form.setError, Object.keys(systemSchema.shape));
    }
  });
  const withCurrent = (list: string[], value?: string | null) =>
    value && !list.includes(value) ? [value, ...list] : list;

  return (
    <form className={page.card} onSubmit={onSubmit} noValidate>
      <div className={page.cardBody}>
        <FormError message={errors.root?.server?.message} />
        <div className={page.grid2}>
          <FormSelect label="Time zone" error={errors.timezone?.message} {...form.register('timezone')}>
            {withCurrent(TIMEZONES, farm.timezone).map((z) => (
              <option key={z} value={z}>
                {z.replace(/_/g, ' ')}
              </option>
            ))}
          </FormSelect>
          <FormSelect label="Date format" {...form.register('date_format')}>
            {DATE_FORMATS.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </FormSelect>
        </div>
        <div className={page.grid2}>
          <FormSelect label="Currency" error={errors.currency?.message} {...form.register('currency')}>
            {withCurrent(CURRENCIES, farm.currency).map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </FormSelect>
          <FormSelect label="Weight unit" {...form.register('weight_unit')}>
            <option value="kg">Kilograms (kg)</option>
            <option value="lb">Pounds (lb)</option>
          </FormSelect>
        </div>
        <div className={page.grid2}>
          <FormSelect label="Farm language" {...form.register('language')}>
            <option value="en">English</option>
            <option value="sw">Kiswahili</option>
          </FormSelect>
          <FormSelect label="Default calendar view" {...form.register('default_calendar_view')}>
            <option value="month">Month</option>
            <option value="week">Week</option>
            <option value="day">Day</option>
            <option value="agenda">Agenda</option>
          </FormSelect>
        </div>
        <FormSelect
          label="Financial year starts in"
          error={errors.financial_year_start?.message}
          {...form.register('financial_year_start')}
        >
          {MONTHS.map((m, i) => (
            <option key={m} value={i + 1}>
              {m}
            </option>
          ))}
        </FormSelect>
        <div className={page.formActions}>
          <button type="submit" className="btn btn-primary" disabled={isSubmitting || !isDirty}>
            Save changes
          </button>
        </div>
      </div>
    </form>
  );
}

// --- My profile -------------------------------------------------------------------------------------

const profileSchema = z.object({
  first_name: z.string().trim().min(1, 'Enter your first name.'),
  last_name: z.string().trim().min(1, 'Enter your last name.'),
  email: optionalEmail,
  phone: optionalPhone,
  language: z.string(),
});
type ProfileValues = z.infer<typeof profileSchema>;

const passwordSchema = z
  .object({
    current_password: z.string().min(1, 'Enter your current password.'),
    password,
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, { path: ['confirm'], message: 'The passwords do not match.' });
type PasswordValues = z.infer<typeof passwordSchema>;

function ProfileSection() {
  const { user, setUser, startSession } = useSession();
  const { i18n } = useTranslation();
  const toast = useToast();
  const [verifyOpen, setVerifyOpen] = useState(false);
  const form = useForm<ProfileValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: {
      first_name: user?.first_name ?? '',
      last_name: user?.last_name ?? '',
      email: user?.email ?? '',
      phone: user?.phone ?? '',
      language: user?.language ?? 'en',
    },
  });
  const pw = useForm<PasswordValues>({
    resolver: zodResolver(passwordSchema),
    defaultValues: { current_password: '', password: '', confirm: '' },
  });
  if (!user) return null;

  const onSave = form.handleSubmit(async (values) => {
    try {
      const me = await api<Schemas['Me']>('/me', { method: 'PATCH', body: values });
      setUser(me);
      void i18n.changeLanguage(me.language ?? 'en');
      form.reset({ ...values, phone: me.phone, email: me.email });
      toast.success(
        me.email !== user.email
          ? 'Profile saved. Check your email to confirm the new address.'
          : 'Profile saved.',
      );
    } catch (err) {
      applyServerErrors(err, form.setError, Object.keys(profileSchema.shape));
    }
  });

  const onChangePassword = pw.handleSubmit(async ({ current_password, password: newPw }) => {
    try {
      const session = await api<Session>('/me/password', {
        method: 'POST',
        body: { current_password, password: newPw },
      });
      startSession(session);
      pw.reset();
      toast.success('Password changed. Other devices have been logged out.');
    } catch (err) {
      applyServerErrors(err, pw.setError, ['current_password', 'password']);
    }
  });

  const badge = (ok: boolean) => (
    <span className={ok ? page.verified : page.unverified}>{ok ? 'Confirmed' : 'Not confirmed'}</span>
  );

  return (
    <div style={{ display: 'grid', gap: 'var(--space-5)' }}>
      <form className={page.card} onSubmit={onSave} noValidate>
        <div className={page.cardBody}>
          <h3>My profile</h3>
          <FormError message={form.formState.errors.root?.server?.message} />
          <ImagePicker
            label="Change photo"
            current={user.photo}
            onPick={async (file) => {
              try {
                const me = (await uploadImage('/me/photo', file)) as Schemas['Me'];
                setUser(me);
                toast.success('Photo updated.');
              } catch (err) {
                toast.error(
                  err instanceof ApiError ? (err.field('file')[0] ?? err.message) : 'Upload failed.',
                );
              }
            }}
          />
          <div className={page.grid2}>
            <FormInput
              label="First name"
              error={form.formState.errors.first_name?.message}
              {...form.register('first_name')}
            />
            <FormInput
              label="Last name"
              error={form.formState.errors.last_name?.message}
              {...form.register('last_name')}
            />
          </div>
          <div className={page.grid2}>
            <FormInput
              label="Email"
              type="email"
              hint={badge(user.email_verified ?? false)}
              error={form.formState.errors.email?.message}
              {...form.register('email')}
            />
            <FormInput
              label="Mobile number"
              type="tel"
              hint={
                <>
                  {badge(user.phone_verified ?? false)}{' '}
                  {user.phone && !user.phone_verified && (
                    <button type="button" className={page.small} onClick={() => setVerifyOpen(true)}>
                      Enter code
                    </button>
                  )}
                </>
              }
              error={form.formState.errors.phone?.message}
              {...form.register('phone')}
            />
          </div>
          <FormSelect label="Language" {...form.register('language')}>
            <option value="en">English</option>
            <option value="sw">Kiswahili</option>
          </FormSelect>
          <p className={page.sub}>Username: {user.username}</p>
          <div className={page.formActions}>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={form.formState.isSubmitting || !form.formState.isDirty}
            >
              Save profile
            </button>
          </div>
        </div>
      </form>

      <form className={page.card} onSubmit={onChangePassword} noValidate>
        <div className={page.cardBody}>
          <h3>Change password</h3>
          <FormError message={pw.formState.errors.root?.server?.message} />
          <PasswordInput
            label="Current password"
            autoComplete="current-password"
            error={pw.formState.errors.current_password?.message}
            {...pw.register('current_password')}
          />
          <div className={page.grid2}>
            <PasswordInput
              label="New password"
              autoComplete="new-password"
              hint={<PasswordStrength password={pw.watch('password')} />}
              error={pw.formState.errors.password?.message}
              {...pw.register('password')}
            />
            <PasswordInput
              label="Repeat new password"
              autoComplete="new-password"
              error={pw.formState.errors.confirm?.message}
              {...pw.register('confirm')}
            />
          </div>
          <div className={page.formActions}>
            <button type="submit" className="btn btn-primary" disabled={pw.formState.isSubmitting}>
              Change password
            </button>
          </div>
        </div>
      </form>
      <VerifyPhoneModal open={verifyOpen} onClose={() => setVerifyOpen(false)} />
    </div>
  );
}
