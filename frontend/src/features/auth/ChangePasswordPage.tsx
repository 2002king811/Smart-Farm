import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

import { api, type Session } from '@/api/client';
import { applyServerErrors, FormError, PasswordInput, PasswordStrength } from '@/components/forms';
import { useToast } from '@/components/Toast';
import { useSession } from '@/features/session/SessionContext';

import { AuthLayout } from './AuthLayout';
import styles from './AuthLayout.module.css';
import { password } from './schemas';

const schema = z
  .object({
    current_password: z.string().min(1, 'Enter the temporary password you were sent.'),
    password,
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, { path: ['confirm'], message: 'The passwords do not match.' });

/** Shown after logging in with a temporary password. Nothing else is reachable until done. */
export function ChangePasswordPage() {
  const { startSession, logout, user } = useSession();
  const toast = useToast();
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { current_password: '', password: '', confirm: '' },
  });
  const { errors, isSubmitting } = form.formState;

  const onSubmit = form.handleSubmit(async ({ current_password, password: pw }) => {
    try {
      const session = await api<Session>('/me/password', {
        method: 'POST',
        body: { current_password, password: pw },
      });
      startSession(session);
      toast.success('Your new password is saved.');
    } catch (err) {
      applyServerErrors(err, form.setError, ['current_password', 'password']);
    }
  });

  return (
    <AuthLayout
      title="Choose your own password"
      subtitle={`Welcome, ${user?.first_name}. Replace the temporary password before you continue.`}
    >
      <form className={styles.form} onSubmit={onSubmit} noValidate>
        <FormError message={errors.root?.server?.message} />
        <PasswordInput
          label="Temporary password"
          autoComplete="current-password"
          error={errors.current_password?.message}
          {...form.register('current_password')}
        />
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
        <button type="submit" className={`btn btn-primary ${styles.full}`} disabled={isSubmitting}>
          Save password
        </button>
        <button type="button" className={`btn btn-secondary ${styles.full}`} onClick={() => void logout()}>
          Log out
        </button>
      </form>
    </AuthLayout>
  );
}
