import { Languages, LogOut, Settings, UserRound } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { useSession } from '@/features/session/SessionContext';
import { LANGUAGES } from '@/i18n';

import { useChangeLanguage } from './useChangeLanguage';
import styles from './UserMenu.module.css';

export function UserMenu() {
  const { t, i18n } = useTranslation();
  const { user, activeFarm, logout } = useSession();
  const changeLanguage = useChangeLanguage();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const initials = user ? `${user.first_name[0] ?? ''}${user.last_name[0] ?? ''}`.toUpperCase() || '?' : '?';

  return (
    <div className={styles.wrap} ref={ref}>
      <button
        type="button"
        className={styles.avatar}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`${t('header.account')}: ${user?.full_name ?? ''}`}
      >
        {user?.photo ? <img src={user.photo} alt="" /> : initials}
      </button>
      {open && (
        <div className={styles.menu} role="menu">
          <div className={styles.who}>
            <strong>{user?.full_name}</strong>
            <span>{activeFarm ? `${activeFarm.role_label} · ${activeFarm.farm.name}` : user?.email}</span>
          </div>
          <Link role="menuitem" to="/settings/profile" className={styles.item} onClick={() => setOpen(false)}>
            <UserRound size={18} aria-hidden="true" /> My profile
          </Link>
          <Link role="menuitem" to="/settings" className={styles.item} onClick={() => setOpen(false)}>
            <Settings size={18} aria-hidden="true" /> {t('nav.settings')}
          </Link>
          {LANGUAGES.filter((l) => l.code !== i18n.language).map((l) => (
            <button
              key={l.code}
              role="menuitem"
              type="button"
              className={styles.item}
              lang={l.code}
              onClick={() => {
                changeLanguage(l.code);
                setOpen(false);
              }}
            >
              <Languages size={18} aria-hidden="true" /> {l.label}
            </button>
          ))}
          <button role="menuitem" type="button" className={styles.item} onClick={() => void logout()}>
            <LogOut size={18} aria-hidden="true" /> {t('header.signOut')}
          </button>
        </div>
      )}
    </div>
  );
}
