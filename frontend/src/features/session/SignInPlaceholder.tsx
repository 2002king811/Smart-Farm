import { Sprout } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { ROLE_LABELS, type Role } from '@/routes/permissions';

import styles from './SignInPlaceholder.module.css';
import { useSession } from './SessionContext';

/** Phase 1 stand-in for the Login screen (built in phase 2). */
export function SignInPlaceholder() {
  const { t } = useTranslation();
  const { startPreview } = useSession();
  return (
    <main className={styles.page}>
      <div className={styles.card}>
        <span className={styles.logo} aria-hidden="true">
          <Sprout size={28} />
        </span>
        <h1>{t('app.name')}</h1>
        <p className={styles.note}>{t('preview.banner')}</p>
        {import.meta.env.DEV && (
          <fieldset className={styles.roles}>
            <legend>{t('preview.as')}</legend>
            {(Object.keys(ROLE_LABELS) as Role[]).map((role) => (
              <button
                key={role}
                type="button"
                className="btn btn-secondary"
                onClick={() => startPreview(role)}
              >
                {ROLE_LABELS[role]}
              </button>
            ))}
          </fieldset>
        )}
      </div>
    </main>
  );
}
