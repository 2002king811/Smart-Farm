import type { LucideIcon } from 'lucide-react';
import { Inbox } from 'lucide-react';
import type { ReactNode } from 'react';

import styles from './States.module.css';

interface Props {
  title: string;
  message?: string;
  icon?: LucideIcon;
  action?: ReactNode;
}

export function EmptyState({ title, message, icon: Icon = Inbox, action }: Props) {
  return (
    <div className={styles.state}>
      <span className={styles.icon} aria-hidden="true">
        <Icon size={26} />
      </span>
      <h2 className={styles.title}>{title}</h2>
      {message && <p className={styles.message}>{message}</p>}
      {action}
    </div>
  );
}
