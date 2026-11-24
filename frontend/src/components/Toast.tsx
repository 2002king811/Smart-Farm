import { CheckCircle2, CloudOff, X, XCircle } from 'lucide-react';
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

import { QUEUED_MESSAGE } from '@/offline/sync';

import styles from './Toast.module.css';

/**
 * Toasts confirm what the API has confirmed. Call `toast.success` only after the request
 * succeeded — never optimistically.
 */
type Kind = 'success' | 'error' | 'info';
interface ToastItem {
  id: number;
  kind: Kind;
  message: string;
}
interface ToastApi {
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
}

const ToastContext = createContext<ToastApi | null>(null);
let nextId = 1;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const dismiss = useCallback((id: number) => setItems((all) => all.filter((t) => t.id !== id)), []);
  const push = useCallback(
    (kind: Kind, message: string) => {
      const id = nextId++;
      setItems((all) => [...all, { id, kind, message }]);
      window.setTimeout(() => dismiss(id), 5000);
    },
    [dismiss],
  );
  const api = useMemo<ToastApi>(
    () => ({
      success: (m) => push('success', m),
      // A change saved offline is not a failure: show it as information.
      error: (m) => push(m === QUEUED_MESSAGE ? 'info' : 'error', m),
      info: (m) => push('info', m),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className={styles.region} aria-live="polite" aria-atomic="false">
        {items.map((t) => (
          <div
            key={t.id}
            className={`${styles.toast} ${styles[t.kind]}`}
            role={t.kind === 'error' ? 'alert' : 'status'}
          >
            {t.kind === 'success' ? (
              <CheckCircle2 size={18} aria-hidden="true" />
            ) : t.kind === 'info' ? (
              <CloudOff size={18} aria-hidden="true" />
            ) : (
              <XCircle size={18} aria-hidden="true" />
            )}
            <span>{t.message}</span>
            <button type="button" className={styles.close} onClick={() => dismiss(t.id)} aria-label="Dismiss">
              <X size={16} aria-hidden="true" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>');
  return ctx;
}
