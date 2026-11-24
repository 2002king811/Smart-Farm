import { CloudOff, RefreshCw, TriangleAlert } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { discardFailed, getSyncState, subscribe, syncNow, type SyncState } from './sync';
import styles from './SyncBanner.module.css';

export function useSyncState(): SyncState {
  const [state, setState] = useState(getSyncState);
  useEffect(() => subscribe(setState), []);
  return state;
}

/** "Offline" and "Waiting to sync (3)" banner, plus changes the server refused. */
export function SyncBanner() {
  const { t } = useTranslation();
  const s = useSyncState();
  if (s.online && !s.pending && !s.failed.length) return null;
  return (
    <div className={styles.stack}>
      {(!s.online || s.pending > 0) && (
        <div className={`${styles.banner} ${s.online ? styles.waiting : styles.offline}`} role="status">
          {s.online ? (
            <RefreshCw size={18} aria-hidden="true" className={s.syncing ? styles.spin : ''} />
          ) : (
            <CloudOff size={18} aria-hidden="true" />
          )}
          <span>
            {!s.online && t('sync.offline')}
            {!s.online && s.pending > 0 && ' · '}
            {s.pending > 0 && t('sync.waiting', { count: s.pending })}
          </span>
          {s.online && s.pending > 0 && !s.syncing && (
            <button type="button" className={styles.action} onClick={() => void syncNow()}>
              {t('sync.now')}
            </button>
          )}
        </div>
      )}
      {s.failed.length > 0 && (
        <div className={`${styles.banner} ${styles.failed}`} role="alert">
          <TriangleAlert size={18} aria-hidden="true" />
          <span>
            {t('sync.failed', { count: s.failed.length })}{' '}
            {s.failed.map((c) => `${c.label}: ${c.error}`).join('; ')}
          </span>
          <button type="button" className={styles.action} onClick={() => void discardFailed()}>
            {t('sync.dismiss')}
          </button>
        </div>
      )}
    </div>
  );
}
