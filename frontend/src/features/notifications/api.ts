import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';

import { accessTokenForDownload, api, type Schemas } from '@/api/client';

export type Notification = Schemas['Notification'];
export type Delivery = Schemas['Delivery'];
export type Preferences = Schemas['Preferences'];
export type Contact = Schemas['Contact'];
export interface Usage {
  channel: string;
  label: string;
  used: number;
  allowance: number | null;
  month: string;
}

export const CHANNELS = [
  ['in_app', 'In-app'],
  ['whatsapp', 'WhatsApp'],
  ['sms', 'SMS'],
  ['email', 'Email'],
] as const;
export const CHANNEL_LABEL: Record<string, string> = Object.fromEntries(CHANNELS);

const POLL_MS = 60_000;

/** The bell badge: polls every 60 seconds; the WebSocket makes it instant. */
export function useUnreadCount(enabled = true) {
  return useQuery({
    queryKey: ['notifications', 'unread-count'],
    queryFn: () => api<{ unread: number; urgent: number }>('/notifications/unread-count'),
    refetchInterval: POLL_MS,
    enabled,
  });
}

/** Opens /ws/notifications and refreshes notification queries when something arrives.
 * Gives up quietly after a few failures (polling keeps working). */
export function useLiveNotifications(enabled: boolean) {
  const queryClient = useQueryClient();
  useEffect(() => {
    if (!enabled || typeof WebSocket === 'undefined') return;
    let socket: WebSocket | null = null;
    let failures = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;

    const connect = () => {
      const token = accessTokenForDownload();
      if (!token || stopped) return;
      const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
      const base = import.meta.env.VITE_WS_BASE_URL ?? `${scheme}://${window.location.host}`;
      socket = new WebSocket(`${base}/ws/notifications?token=${encodeURIComponent(token)}`);
      socket.onopen = () => {
        failures = 0;
      };
      socket.onmessage = (e) => {
        try {
          const data = JSON.parse(String(e.data)) as { type?: string };
          if (data.type === 'notification.new') {
            void queryClient.invalidateQueries({ queryKey: ['notifications'] });
          }
        } catch {
          /* ignore malformed frames */
        }
      };
      socket.onclose = () => {
        if (stopped) return;
        failures += 1;
        if (failures <= 5) timer = setTimeout(connect, 2_000 * 2 ** failures);
      };
    };
    connect();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      socket?.close();
    };
  }, [enabled, queryClient]);
}

export function markRead(id: string) {
  return api<Notification>(`/notifications/${id}/read`, { method: 'POST' });
}

export function usePreferences() {
  return useQuery({
    queryKey: ['notifications', 'preferences'],
    queryFn: () => api<Preferences>('/notification-preferences'),
  });
}

export function useContacts() {
  return useQuery({
    queryKey: ['notifications', 'contacts'],
    queryFn: () => api<Contact[]>('/channel-contacts'),
  });
}

export function useUsage(enabled: boolean) {
  return useQuery({
    queryKey: ['notifications', 'usage'],
    queryFn: () => api<Usage[]>('/notifications/usage'),
    enabled,
  });
}

/** "5 min ago", "Yesterday 14:05", "3 Mar 2026". */
export function timeAgo(value: string, now = new Date()) {
  const d = new Date(value);
  const mins = Math.round((now.getTime() - d.getTime()) / 60_000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24 && d.getDate() === now.getDate()) return `${hours} h ago`;
  const time = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (d.toDateString() === yesterday.toDateString()) return `Yesterday ${time}`;
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}
