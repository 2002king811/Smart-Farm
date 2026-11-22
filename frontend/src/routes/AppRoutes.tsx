import { lazy, Suspense, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';

import { EmptyState } from '@/components/EmptyState';
import { AppLayout } from '@/components/layout/AppLayout';
import { LoadingState } from '@/components/LoadingState';
import { ChangePasswordPage } from '@/features/auth/ChangePasswordPage';
import { ForgotPasswordPage } from '@/features/auth/ForgotPasswordPage';
import { InvitePage } from '@/features/auth/InvitePage';
import { LoginPage } from '@/features/auth/LoginPage';
import { NoFarmPage } from '@/features/auth/NoFarmPage';
import { ResetPasswordPage } from '@/features/auth/ResetPasswordPage';
import { SignupPage } from '@/features/auth/SignupPage';
import { VerifyEmailPage } from '@/features/auth/VerifyEmailPage';
import { ModulePlaceholder } from '@/features/placeholder/ModulePlaceholder';
import { useSession } from '@/features/session/SessionContext';

import { SIDEBAR_ITEMS, type NavItem } from './nav';
import { can, type Module } from './permissions';

const UsersPage = lazy(() => import('@/features/users/UsersPage'));
const SettingsPage = lazy(() => import('@/features/settings/SettingsPage'));
const LivestockRoutes = lazy(() => import('@/features/livestock/LivestockRoutes'));
const HealthPage = lazy(() => import('@/features/health/HealthPage'));
const CalendarPage = lazy(() => import('@/features/calendar/CalendarPage'));
const ActivitiesPage = lazy(() => import('@/features/calendar/ActivitiesPage'));

/** Screens built so far; everything else shows its phase placeholder. */
const BUILT: Partial<Record<Module, () => ReactNode>> = {
  livestock: () => <LivestockRoutes />,
  health: () => <HealthPage />,
  calendar: () => <CalendarPage />,
  activities: () => <ActivitiesPage />,
  users: () => <UsersPage />,
  settings: () => <SettingsPage />,
};

/** Renders the route only if the role may view the module; otherwise it does not exist. */
function Guarded({ item }: { item: NavItem }) {
  const { role } = useSession();
  // Everyone has "My profile" under Settings; farm settings need the settings module.
  const allowed = item.module === 'settings' ? true : can(role, item.module);
  if (!allowed) return <NotFound />;
  const screen = BUILT[item.module];
  return screen ? (
    <Suspense fallback={<LoadingState />}>{screen()}</Suspense>
  ) : (
    <ModulePlaceholder item={item} />
  );
}

function NotFound() {
  const { t } = useTranslation();
  return <EmptyState title={t('notFound.title')} message={t('notFound.message')} />;
}

function RedirectToLogin() {
  const location = useLocation();
  return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
}

export function AppRoutes() {
  const { status, user, farms, farmsLoading } = useSession();

  // Pages that work whether or not you are signed in.
  const shared = [
    <Route key="verify" path="/verify-email" element={<VerifyEmailPage />} />,
    <Route key="invite" path="/invite" element={<InvitePage />} />,
  ];

  if (status === 'loading') return <LoadingState />;

  if (status === 'anonymous') {
    return (
      <Routes>
        {shared}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="*" element={<RedirectToLogin />} />
      </Routes>
    );
  }

  if (user?.must_change_password) return <ChangePasswordPage />;
  if (farmsLoading) return <LoadingState />;

  return (
    <Routes>
      {shared}
      <Route path="/login" element={<Navigate to="/dashboard" replace />} />
      <Route path="/signup" element={<Navigate to="/dashboard" replace />} />
      {farms.length === 0 ? (
        <Route path="*" element={<NoFarmPage />} />
      ) : (
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          {SIDEBAR_ITEMS.map((item) => (
            <Route key={item.path} path={`${item.path}/*`} element={<Guarded item={item} />} />
          ))}
          <Route path="*" element={<NotFound />} />
        </Route>
      )}
    </Routes>
  );
}
