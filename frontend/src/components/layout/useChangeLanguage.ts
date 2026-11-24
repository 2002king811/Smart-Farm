import { useCallback } from 'react';

import { api, type Schemas } from '@/api/client';
import { setLanguage } from '@/i18n';
import { useSession } from '@/features/session/SessionContext';

/** Changes the language now and saves it to the person's profile (when signed in). */
export function useChangeLanguage() {
  const { user, setUser } = useSession();
  return useCallback(
    (code: string) => {
      setLanguage(code);
      if (user && user.language !== code) {
        void api<Schemas['Me']>('/me', { method: 'PATCH', body: { language: code } })
          .then(setUser)
          .catch(() => undefined); // offline: the choice still applies on this device
      }
    },
    [user, setUser],
  );
}
