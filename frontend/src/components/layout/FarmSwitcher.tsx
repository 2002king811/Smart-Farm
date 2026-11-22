import { ChevronsUpDown } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useSession } from '@/features/session/SessionContext';

import styles from './FarmSwitcher.module.css';

/** Lists the user's farm memberships; switching sets X-Farm-ID and clears cached farm data. */
export function FarmSwitcher() {
  const { t } = useTranslation();
  const { farms, activeFarm, switchFarm } = useSession();

  if (!activeFarm) return null;

  return (
    <div className={styles.switcher}>
      <label htmlFor="farm-switcher" className={styles.label}>
        {t('farm.switch')}
      </label>
      <div className={styles.selectWrap}>
        <select
          id="farm-switcher"
          className={styles.select}
          value={activeFarm.farm.id}
          onChange={(e) => switchFarm(e.target.value)}
          disabled={farms.length < 2}
        >
          {farms.map((m) => (
            <option key={m.farm.id} value={m.farm.id}>
              {m.farm.name}
            </option>
          ))}
        </select>
        {farms.length > 1 && <ChevronsUpDown size={16} aria-hidden="true" className={styles.chevron} />}
      </div>
      <span className={styles.role}>{activeFarm.role_label}</span>
    </div>
  );
}
