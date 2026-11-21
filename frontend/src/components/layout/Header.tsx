import { Bell, Menu, Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { useSession } from '@/features/session/SessionContext';
import { LANGUAGES } from '@/i18n';

import styles from './Header.module.css';

interface Props {
  title: string;
  onMenu?: () => void;
  menuOpen?: boolean;
  compact?: boolean;
}

export function Header({ title, onMenu, menuOpen = false, compact = false }: Props) {
  const { t, i18n } = useTranslation();
  const { user, activeFarm, status } = useSession();
  const initials = user ? `${user.first_name[0] ?? ''}${user.last_name[0] ?? ''}`.toUpperCase() || '?' : '•';

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
        {compact && (
          <span className={styles.farm}>
            {activeFarm?.farm.name ?? (status === 'preview' ? 'Preview' : '')}
          </span>
        )}
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
              onChange={(e) => void i18n.changeLanguage(e.target.value)}
            >
              {LANGUAGES.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.label}
                </option>
              ))}
            </select>
          </>
        )}
        <Link to="/notifications" className={styles.iconButton} aria-label={t('header.notifications')}>
          <Bell size={22} aria-hidden="true" />
        </Link>
        <span className={styles.avatar} title={user?.full_name ?? t('header.account')} aria-hidden="true">
          {initials}
        </span>
      </div>
    </header>
  );
}
