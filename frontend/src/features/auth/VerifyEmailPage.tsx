import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';

import { api, ApiError } from '@/api/client';
import { LoadingState } from '@/components/LoadingState';
import { useSession } from '@/features/session/SessionContext';

import { AuthLayout } from './AuthLayout';
import styles from './AuthLayout.module.css';

export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const { status, user, setUser } = useSession();
  const result = useQuery({
    queryKey: ['verify-email', token],
    queryFn: async () => {
      const res = await api<{ detail: string }>('/auth/verify-email', {
        method: 'POST',
        body: { token },
        noRefresh: true,
      });
      if (user) setUser({ ...user, email_verified: true });
      return res;
    },
    retry: false,
    staleTime: Infinity,
  });

  return (
    <AuthLayout title="Confirm your email">
      {result.isPending && <LoadingState label="Confirming…" />}
      {result.isSuccess && (
        <div className={styles.success} role="status">
          {result.data.detail}
        </div>
      )}
      {result.isError && (
        <div role="alert" style={{ color: 'var(--tone-red-fg)' }}>
          {result.error instanceof ApiError
            ? result.error.message
            : 'Could not confirm your email. Try again.'}
        </div>
      )}
      <p className={styles.muted}>
        {status === 'authenticated' ? (
          <Link to="/dashboard">Go to Smart Farm</Link>
        ) : (
          <Link to="/login">Log in</Link>
        )}
      </p>
    </AuthLayout>
  );
}
