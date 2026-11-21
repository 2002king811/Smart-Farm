import { useTranslation } from 'react-i18next';
import { Navigate, Route, Routes } from 'react-router-dom';

import { EmptyState } from '@/components/EmptyState';
import { AppLayout } from '@/components/layout/AppLayout';
import { LoadingState } from '@/components/LoadingState';
import { ModulePlaceholder } from '@/features/placeholder/ModulePlaceholder';
import { useSession } from '@/features/session/SessionContext';
import { SignInPlaceholder } from '@/features/session/SignInPlaceholder';

import { SIDEBAR_ITEMS, type NavItem } from './nav';
import { can } from './permissions';

/** Renders the route only if the role may view the module; otherwise it does not exist. */
function Guarded({ item }: { item: NavItem }) {
  const { role } = useSession();
  if (!can(role, item.module)) return <NotFound />;
  return <ModulePlaceholder item={item} />;
}

function NotFound() {
  const { t } = useTranslation();
  return <EmptyState title={t('notFound.title')} message={t('notFound.message')} />;
}

export function AppRoutes() {
  const { status } = useSession();

  if (status === 'loading') return <LoadingState />;
  if (status === 'anonymous') {
    return (
      <Routes>
        <Route path="*" element={<SignInPlaceholder />} />
      </Routes>
    );
  }

  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        {SIDEBAR_ITEMS.map((item) => (
          <Route key={item.path} path={`${item.path}/*`} element={<Guarded item={item} />} />
        ))}
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
