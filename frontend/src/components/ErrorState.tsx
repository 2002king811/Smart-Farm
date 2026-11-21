import { AlertTriangle, RotateCw } from 'lucide-react';

import styles from './States.module.css';

interface Props {
  title?: string;
  message?: string;
  onRetry?: () => void;
}

export function ErrorState({ title = 'Something went wrong', message, onRetry }: Props) {
  return (
    <div className={`${styles.state} ${styles.error}`} role="alert">
      <span className={styles.icon} aria-hidden="true">
        <AlertTriangle size={26} />
      </span>
      <h2 className={styles.title}>{title}</h2>
      {message && <p className={styles.message}>{message}</p>}
      {onRetry && (
        <button type="button" className="btn btn-secondary" onClick={onRetry}>
          <RotateCw size={16} aria-hidden="true" /> Retry
        </button>
      )}
    </div>
  );
}
