import { useQuery, useQueryClient } from '@tanstack/react-query';
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { api, ApiError, setActiveFarmId, type Schemas } from '@/api/client';
import type { Role } from '@/routes/permissions';

export type Me = Schemas['Me'];
export type MyFarm = Schemas['MyFarm'];

const FARM_KEY = 'sf.activeFarmId';

interface SessionValue {
  status: 'loading' | 'anonymous' | 'authenticated' | 'preview';
  user: Me | null;
  farms: MyFarm[];
  activeFarm: MyFarm | null;
  role: Role | undefined;
  switchFarm: (farmId: string) => void;
  /** Development only: view the shell as a role before sign-in exists (removed in phase 2). */
  startPreview: (role: Role) => void;
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
  const [farmId, setFarmId] = useState<string | null>(readStoredFarm);
  const [previewRole, setPreviewRole] = useState<Role | null>(null);

  const me = useQuery({
    queryKey: ['me'],
    queryFn: () => api<Me>('/me'),
    retry: (count, err) => !(err instanceof ApiError && err.status === 401) && count < 2,
    enabled: previewRole === null,
  });
  const farms = useQuery({
    queryKey: ['me', 'farms'],
    queryFn: () => api<MyFarm[]>('/me/farms'),
    enabled: me.isSuccess,
  });

  const farmList = useMemo(() => farms.data ?? [], [farms.data]);
  const activeFarm = farmList.find((m) => m.farm.id === farmId) ?? farmList[0] ?? null;

  useEffect(() => {
    setActiveFarmId(activeFarm?.farm.id ?? null);
  }, [activeFarm]);

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

  const value = useMemo<SessionValue>(() => {
    if (previewRole) {
      return {
        status: 'preview',
        user: null,
        farms: [],
        activeFarm: null,
        role: previewRole,
        switchFarm,
        startPreview: setPreviewRole,
      };
    }
    const status =
      me.isPending || (me.isSuccess && farms.isPending)
        ? 'loading'
        : me.isSuccess
          ? 'authenticated'
          : 'anonymous';
    return {
      status,
      user: me.data ?? null,
      farms: farmList,
      activeFarm,
      role: activeFarm?.role as Role | undefined,
      switchFarm,
      startPreview: setPreviewRole,
    };
  }, [previewRole, me.isPending, me.isSuccess, me.data, farms.isPending, farmList, activeFarm, switchFarm]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession must be used inside <SessionProvider>');
  return ctx;
}
