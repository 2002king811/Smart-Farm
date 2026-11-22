import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { z } from 'zod';

import { api } from '@/api/client';
import { applyServerErrors, FormError, PasswordInput, PasswordStrength } from '@/components/forms';
import { useToast } from '@/components/Toast';

import { AuthLayout } from './AuthLayout';
import styles from './AuthLayout.module.css';
import { password } from './schemas';

const schema = z
  .object({ password, confirm: z.string() })
  .refine((v) => v.password === v.confirm, { path: ['confirm'], message: 'The passwords do not match.' });

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const navigate = useNavigate();
  const toast = useToast();
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { password: '', confirm: '' },
  });
  const { errors, isSubmitting } = form.formState;

  const onSubmit = form.handleSubmit(async ({ password: pw }) => {
    try {
      await api('/auth/password/reset', { method: 'POST', body: { token, password: pw }, noRefresh: true });
      toast.success('Your password has been changed. Log in with the new password.');
      navigate('/login', { replace: true });
    } catch (err) {
      applyServerErrors(err, form.setError, ['password']);
    }
  });

  return (
    <AuthLayout title="Choose a new password">
      <form className={styles.form} onSubmit={onSubmit} noValidate>
        <FormError message={errors.root?.server?.message} />
        <PasswordInput
          label="New password"
          autoComplete="new-password"
          hint={<PasswordStrength password={form.watch('password')} />}
          error={errors.password?.message}
          {...form.register('password')}
        />
        <PasswordInput
          label="Repeat new password"
          autoComplete="new-password"
          error={errors.confirm?.message}
          {...form.register('confirm')}
        />
        <button type="submit" className={`btn btn-primary ${styles.full}`} disabled={isSubmitting || !token}>
          Change password
        </button>
      </form>
      <p className={styles.muted}>
        <Link to="/forgot-password">Request a new link</Link>
      </p>
    </AuthLayout>
  );
}
