import { Sprout } from 'lucide-react';
import type { ReactNode } from 'react';

import styles from './AuthLayout.module.css';

export function AuthLayout({
  title,
  subtitle,
  children,
  wide = false,
}: {
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <main className={styles.page}>
      <div className={`${styles.card} ${wide ? styles.wide : ''}`}>
        <div className={styles.brand}>
          <span className={styles.logo} aria-hidden="true">
            <Sprout size={24} />
          </span>
          <span>Smart Farm</span>
        </div>
        <h1 className={styles.title}>{title}</h1>
        {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
        {children}
      </div>
    </main>
  );
}
