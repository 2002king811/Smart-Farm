import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AppRoutes } from '@/routes/AppRoutes';
import { clearSession, membership, renderWithProviders, signedInApi } from '@/test/utils';

import { timeAgo } from './api';

const note = {
  id: 'n1',
  event_type: 'task.assigned',
  event_label: 'Task assigned',
  title: 'New task: Dip the herd',
  message: 'Grace assigned you Dip the herd for 24 Nov 2026.',
  link: '/activities?activity=a1',
  urgent: false,
  read: false,
  read_at: null,
  created_at: new Date().toISOString(),
  deliveries: [
    {
      id: 'd1',
      channel: 'sms',
      status: 'delivered',
      error: '',
      attempts: 1,
      send_after: null,
      sent_at: null,
      status_at: null,
    },
    {
      id: 'd2',
      channel: 'whatsapp',
      status: 'failed',
      error: 'WhatsApp not switched on',
      attempts: 0,
      send_after: null,
      sent_at: null,
      status_at: null,
    },
  ],
};

const prefs = {
  matrix: [
    {
      event_type: 'activity.overdue',
      label: 'Overdue activity',
      channels: { in_app: true, whatsapp: true, sms: true, email: false },
    },
  ],
  settings: {
    quiet_hours_enabled: true,
    quiet_start: '21:00:00',
    quiet_end: '06:00:00',
    digest_time: '07:00:00',
    language: 'en',
    default_reminder_days: 1,
  },
};

describe('notifications', () => {
  beforeEach(clearSession);

  it('shows the bell count, lists notifications with delivery status and marks them read', async () => {
    const read: string[] = [];
    signedInApi([membership('f1', 'YPA FARM', 'livestock_attendant', 'Attendant')], (url, init) => {
      if (url.pathname === '/api/v1/notifications/unread-count') return { body: { unread: 1, urgent: 0 } };
      if (url.pathname === '/api/v1/notifications')
        return { body: { count: 1, next: null, previous: null, results: [note] } };
      if (url.pathname === '/api/v1/notifications/n1/read' && init?.method === 'POST') {
        read.push('n1');
        return { body: { ...note, read: true } };
      }
      if (url.pathname.startsWith('/api/v1/')) return { body: [] };
    });
    renderWithProviders(<AppRoutes />, { route: '/notifications' });
    expect(await screen.findByText('New task: Dip the herd')).toBeInTheDocument();
    expect(await screen.findByTestId('bell-count')).toHaveTextContent('1');
    const delivery = screen.getByRole('list', { name: 'Delivery' });
    expect(within(delivery).getByText('Delivered')).toBeInTheDocument();
    expect(within(delivery).getByText('Failed')).toBeInTheDocument();
    expect(within(delivery).getByText('WhatsApp not switched on')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /New task: Dip the herd/ }));
    expect(read).toEqual(['n1']);
  });

  it('saves the channel matrix and quiet hours', async () => {
    let saved: { matrix: { channels: Record<string, boolean> }[]; settings: Record<string, unknown> } | null =
      null;
    signedInApi([membership('f1', 'YPA FARM', 'farm_manager', 'Manager')], (url, init) => {
      if (url.pathname === '/api/v1/notification-preferences') {
        if (init?.method === 'PUT') {
          saved = JSON.parse(String(init.body));
          return { body: saved };
        }
        return { body: prefs };
      }
      if (url.pathname === '/api/v1/notifications/unread-count') return { body: { unread: 0, urgent: 0 } };
      if (url.pathname.startsWith('/api/v1/')) return { body: [] };
    });
    renderWithProviders(<AppRoutes />, { route: '/settings/notifications' });
    await userEvent.click(await screen.findByRole('checkbox', { name: 'Overdue activity: SMS' }));
    await userEvent.clear(screen.getByLabelText('Quiet from'));
    await userEvent.type(screen.getByLabelText('Quiet from'), '22:00');
    await userEvent.click(screen.getByRole('button', { name: 'Save notification settings' }));
    expect(await screen.findByText('Notification settings saved.')).toBeInTheDocument();
    expect(saved!.matrix[0]?.channels.sms).toBe(false);
    expect(saved!.settings.quiet_start).toBe('22:00');
    // Usage is for administrators only.
    expect(screen.queryByText('Messages this month')).not.toBeInTheDocument();
  });

  it('formats times', () => {
    const now = new Date('2026-11-22T12:00:00');
    expect(timeAgo('2026-11-22T11:55:00', now)).toBe('5 min ago');
    expect(timeAgo('2026-11-21T09:05:00', now)).toBe('Yesterday 09:05');
    expect(timeAgo('2026-03-03T09:05:00', now)).toBe('3 Mar 2026');
  });
});
