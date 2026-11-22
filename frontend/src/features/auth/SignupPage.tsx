import { zodResolver } from '@hookform/resolvers/zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link, useNavigate } from 'react-router-dom';
import { z } from 'zod';

import { api, ApiError, type Session } from '@/api/client';
import {
  Checkbox,
  CheckboxGroup,
  FormError,
  FormInput,
  FormSelect,
  PasswordInput,
  PasswordStrength,
} from '@/components/forms';
import { useSession } from '@/features/session/SessionContext';

import { AuthLayout } from './AuthLayout';
import styles from './AuthLayout.module.css';
import { CountrySelect, RegionField, useCountries } from './countries';
import { email, password, phone } from './schemas';

export const LIVESTOCK = [
  ['goats', 'Goats'],
  ['sheep', 'Sheep'],
  ['dairy_cattle', 'Dairy cattle'],
  ['beef_cattle', 'Beef cattle'],
  ['poultry', 'Poultry'],
] as const;

export const HERD_SIZES = [
  ['1-20', '1–20 animals'],
  ['21-50', '21–50 animals'],
  ['51-100', '51–100 animals'],
  ['101-500', '101–500 animals'],
  ['500+', 'More than 500 animals'],
] as const;

const ROLES_ON_FARM = ['Owner', 'Farm manager', 'Veterinary officer', 'Family member', 'Other'];

const schema = z.object({
  first_name: z.string().trim().min(1, 'Enter your first name.'),
  last_name: z.string().trim().min(1, 'Enter your last name.'),
  email,
  phone,
  password,
  country: z.string(),
  farm_name: z.string().trim().min(2, 'Enter your farm name.'),
  county: z.string(),
  herd_size_band: z.string(),
  livestock_types: z.array(z.string()).min(1, 'Choose at least one type of livestock.'),
  job_title: z.string(),
  alert_channels: z.array(z.string()),
});
type Values = z.infer<typeof schema>;

const STEP_FIELDS: (keyof Values)[][] = [
  ['country', 'first_name', 'last_name', 'email', 'phone', 'password'],
  ['farm_name', 'county', 'herd_size_band', 'livestock_types', 'job_title'],
  ['alert_channels'],
];
const STEP_TITLES = ['Your account', 'Your farm', 'Alerts'];

export function SignupPage() {
  const { startSession } = useSession();
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const countries = useCountries();
  const prefixOf = (code: string) => countries.data?.find((c) => c.code === code)?.phone_prefix ?? '+';
  const {
    register,
    handleSubmit,
    trigger,
    watch,
    setValue,
    getValues,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    mode: 'onTouched',
    defaultValues: {
      first_name: '',
      last_name: '',
      email: '',
      phone: '+256 ',
      country: 'UG',
      password: '',
      farm_name: '',
      county: '',
      herd_size_band: '',
      livestock_types: ['goats'],
      job_title: 'Owner',
      alert_channels: ['whatsapp', 'email'],
    },
  });

  const country = watch('country');

  const next = async () => {
    if (await trigger(STEP_FIELDS[step])) setStep((s) => s + 1);
  };

  const onSubmit = handleSubmit(async (values) => {
    try {
      const session = await api<Session>('/auth/signup', { method: 'POST', body: values, noRefresh: true });
      startSession(session);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        // Go back to the first step that has an error.
        const bad = STEP_FIELDS.findIndex((fields) => fields.some((f) => err.errors[f]));
        for (const [key, messages] of Object.entries(err.errors)) {
          if (key in schema.shape) setError(key as keyof Values, { message: messages.join(' ') });
          else setError('root.server', { message: messages.join(' ') });
        }
        if (bad >= 0) setStep(bad);
      } else {
        setError('root.server', {
          message: 'Could not reach Smart Farm. Check your connection and try again.',
        });
      }
    }
  });

  return (
    <AuthLayout
      title="Create an account for your farm"
      subtitle={`Step ${step + 1} of 3: ${STEP_TITLES[step]}`}
      wide
    >
      <ol className={styles.steps} aria-label="Sign-up steps">
        {STEP_TITLES.map((t, i) => (
          <li key={t} aria-current={i === step ? 'step' : undefined} className={i < step ? styles.done : ''}>
            {i + 1}. {t}
          </li>
        ))}
      </ol>
      <form
        className={styles.form}
        onSubmit={(e) => {
          if (step < 2) {
            e.preventDefault();
            void next();
          } else void onSubmit(e);
        }}
        noValidate
      >
        <FormError message={errors.root?.server?.message} />

        {step === 0 && (
          <>
            {countries.data && (
              <CountrySelect
                countries={countries.data}
                value={country}
                onChange={(code) => {
                  const old = prefixOf(country);
                  setValue('country', code);
                  setValue('county', '');
                  // Swap the phone's country code if the user hasn't typed a number yet.
                  const current = getValues('phone').trim();
                  if (!current || current === old) setValue('phone', `${prefixOf(code)} `);
                }}
              />
            )}
            <div className={styles.grid2}>
              <FormInput
                label="First name"
                autoComplete="given-name"
                error={errors.first_name?.message}
                {...register('first_name')}
              />
              <FormInput
                label="Last name"
                autoComplete="family-name"
                error={errors.last_name?.message}
                {...register('last_name')}
              />
            </div>
            <FormInput
              label="Email"
              type="email"
              autoComplete="email"
              error={errors.email?.message}
              {...register('email')}
            />
            <FormInput
              label="Mobile number"
              type="tel"
              autoComplete="tel"
              hint="We send a 6-digit code to confirm it. You can type it as 0772 123 456."
              error={errors.phone?.message}
              {...register('phone')}
            />
            <PasswordInput
              label="Password"
              autoComplete="new-password"
              hint={<PasswordStrength password={watch('password')} />}
              error={errors.password?.message}
              {...register('password')}
            />
          </>
        )}

        {step === 1 && (
          <>
            <FormInput
              label="Farm name"
              placeholder="e.g. YPA FARM"
              error={errors.farm_name?.message}
              {...register('farm_name')}
            />
            <div className={styles.grid2}>
              {countries.data && (
                <RegionField
                  country={country}
                  countries={countries.data}
                  value={watch('county')}
                  onChange={(v) => setValue('county', v)}
                  error={errors.county?.message}
                />
              )}
              <FormSelect label="Herd size" {...register('herd_size_band')}>
                <option value="">Choose…</option>
                {HERD_SIZES.map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </FormSelect>
            </div>
            <CheckboxGroup legend="Livestock you keep" error={errors.livestock_types?.message}>
              {LIVESTOCK.map(([v, l]) => (
                <Checkbox key={v} label={l} value={v} {...register('livestock_types')} />
              ))}
            </CheckboxGroup>
            <FormSelect label="Your role on the farm" {...register('job_title')}>
              {ROLES_ON_FARM.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </FormSelect>
          </>
        )}

        {step === 2 && (
          <CheckboxGroup legend="How should we send you alerts?">
            <Checkbox label="In-app (always on)" checked disabled readOnly />
            <Checkbox label="WhatsApp" value="whatsapp" {...register('alert_channels')} />
            <Checkbox label="SMS" value="sms" {...register('alert_channels')} />
            <Checkbox label="Email" value="email" {...register('alert_channels')} />
          </CheckboxGroup>
        )}

        <div className={styles.actions}>
          {step > 0 ? (
            <button type="button" className="btn btn-secondary" onClick={() => setStep((s) => s - 1)}>
              Back
            </button>
          ) : (
            <span />
          )}
          <button type="submit" className="btn btn-primary" disabled={isSubmitting}>
            {step < 2 ? 'Continue' : isSubmitting ? 'Creating your farm…' : 'Create account'}
          </button>
        </div>
      </form>
      <p className={styles.muted}>
        Already have an account? <Link to="/login">Log in</Link>
      </p>
    </AuthLayout>
  );
}
