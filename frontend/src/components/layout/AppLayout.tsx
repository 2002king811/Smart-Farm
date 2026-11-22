import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet, useLocation } from 'react-router-dom';

import { useSession } from '@/features/session/SessionContext';
import { VerificationBanner } from '@/features/session/VerificationBanner';
import { MOBILE_ITEMS, SIDEBAR_ITEMS } from '@/routes/nav';

import styles from './AppLayout.module.css';
import { Header } from './Header';
import { MobileNav } from './MobileNav';
import { Sidebar } from './Sidebar';

function usePageTitle(): string {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const item = [...SIDEBAR_ITEMS, ...MOBILE_ITEMS].find((i) => pathname.startsWith(i.path));
  return item ? t(`nav.${item.key}`) : t('app.name');
}

/** Desktop shell for administrators and farm managers: sidebar + header. */
export function DesktopLayout() {
  const { t } = useTranslation();
  const title = usePageTitle();
  const [menuOpen, setMenuOpen] = useState(false);
  const { pathname } = useLocation();

  useEffect(() => setMenuOpen(false), [pathname]);
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setMenuOpen(false);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [menuOpen]);

  return (
    <div className={styles.desktop}>
      <a className="skip-link" href="#main">
        {t('app.skipToContent')}
      </a>
      <Sidebar open={menuOpen} onClose={() => setMenuOpen(false)} />
      {menuOpen && <div className={styles.scrim} onClick={() => setMenuOpen(false)} aria-hidden="true" />}
      <div className={styles.main}>
        <Header title={title} onMenu={() => setMenuOpen(true)} menuOpen={menuOpen} />
        <main id="main" className={styles.content} tabIndex={-1}>
          <VerificationBanner />
          <Outlet />
        </main>
      </div>
    </div>
  );
}

/** Phone view for livestock attendants: compact header + bottom navigation. */
export function MobileLayout() {
  const { t } = useTranslation();
  const title = usePageTitle();
  return (
    <div className={styles.mobile}>
      <a className="skip-link" href="#main">
        {t('app.skipToContent')}
      </a>
      <Header title={title} compact />
      <main id="main" className={styles.mobileContent} tabIndex={-1}>
        <VerificationBanner />
        <Outlet />
      </main>
      <MobileNav />
    </div>
  );
}

export function AppLayout() {
  const { role } = useSession();
  return role === 'livestock_attendant' ? <MobileLayout /> : <DesktopLayout />;
}
