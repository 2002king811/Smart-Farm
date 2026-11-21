import { Sprout, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { NavLink } from 'react-router-dom';

import { useSession } from '@/features/session/SessionContext';
import { SIDEBAR_ITEMS } from '@/routes/nav';
import { can } from '@/routes/permissions';

import { FarmSwitcher } from './FarmSwitcher';
import styles from './Sidebar.module.css';

interface Props {
  open: boolean;
  onClose: () => void;
}

export function Sidebar({ open, onClose }: Props) {
  const { t } = useTranslation();
  const { role } = useSession();
  const items = SIDEBAR_ITEMS.filter((item) => can(role, item.module));

  return (
    <aside className={`${styles.sidebar} ${open ? styles.open : ''}`} id="app-sidebar">
      <div className={styles.brand}>
        <span className={styles.logo} aria-hidden="true">
          <Sprout size={22} />
        </span>
        <span className={styles.name}>{t('app.name')}</span>
        <button type="button" className={styles.close} onClick={onClose} aria-label={t('header.closeMenu')}>
          <X size={20} aria-hidden="true" />
        </button>
      </div>
      <FarmSwitcher />
      <nav aria-label={t('nav.main')} className={styles.nav}>
        <ul>
          {items.map(({ path, key, icon: Icon }) => (
            <li key={path}>
              <NavLink
                to={path}
                className={({ isActive }) => `${styles.link} ${isActive ? styles.active : ''}`}
                onClick={onClose}
              >
                <Icon size={20} aria-hidden="true" />
                <span>{t(`nav.${key}`)}</span>
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </aside>
  );
}
