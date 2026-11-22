import { useInfiniteQuery } from '@tanstack/react-query';

import { api, type Schemas } from '@/api/client';

export type Member = Schemas['Member'];
export type Invitation = Schemas['Invitation'];

interface Page<T> {
  count: number;
  next: string | null;
  results: T[];
}

/** Cursor-paginated list with a "Load more" button. */
export function useCursorList<T>(key: unknown[], path: string, query: Record<string, string>) {
  return useInfiniteQuery({
    queryKey: [...key, query],
    queryFn: ({ pageParam }) =>
      api<Page<T>>(pageParam ?? path, pageParam ? {} : { query: { ...query, page_size: '25' } }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next,
  });
}

export const ROLE_OPTIONS = [
  ['administrator', 'Administrator'],
  ['farm_manager', 'Farm Manager'],
  ['livestock_attendant', 'Livestock Attendant'],
] as const;

export const CHANNEL_OPTIONS = [
  ['email', 'Email'],
  ['sms', 'SMS'],
  ['whatsapp', 'WhatsApp'],
] as const;
