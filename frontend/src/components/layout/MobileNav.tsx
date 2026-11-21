import { useTranslation } from 'react-i18next';
import { NavLink } from 'react-router-dom';

import { useSession } from '@/features/session/SessionContext';
import { MOBILE_ITEMS } from '@/routes/nav';
import { can } from '@/routes/permissions';

import styles from './MobileNav.module.css';

/** Bottom navigation for the attendant phone view. */
export function MobileNav() {
  const { t } = useTranslation();
  const { role } = useSession();
  const items = MOBILE_ITEMS.filter((item) => can(role, item.module));

  return (
    <nav className={styles.nav} aria-label={t('nav.main')}>
      <ul>
        {items.map(({ path, key, icon: Icon }) => (
          <li key={key}>
            <NavLink
              to={path}
              className={({ isActive }) => `${styles.link} ${isActive ? styles.active : ''}`}
            >
              <Icon size={22} aria-hidden="true" />
              <span>{t(`nav.${key}`)}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
