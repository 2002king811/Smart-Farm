import { zodResolver } from '@hookform/resolvers/zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link, useNavigate } from 'react-router-dom';
import { z } from 'zod';

import { api } from '@/api/client';
import { applyServerErrors, FormError, FormInput, PasswordInput } from '@/components/forms';
import { useToast } from '@/components/Toast';

import { AuthLayout } from './AuthLayout';
import styles from './AuthLayout.module.css';
import { password } from './schemas';

const requestSchema = z.object({
  identifier: z.string().trim().min(1, 'Enter your username, email or phone number.'),
  channel: z.enum(['email', 'sms']),
});
const codeSchema = z.object({
  code: z
    .string()
    .trim()
    .regex(/^\d{6}$/, 'Enter the 6-digit code.'),
  password,
});

export function ForgotPasswordPage() {
  const [sentTo, setSentTo] = useState<{
    identifier: string;
    channel: 'email' | 'sms';
    message: string;
  } | null>(null);
  const request = useForm<z.infer<typeof requestSchema>>({
    resolver: zodResolver(requestSchema),
    defaultValues: { identifier: '', channel: 'email' },
  });

  const onRequest = request.handleSubmit(async (values) => {
    try {
      const res = await api<{ detail: string }>('/auth/password/forgot', {
        method: 'POST',
        body: values,
        noRefresh: true,
      });
      setSentTo({ ...values, message: res.detail });
    } catch (err) {
      applyServerErrors(err, request.setError, ['identifier']);
    }
  });

  if (sentTo?.channel === 'sms')
    return <ResetWithCode identifier={sentTo.identifier} message={sentTo.message} />;

  return (
    <AuthLayout title="Forgot password" subtitle="We'll send you a link by email or a code by SMS.">
      {sentTo ? (
        <div className={styles.success} role="status">
          {sentTo.message} Check your email and follow the link within 15 minutes.
        </div>
      ) : (
        <form className={styles.form} onSubmit={onRequest} noValidate>
          <FormError message={request.formState.errors.root?.server?.message} />
          <FormInput
            label="Username, email or phone"
            autoComplete="username"
            error={request.formState.errors.identifier?.message}
            {...request.register('identifier')}
          />
          <fieldset className={styles.form} style={{ border: 0, padding: 0, margin: 0 }}>
            <legend style={{ fontWeight: 600, fontSize: 'var(--text-sm)', marginBottom: 8 }}>Send me</legend>
            <label>
              <input type="radio" value="email" {...request.register('channel')} /> A reset link by email
            </label>
            <label>
              <input type="radio" value="sms" {...request.register('channel')} /> A 6-digit code by SMS
            </label>
          </fieldset>
          <button
            type="submit"
            className={`btn btn-primary ${styles.full}`}
            disabled={request.formState.isSubmitting}
          >
            Send
          </button>
        </form>
      )}
      <p className={styles.muted}>
        <Link to="/login">Back to log in</Link>
      </p>
    </AuthLayout>
  );
}

function ResetWithCode({ identifier, message }: { identifier: string; message: string }) {
  const navigate = useNavigate();
  const toast = useToast();
  const form = useForm<z.infer<typeof codeSchema>>({
    resolver: zodResolver(codeSchema),
    defaultValues: { code: '', password: '' },
  });
  const onSubmit = form.handleSubmit(async (values) => {
    try {
      await api('/auth/password/reset', { method: 'POST', body: { ...values, identifier }, noRefresh: true });
      toast.success('Your password has been changed. Log in with the new password.');
      navigate('/login', { replace: true });
    } catch (err) {
      applyServerErrors(err, form.setError, ['code', 'password']);
    }
  });
  return (
    <AuthLayout title="Enter your code" subtitle={message}>
      <form className={styles.form} onSubmit={onSubmit} noValidate>
        <FormError message={form.formState.errors.root?.server?.message} />
        <FormInput
          label="6-digit code"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          error={form.formState.errors.code?.message}
          {...form.register('code')}
        />
        <PasswordInput
          label="New password"
          autoComplete="new-password"
          error={form.formState.errors.password?.message}
          {...form.register('password')}
        />
        <button
          type="submit"
          className={`btn btn-primary ${styles.full}`}
          disabled={form.formState.isSubmitting}
        >
          Change password
        </button>
      </form>
    </AuthLayout>
  );
}
