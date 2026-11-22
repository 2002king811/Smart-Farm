import { Eye, EyeOff } from 'lucide-react';
import {
  forwardRef,
  useId,
  useState,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
} from 'react';
import type { FieldValues, Path, UseFormSetError } from 'react-hook-form';

import { ApiError } from '@/api/client';

import styles from './forms.module.css';

interface FieldProps {
  label: string;
  error?: string;
  hint?: ReactNode;
}

/** Text input with label, hint and error. Pass react-hook-form's register() props through. */
export const FormInput = forwardRef<HTMLInputElement, FieldProps & InputHTMLAttributes<HTMLInputElement>>(
  function FormInput({ label, error, hint, id, ...props }, ref) {
    const autoId = useId();
    const inputId = id ?? autoId;
    return (
      <div className={styles.field}>
        <label htmlFor={inputId} className={styles.label}>
          {label}
        </label>
        <input
          ref={ref}
          id={inputId}
          className={`${styles.input} ${error ? styles.invalid : ''}`}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined}
          {...props}
        />
        {hint && !error && (
          <p id={`${inputId}-hint`} className={styles.hint}>
            {hint}
          </p>
        )}
        {error && (
          <p id={`${inputId}-error`} className={styles.error}>
            {error}
          </p>
        )}
      </div>
    );
  },
);

export const PasswordInput = forwardRef<HTMLInputElement, FieldProps & InputHTMLAttributes<HTMLInputElement>>(
  function PasswordInput({ label, error, hint, id, ...props }, ref) {
    const autoId = useId();
    const inputId = id ?? autoId;
    const [show, setShow] = useState(false);
    return (
      <div className={styles.field}>
        <label htmlFor={inputId} className={styles.label}>
          {label}
        </label>
        <div className={styles.passwordWrap}>
          <input
            ref={ref}
            id={inputId}
            type={show ? 'text' : 'password'}
            className={`${styles.input} ${error ? styles.invalid : ''}`}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined}
            {...props}
          />
          <button
            type="button"
            className={styles.reveal}
            onClick={() => setShow((v) => !v)}
            aria-label={show ? 'Hide password' : 'Show password'}
            aria-pressed={show}
          >
            {show ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}
          </button>
        </div>
        {hint && (
          <div id={`${inputId}-hint`} className={styles.hint}>
            {hint}
          </div>
        )}
        {error && (
          <p id={`${inputId}-error`} className={styles.error}>
            {error}
          </p>
        )}
      </div>
    );
  },
);

export const FormSelect = forwardRef<
  HTMLSelectElement,
  FieldProps & SelectHTMLAttributes<HTMLSelectElement> & { children: ReactNode }
>(function FormSelect({ label, error, hint, id, children, ...props }, ref) {
  const autoId = useId();
  const inputId = id ?? autoId;
  return (
    <div className={styles.field}>
      <label htmlFor={inputId} className={styles.label}>
        {label}
      </label>
      <select
        ref={ref}
        id={inputId}
        className={`${styles.input} ${error ? styles.invalid : ''}`}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${inputId}-error` : undefined}
        {...props}
      >
        {children}
      </select>
      {hint && !error && <p className={styles.hint}>{hint}</p>}
      {error && (
        <p id={`${inputId}-error`} className={styles.error}>
          {error}
        </p>
      )}
    </div>
  );
});

/** A group of checkboxes (e.g. livestock types, channels) with one legend and one error. */
export function CheckboxGroup({
  legend,
  error,
  children,
}: {
  legend: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <fieldset className={styles.group} aria-invalid={error ? true : undefined}>
      <legend className={styles.label}>{legend}</legend>
      <div className={styles.options}>{children}</div>
      {error && <p className={styles.error}>{error}</p>}
    </fieldset>
  );
}

export const Checkbox = forwardRef<
  HTMLInputElement,
  { label: ReactNode } & InputHTMLAttributes<HTMLInputElement>
>(function Checkbox({ label, ...props }, ref) {
  return (
    <label className={styles.check}>
      <input ref={ref} type="checkbox" {...props} />
      <span>{label}</span>
    </label>
  );
});

export function FormError({ message }: { message?: string }) {
  if (!message) return null;
  return (
    <div className={styles.formError} role="alert">
      {message}
    </div>
  );
}

/** Copies the API's field errors onto the form; anything else becomes the form-level error. */
export function applyServerErrors<T extends FieldValues>(
  err: unknown,
  setError: UseFormSetError<T>,
  fields: readonly string[],
): void {
  if (!(err instanceof ApiError)) {
    setError('root.server' as Path<T>, {
      message: 'Could not reach Smart Farm. Check your connection and try again.',
    });
    return;
  }
  const leftovers: string[] = [];
  for (const [key, messages] of Object.entries(err.errors)) {
    const text = Array.isArray(messages) ? messages.join(' ') : String(messages);
    if (fields.includes(key)) setError(key as Path<T>, { message: text });
    else leftovers.push(text);
  }
  if (leftovers.length) setError('root.server' as Path<T>, { message: leftovers.join(' ') });
}

/** 0–4 score with label, for the sign-up strength meter. */
export function passwordStrength(pw: string): { score: number; label: string } {
  let score = 0;
  if (pw.length >= 8) score++;
  if (pw.length >= 12) score++;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) score++;
  if (/\d/.test(pw) && /[^A-Za-z0-9]/.test(pw)) score++;
  if (pw.length < 8) score = Math.min(score, 1);
  const labels = ['Too short', 'Weak', 'Fair', 'Good', 'Strong'];
  return { score, label: labels[score]! };
}

export function PasswordStrength({ password }: { password: string }) {
  const { score, label } = passwordStrength(password);
  return (
    <div className={styles.strength} aria-live="polite">
      <div className={styles.bars} aria-hidden="true">
        {[1, 2, 3, 4].map((n) => (
          <span key={n} className={n <= score ? styles[`s${score}`] : ''} />
        ))}
      </div>
      <span>Password strength: {password ? label : '—'}</span>
    </div>
  );
}
