import { useSession } from '@/features/session/SessionContext';

import { AuthLayout } from './AuthLayout';
import styles from './AuthLayout.module.css';

/** Signed in, but not an active member of any farm (e.g. deactivated everywhere). */
export function NoFarmPage() {
  const { user, logout } = useSession();
  return (
    <AuthLayout title="No farm yet" subtitle={`You are logged in as ${user?.full_name}.`}>
      <p className={styles.muted}>
        You are not an active member of any farm. Ask a farm administrator to invite you, then open the link
        they send.
      </p>
      <button type="button" className={`btn btn-secondary ${styles.full}`} onClick={() => void logout()}>
        Log out
      </button>
    </AuthLayout>
  );
}
