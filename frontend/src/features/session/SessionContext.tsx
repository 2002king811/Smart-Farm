import { useQuery, useQueryClient } from '@tanstack/react-query';
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import {
  api,
  forgetOfflineUser,
  hasSessionCookie,
  onSynced,
  refreshSession,
  setAccessToken,
  setActiveFarmId,
  setSessionEndedHandler,
  type Schemas,
  type Session,
} from '@/api/client';
import { cacheClear } from '@/offline/store';
import { prefetchForOffline } from '@/offline/prefetch';
import { discardAll, startSyncLoop } from '@/offline/sync';
import type { Role } from '@/routes/permissions';

export type Me = Schemas['Me'];
export type MyFarm = Schemas['MyFarm'];

const FARM_KEY = 'sf.activeFarmId';

interface SessionValue {
  status: 'loading' | 'anonymous' | 'authenticated';
  user: Me | null;
  farms: MyFarm[];
  farmsLoading: boolean;
  activeFarm: MyFarm | null;
  role: Role | undefined;
  /** Store a session returned by login, sign-up, invitation accept or password change. */
  startSession: (session: Session) => void;
  setUser: (user: Me) => void;
  logout: () => Promise<void>;
  switchFarm: (farmId: string) => void;
  refetchFarms: () => void;
}

const SessionContext = createContext<SessionValue | null>(null);

function readStoredFarm(): string | null {
  try {
    return window.localStorage.getItem(FARM_KEY);
  } catch {
    return null;
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<SessionValue['status']>(hasSessionCookie() ? 'loading' : 'anonymous');
  const [user, setUser] = useState<Me | null>(null);
  const [farmId, setFarmId] = useState<string | null>(readStoredFarm);

  const endSession = useCallback(() => {
    forgetOfflineUser();
    void cacheClear();
    setAccessToken(null);
    setActiveFarmId(null);
    setUser(null);
    setStatus('anonymous');
    queryClient.clear();
  }, [queryClient]);

  // Resume a session after a reload, using the refresh cookie.
  useEffect(() => {
    if (status !== 'loading') return;
    let cancelled = false;
    void refreshSession().then((session) => {
      if (cancelled) return;
      if (session) {
        setUser(session.user);
        setStatus('authenticated');
      } else {
        setStatus('anonymous');
      }
    });
    return () => {
      cancelled = true;
    };
  }, [status]);

  useEffect(() => {
    setSessionEndedHandler(endSession);
    return () => setSessionEndedHandler(null);
  }, [endSession]);

  // Offline changes sync in the background; afterwards every screen reloads its data.
  useEffect(() => {
    if (status !== 'authenticated') return;
    onSynced(() => void queryClient.invalidateQueries());
    return startSyncLoop();
  }, [status, queryClient]);

  const farmsQuery = useQuery({
    queryKey: ['me', 'farms'],
    queryFn: () => api<MyFarm[]>('/me/farms'),
    enabled: status === 'authenticated' && !user?.must_change_password,
  });

  const farms = useMemo(() => farmsQuery.data ?? [], [farmsQuery.data]);
  const activeFarm = farms.find((m) => m.farm.id === farmId) ?? farms[0] ?? null;

  // Set synchronously during render so the first farm-scoped request already carries it.
  setActiveFarmId(activeFarm?.farm.id ?? null);

  // Save the field data for offline use once the farm is known (and again on farm switch).
  const activeId = activeFarm?.farm.id;
  useEffect(() => {
    if (activeId && import.meta.env.MODE !== 'test') void prefetchForOffline();
  }, [activeId]);

  const startSession = useCallback(
    (session: Session) => {
      setAccessToken(session.access);
      setUser(session.user);
      setStatus('authenticated');
      void queryClient.invalidateQueries({ queryKey: ['me', 'farms'] });
    },
    [queryClient],
  );

  const logout = useCallback(async () => {
    try {
      await api('/auth/logout', { method: 'POST', noRefresh: true });
    } finally {
      await discardAll();
      endSession();
    }
  }, [endSession]);

  const switchFarm = useCallback(
    (id: string) => {
      setFarmId(id);
      setActiveFarmId(id);
      try {
        window.localStorage.setItem(FARM_KEY, id);
      } catch {
        /* storage unavailable: the choice lasts for this tab only */
      }
      // Nothing cached for the previous farm may leak into the next one.
      queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== 'me' });
    },
    [queryClient],
  );

  const value = useMemo<SessionValue>(
    () => ({
      status,
      user,
      farms,
      farmsLoading: farmsQuery.isPending && status === 'authenticated' && !user?.must_change_password,
      activeFarm,
      role: activeFarm?.role as Role | undefined,
      startSession,
      setUser,
      logout,
      switchFarm,
      refetchFarms: () => void farmsQuery.refetch(),
    }),
    [status, user, farms, farmsQuery, activeFarm, startSession, logout, switchFarm],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession must be used inside <SessionProvider>');
  return ctx;
}
