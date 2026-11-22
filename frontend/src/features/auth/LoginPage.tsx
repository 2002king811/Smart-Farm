import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { z } from 'zod';

import { api, type Session } from '@/api/client';
import { applyServerErrors, Checkbox, FormError, FormInput, PasswordInput } from '@/components/forms';
import { useSession } from '@/features/session/SessionContext';

import { AuthLayout } from './AuthLayout';
import styles from './AuthLayout.module.css';

const schema = z.object({
  identifier: z.string().trim().min(1, 'Enter your username, email or phone number.'),
  password: z.string().min(1, 'Enter your password.'),
  remember: z.boolean(),
});
type Values = z.infer<typeof schema>;

export function LoginPage() {
  const { startSession } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { identifier: '', password: '', remember: false },
  });

  const onSubmit = handleSubmit(async (values) => {
    try {
      const session = await api<Session>('/auth/login', { method: 'POST', body: values, noRefresh: true });
      startSession(session);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from && from !== '/login' ? from : '/dashboard', { replace: true });
    } catch (err) {
      applyServerErrors(err, setError, ['identifier', 'password']);
    }
  });

  return (
    <AuthLayout title="Log in" subtitle="Welcome back. Log in to manage your farm.">
      <form className={styles.form} onSubmit={onSubmit} noValidate>
        <FormError message={errors.root?.server?.message} />
        <FormInput
          label="Username, email or phone"
          autoComplete="username"
          autoCapitalize="none"
          error={errors.identifier?.message}
          {...register('identifier')}
        />
        <PasswordInput
          label="Password"
          autoComplete="current-password"
          error={errors.password?.message}
          {...register('password')}
        />
        <div className={styles.row}>
          <Checkbox label="Remember me for 30 days" {...register('remember')} />
          <Link to="/forgot-password">Forgot password?</Link>
        </div>
        <button type="submit" className={`btn btn-primary ${styles.full}`} disabled={isSubmitting}>
          {isSubmitting ? 'Logging in…' : 'Log in'}
        </button>
      </form>
      <p className={styles.muted}>
        New to Smart Farm? <Link to="/signup">Create an account for your farm</Link>
      </p>
    </AuthLayout>
  );
}
