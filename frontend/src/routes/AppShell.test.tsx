import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { mockApi, renderWithProviders } from '@/test/utils';

import { AppRoutes } from './AppRoutes';

const me = {
  id: 'u1',
  username: 'grace',
  first_name: 'Grace',
  last_name: 'Wanjiru',
  full_name: 'Grace Wanjiru',
  email: 'grace@example.com',
  phone: '',
  photo: null,
  language: 'en',
  email_verified: true,
  phone_verified: false,
  must_change_password: false,
};

function farm(id: string, name: string, role: string, role_label: string) {
  return {
    id: `m-${id}`,
    farm: { id, name, slug: id, status: 'active' },
    role,
    role_label,
    status: 'active',
    joined_at: '2026-01-01T00:00:00Z',
    permissions: {},
  };
}

describe('app shell', () => {
  beforeEach(() => window.localStorage.clear());

  it('shows the sign-in stand-in when not signed in', async () => {
    mockApi(() => ({ status: 401, body: { errors: { detail: ['Authentication required.'] } } }));
    renderWithProviders(<AppRoutes />);
    expect(await screen.findByText(/sign-in arrives in phase 2/i)).toBeInTheDocument();
  });

  it('shows a farm manager the sidebar without User Management or Settings', async () => {
    mockApi((url) => {
      if (url.pathname === '/api/v1/me') return { body: me };
      if (url.pathname === '/api/v1/me/farms')
        return { body: [farm('f1', 'YPA FARM', 'farm_manager', 'Farm Manager')] };
    });
    renderWithProviders(<AppRoutes />, { route: '/dashboard' });
    const nav = await screen.findByRole('navigation', { name: 'Main navigation' });
    expect(within(nav).getByRole('link', { name: 'Livestock' })).toBeInTheDocument();
    expect(within(nav).getByRole('link', { name: 'Reports' })).toBeInTheDocument();
    expect(within(nav).queryByRole('link', { name: 'User Management' })).not.toBeInTheDocument();
    expect(within(nav).queryByRole('link', { name: 'Settings' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'Dashboard' })).toBeInTheDocument();
  });

  it('hides routes the role cannot use', async () => {
    mockApi((url) => {
      if (url.pathname === '/api/v1/me') return { body: me };
      if (url.pathname === '/api/v1/me/farms')
        return { body: [farm('f1', 'YPA FARM', 'farm_manager', 'Farm Manager')] };
    });
    renderWithProviders(<AppRoutes />, { route: '/users' });
    expect(await screen.findByText('Page not found')).toBeInTheDocument();
  });

  it('gives attendants the phone layout with bottom navigation', async () => {
    mockApi((url) => {
      if (url.pathname === '/api/v1/me') return { body: me };
      if (url.pathname === '/api/v1/me/farms')
        return { body: [farm('f1', 'YPA FARM', 'livestock_attendant', 'Livestock Attendant')] };
    });
    renderWithProviders(<AppRoutes />, { route: '/activities' });
    const nav = await screen.findByRole('navigation', { name: 'Main navigation' });
    const labels = within(nav)
      .getAllByRole('link')
      .map((a) => a.textContent);
    expect(labels).toEqual(['Home', 'Tasks', 'Animals', 'Calendar', 'Alerts']);
    expect(screen.getByText('YPA FARM')).toBeInTheDocument();
  });

  it('switching farm sends the new X-Farm-ID', async () => {
    const fetchMock = mockApi((url) => {
      if (url.pathname === '/api/v1/me') return { body: me };
      if (url.pathname === '/api/v1/me/farms')
        return {
          body: [
            farm('f1', 'YPA FARM', 'administrator', 'Administrator'),
            farm('f2', 'Second Farm', 'farm_manager', 'Farm Manager'),
          ],
        };
    });
    renderWithProviders(<AppRoutes />, { route: '/dashboard' });
    const select = await screen.findByLabelText('Switch farm');
    expect(screen.getByRole('link', { name: 'User Management' })).toBeInTheDocument();
    await userEvent.selectOptions(select, 'f2');
    expect(screen.queryByRole('link', { name: 'User Management' })).not.toBeInTheDocument();
    expect(window.localStorage.getItem('sf.activeFarmId')).toBe('f2');
    const { api } = await import('@/api/client');
    await api('/anything').catch(() => undefined);
    const last = fetchMock.mock.calls.at(-1)!;
    expect((last[1]!.headers as Record<string, string>)['X-Farm-ID']).toBe('f2');
  });
});
