import { Bell, Menu, Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { useLiveNotifications, useUnreadCount } from '@/features/notifications/api';
import { useSession } from '@/features/session/SessionContext';
import { LANGUAGES } from '@/i18n';
import { useChangeLanguage } from './useChangeLanguage';

import styles from './Header.module.css';
import { UserMenu } from './UserMenu';

interface Props {
  title: string;
  onMenu?: () => void;
  menuOpen?: boolean;
  compact?: boolean;
}

export function Header({ title, onMenu, menuOpen = false, compact = false }: Props) {
  const { t, i18n } = useTranslation();
  const { activeFarm } = useSession();
  const changeLanguage = useChangeLanguage();
  const unread = useUnreadCount(Boolean(activeFarm));
  useLiveNotifications(Boolean(activeFarm));
  const count = unread.data?.unread ?? 0;
  const bellLabel = count ? `${t('header.notifications')}: ${count} unread` : t('header.notifications');

  return (
    <header className={`${styles.header} ${compact ? styles.compact : ''}`}>
      {onMenu && (
        <button
          type="button"
          className={styles.iconButton + ' ' + styles.menu}
          onClick={onMenu}
          aria-label={t('header.openMenu')}
          aria-expanded={menuOpen}
          aria-controls="app-sidebar"
        >
          <Menu size={22} aria-hidden="true" />
        </button>
      )}
      <div className={styles.titles}>
        <h1 className={styles.title}>{title}</h1>
        {compact && <span className={styles.farm}>{activeFarm?.farm.name ?? ''}</span>}
      </div>
      {!compact && (
        <form className={styles.search} role="search" onSubmit={(e) => e.preventDefault()}>
          <Search size={18} aria-hidden="true" />
          <label htmlFor="global-search" className="visually-hidden">
            {t('header.search')}
          </label>
          <input id="global-search" type="search" placeholder={t('header.search')} />
        </form>
      )}
      <div className={styles.actions}>
        {!compact && (
          <>
            <label htmlFor="language" className="visually-hidden">
              Language
            </label>
            <select
              id="language"
              className={styles.language}
              value={i18n.language}
              onChange={(e) => changeLanguage(e.target.value)}
            >
              {LANGUAGES.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.label}
                </option>
              ))}
            </select>
          </>
        )}
        <Link to="/notifications" className={styles.iconButton} aria-label={bellLabel}>
          <Bell size={22} aria-hidden="true" />
          {count > 0 && (
            <span
              className={`${styles.badge} ${unread.data?.urgent ? styles.badgeUrgent : ''}`}
              data-testid="bell-count"
              aria-hidden="true"
            >
              {count > 99 ? '99+' : count}
            </span>
          )}
        </Link>
        <UserMenu />
      </div>
    </header>
  );
}
