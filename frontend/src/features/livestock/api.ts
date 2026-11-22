import { useQuery } from '@tanstack/react-query';

import {
  accessTokenForDownload,
  api,
  API_BASE,
  getActiveFarmId,
  refreshSession,
  type Schemas,
} from '@/api/client';

export type AnimalRow = Schemas['AnimalList'];
export type Animal = Schemas['AnimalDetail'];
export type Weight = Schemas['WeightRecord'];
export type Photo = Schemas['AnimalPhoto'];
export type Location = Schemas['Location'];
export type Group = Schemas['AnimalGroup'];
export type TimelineEvent = Schemas['TimelineEvent'];

export const keys = {
  all: ['animals'] as const,
  detail: (id: string) => ['animals', id] as const,
  weights: (id: string) => ['animals', id, 'weights'] as const,
  photos: (id: string) => ['animals', id, 'photos'] as const,
  timeline: (id: string) => ['animals', id, 'timeline'] as const,
};

export function useAnimal(id: string) {
  return useQuery({ queryKey: keys.detail(id), queryFn: () => api<Animal>(`/animals/${id}`) });
}

export function useLocations() {
  return useQuery({
    queryKey: ['locations'],
    queryFn: () => api<Location[]>('/locations'),
    staleTime: 60_000,
  });
}

export function useGroups() {
  return useQuery({
    queryKey: ['animal-groups'],
    queryFn: () => api<Group[]>('/animal-groups'),
    staleTime: 60_000,
  });
}

/** Possible parents for the registration form. */
export function useParents(sex: 'female' | 'male', species: string) {
  return useQuery({
    queryKey: ['animals', 'parents', sex, species],
    queryFn: () =>
      api<{ results: AnimalRow[] }>('/animals', {
        query: { sex, species, page_size: 200, active: 'all' },
      }).then((r) => r.results),
    staleTime: 60_000,
  });
}

export async function uploadPhoto(animalId: string, file: File, primary = false) {
  const body = new FormData();
  body.append('file', file);
  if (primary) body.append('is_primary', 'true');
  return api<Photo>(`/animals/${animalId}/photos`, { method: 'POST', body });
}

/** Downloads an export with the session's token (a plain link would not carry it). */
export async function downloadExport(query: Record<string, string>, format: 'csv' | 'xlsx') {
  const url = new URL(`${API_BASE}/animals/export`, window.location.origin);
  Object.entries({ ...query, format }).forEach(([k, v]) => v && url.searchParams.set(k, v));
  const send = () =>
    fetch(url, {
      headers: { Authorization: `Bearer ${accessTokenForDownload()}`, 'X-Farm-ID': getActiveFarmId() ?? '' },
      credentials: 'include',
    });
  let res = await send();
  if (res.status === 401 && (await refreshSession())) res = await send();
  if (!res.ok) throw new Error('The export could not be downloaded.');
  const blob = await res.blob();
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download =
    res.headers.get('Content-Disposition')?.match(/filename="(.+)"/)?.[1] ?? `livestock.${format}`;
  link.click();
  URL.revokeObjectURL(link.href);
}
