import type { LucideIcon } from 'lucide-react';

import styles from './StatCard.module.css';

interface Props {
  label: string;
  value: string | number;
  icon: LucideIcon;
  hint?: string;
}

export function StatCard({ label, value, icon: Icon, hint }: Props) {
  return (
    <section className={styles.card} aria-label={label}>
      <span className={styles.icon} aria-hidden="true">
        <Icon size={22} />
      </span>
      <div>
        <p className={styles.label}>{label}</p>
        <p className={styles.value}>{value}</p>
        {hint && <p className={styles.hint}>{hint}</p>}
      </div>
    </section>
  );
}
