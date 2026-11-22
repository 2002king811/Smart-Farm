import { zodResolver } from '@hookform/resolvers/zod';
import { useQuery } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { z } from 'zod';

import { api, ApiError, type Schemas, type Session } from '@/api/client';
import { applyServerErrors, FormError, FormInput, PasswordInput, PasswordStrength } from '@/components/forms';
import { LoadingState } from '@/components/LoadingState';
import { useToast } from '@/components/Toast';
import { useSession } from '@/features/session/SessionContext';

import { AuthLayout } from './AuthLayout';
import styles from './AuthLayout.module.css';
import { password } from './schemas';

const schema = z.object({
  first_name: z.string().trim().min(1, 'Enter your first name.'),
  last_name: z.string(),
  password,
});

export function InvitePage() {
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const navigate = useNavigate();
  const toast = useToast();
  const { status, user, startSession, refetchFarms, switchFarm } = useSession();
  const lookup = useQuery({
    queryKey: ['invitation', token],
    queryFn: () =>
      api<Schemas['InvitationLookup']>('/invitations/lookup', { query: { token }, noRefresh: true }),
    retry: false,
  });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    values: {
      first_name: lookup.data?.first_name ?? '',
      last_name: lookup.data?.last_name ?? '',
      password: '',
    },
  });

  const accept = async (body: Record<string, string>) => {
    const session = await api<Session>('/invitations/accept', {
      method: 'POST',
      body: { token, ...body },
      noRefresh: true,
    });
    startSession(session);
    refetchFarms();
    const farms = await api<Schemas['MyFarm'][]>('/me/farms');
    const joined = farms.find((m) => m.farm.name === lookup.data?.farm_name);
    if (joined) switchFarm(joined.farm.id);
    toast.success(`You have joined ${lookup.data?.farm_name}.`);
    navigate('/dashboard', { replace: true });
  };

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      await accept(values);
    } catch (err) {
      applyServerErrors(err, form.setError, ['first_name', 'last_name', 'password']);
    }
  });

  if (lookup.isPending)
    return (
      <AuthLayout title="Your invitation">
        <LoadingState />
      </AuthLayout>
    );
  if (lookup.isError) {
    return (
      <AuthLayout title="Your invitation">
        <div role="alert" style={{ color: 'var(--tone-red-fg)' }}>
          {lookup.error instanceof ApiError ? lookup.error.message : 'This invitation could not be opened.'}
        </div>
        <p className={styles.muted}>
          <Link to="/login">Log in</Link>
        </p>
      </AuthLayout>
    );
  }

  const info = lookup.data;
  const subtitle = `${info.invited_by_name ?? 'Someone'} invited you to join ${info.farm_name} as ${info.role_label}.`;

  if (info.has_account) {
    return (
      <AuthLayout title={`Join ${info.farm_name}`} subtitle={subtitle}>
        {status === 'authenticated' ? (
          <>
            <p className={styles.muted}>You are logged in as {user?.full_name}.</p>
            <button
              type="button"
              className={`btn btn-primary ${styles.full}`}
              onClick={() =>
                accept({}).catch((err) =>
                  toast.error(err instanceof ApiError ? err.message : 'Could not accept.'),
                )
              }
            >
              Accept invitation
            </button>
          </>
        ) : (
          <>
            <p className={styles.muted}>
              You already have a Smart Farm account. Log in, then open this link again.
            </p>
            <Link
              className={`btn btn-primary ${styles.full}`}
              to="/login"
              state={{ from: `/invite?token=${token}` }}
            >
              Log in to accept
            </Link>
          </>
        )}
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title={`Join ${info.farm_name}`} subtitle={subtitle}>
      <form className={styles.form} onSubmit={onSubmit} noValidate>
        <FormError message={form.formState.errors.root?.server?.message} />
        <div className={styles.grid2}>
          <FormInput
            label="First name"
            error={form.formState.errors.first_name?.message}
            {...form.register('first_name')}
          />
          <FormInput label="Last name" {...form.register('last_name')} />
        </div>
        <FormInput
          label={info.email ? 'Email' : 'Mobile number'}
          value={info.email || info.phone}
          readOnly
          disabled
        />
        <PasswordInput
          label="Choose a password"
          autoComplete="new-password"
          hint={<PasswordStrength password={form.watch('password')} />}
          error={form.formState.errors.password?.message}
          {...form.register('password')}
        />
        <button
          type="submit"
          className={`btn btn-primary ${styles.full}`}
          disabled={form.formState.isSubmitting}
        >
          Accept and create account
        </button>
      </form>
    </AuthLayout>
  );
}
