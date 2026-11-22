import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AppRoutes } from '@/routes/AppRoutes';
import { clearSession, membership, renderWithProviders, signedInApi } from '@/test/utils';

import { iso } from './api';

const today = iso(new Date());
const vaccination = { id: 'c1', name: 'Vaccination', key: 'vaccination', colour: '#2E7D32', icon: 'syringe' };
const task = {
  id: 't1',
  title: 'Vaccination due: PPR vaccine – YPA-001',
  category: vaccination,
  date: today,
  start_time: null,
  end_time: null,
  all_day: true,
  assigned_to: { id: 'u1', name: 'Grace Wanjiru' },
  animals: [{ id: 'a1', animal_id: 'YPA-001', name: 'Simba' }],
  group: null,
  description: '',
  priority: 'high',
  status: 'pending',
  reminder_days: [7, 1],
  recurrence_rule: '',
  is_recurring: false,
  series_id: null,
  completed_at: null,
  completed_by_name: null,
  source: 'vaccination',
  source_label: 'Vaccination',
  source_record: { type: 'vaccination', id: 'v1' },
  template_key: '',
  created_by_name: 'Grace Wanjiru',
  created_at: `${today}T08:00:00Z`,
  updated_at: `${today}T08:00:00Z`,
};
const page = (results: unknown[]) => ({ count: results.length, next: null, previous: null, results });

function calendarApi(
  role: string,
  extra: (u: URL, i?: RequestInit) => { status?: number; body?: unknown } | undefined = () => undefined,
) {
  return signedInApi([membership('f1', 'YPA FARM', role, role)], (url, init) => {
    const hit = extra(url, init);
    if (hit) return hit;
    if (url.pathname === '/api/v1/activities/calendar')
      return { body: { view: url.searchParams.get('view'), start: today, end: today, activities: [task] } };
    if (url.pathname === '/api/v1/activity-categories') return { body: [vaccination] };
    if (url.pathname === '/api/v1/activity-templates')
      return {
        body: [
          {
            key: 'health-calendar-2027',
            name: '2027 health calendar',
            description: '23 planned',
            count: 23,
            applied: 0,
          },
        ],
      };
    if (url.pathname === '/api/v1/activities/t1') return { body: task };
    if (url.pathname.startsWith('/api/v1/activities/t1/')) return { body: [] };
    if (url.pathname === '/api/v1/activities/assignees') return { body: [] };
    if (url.pathname === '/api/v1/activities') return { body: page([task]) };
  });
}

describe('health calendar', () => {
  beforeEach(clearSession);

  it('shows activities in the month grid and opens the detail', async () => {
    calendarApi('farm_manager');
    renderWithProviders(<AppRoutes />, { route: '/calendar' });
    const chip = await screen.findByRole('button', {
      name: /Vaccination due: PPR vaccine – YPA-001, pending/,
    });
    await userEvent.click(chip);
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Grace Wanjiru')).toBeInTheDocument();
    expect(within(dialog).getByRole('link', { name: 'YPA-001' })).toHaveAttribute('href', '/livestock/a1');
    expect(within(dialog).getByRole('button', { name: 'Mark complete' })).toBeInTheDocument();
  });

  it('switches views and applies the 2027 plan once', async () => {
    let applied = false;
    const fetchMock = calendarApi('administrator', (url, init) => {
      if (
        url.pathname === '/api/v1/activity-templates/health-calendar-2027/apply' &&
        init?.method === 'POST'
      ) {
        applied = true;
        return { body: { created: 23, skipped: 0 } };
      }
    });
    renderWithProviders(<AppRoutes />, { route: '/calendar' });
    await userEvent.click(await screen.findByRole('button', { name: 'Agenda' }));
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([u]) => String(u).includes('view=agenda'))).toBe(true),
    );
    await userEvent.click(screen.getByRole('button', { name: 'Add the 23 activities' }));
    expect(await screen.findByText('23 planned activities added to the calendar.')).toBeInTheDocument();
    expect(applied).toBe(true);
  });

  it('hides the template and new activity from attendants', async () => {
    calendarApi('livestock_attendant');
    renderWithProviders(<AppRoutes />, { route: '/calendar' });
    await screen.findByRole('button', { name: /Vaccination due/ });
    expect(screen.queryByRole('button', { name: /Add the 23/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /New activity/ })).not.toBeInTheDocument();
  });
});

describe('activities', () => {
  beforeEach(clearSession);

  it('gives attendants "My tasks" with a working Complete button', async () => {
    let completed = false;
    calendarApi('livestock_attendant', (url, init) => {
      if (url.pathname === '/api/v1/activities/t1/complete' && init?.method === 'POST') {
        completed = true;
        return { body: { ...task, status: 'completed' } };
      }
    });
    renderWithProviders(<AppRoutes />, { route: '/activities' });
    expect(await screen.findByRole('heading', { name: 'My tasks' })).toBeInTheDocument();
    expect(screen.queryByLabelText('Assigned to')).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole('button', { name: 'Complete' }));
    expect(await screen.findByText(/Completed: Vaccination due/)).toBeInTheDocument();
    expect(completed).toBe(true);
  });
});
