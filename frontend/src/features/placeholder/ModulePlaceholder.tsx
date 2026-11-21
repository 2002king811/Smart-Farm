import { Sprout } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { EmptyState } from '@/components/EmptyState';
import type { NavItem } from '@/routes/nav';

/** Stand-in for a screen whose build phase has not started. Shows no demo data. */
export function ModulePlaceholder({ item }: { item: NavItem }) {
  const { t } = useTranslation();
  const name = t(`nav.${item.key}`);
  return (
    <EmptyState
      icon={Sprout}
      title={t('placeholder.title', { module: name })}
      message={t('placeholder.message', { phase: item.phase })}
    />
  );
}
