import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { clearSession, ME, membership, mockApi, renderWithProviders, signedInApi } from '@/test/utils';

import { AppRoutes } from './AppRoutes';

describe('app shell', () => {
  beforeEach(clearSession);

  it('sends signed-out visitors to the login page', async () => {
    mockApi(() => undefined);
    renderWithProviders(<AppRoutes />, { route: '/livestock' });
    expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument();
  });

  it('resumes a session from the refresh cookie and shows a farm manager the right sidebar', async () => {
    const fetchMock = signedInApi([membership('f1', 'YPA FARM', 'farm_manager', 'Farm Manager')]);
    renderWithProviders(<AppRoutes />, { route: '/dashboard' });
    const nav = await screen.findByRole('navigation', { name: 'Main navigation' });
    expect(within(nav).getByRole('link', { name: 'Livestock' })).toBeInTheDocument();
    expect(within(nav).getByRole('link', { name: 'Reports' })).toBeInTheDocument();
    expect(within(nav).queryByRole('link', { name: 'User Management' })).not.toBeInTheDocument();
    // Settings stays (My profile), but only with the profile tab.
    expect(within(nav).getByRole('link', { name: 'Settings' })).toBeInTheDocument();
    const refreshCall = fetchMock.mock.calls.find(([u]) => String(u).includes('/auth/refresh'))!;
    expect((refreshCall[1]!.headers as Record<string, string>)['X-CSRF-Token']).toBe('test-csrf');
  });

  it('hides routes the role cannot use', async () => {
    signedInApi([membership('f1', 'YPA FARM', 'farm_manager', 'Farm Manager')]);
    renderWithProviders(<AppRoutes />, { route: '/users' });
    expect(await screen.findByText('Page not found')).toBeInTheDocument();
  });

  it('gives attendants the phone layout with bottom navigation', async () => {
    signedInApi([membership('f1', 'YPA FARM', 'livestock_attendant', 'Livestock Attendant')]);
    renderWithProviders(<AppRoutes />, { route: '/activities' });
    const nav = await screen.findByRole('navigation', { name: 'Main navigation' });
    const labels = within(nav)
      .getAllByRole('link')
      .map((a) => a.textContent);
    expect(labels).toEqual(['Home', 'Tasks', 'Animals', 'Calendar', 'Alerts']);
  });

  it('switching farm sends the new X-Farm-ID', async () => {
    const fetchMock = signedInApi([
      membership('f1', 'YPA FARM', 'administrator', 'Administrator'),
      membership('f2', 'Second Farm', 'farm_manager', 'Farm Manager'),
    ]);
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

  it('forces a password change before anything else', async () => {
    signedInApi([], () => undefined, { ...ME, must_change_password: true });
    renderWithProviders(<AppRoutes />, { route: '/dashboard' });
    expect(await screen.findByRole('heading', { name: 'Choose your own password' })).toBeInTheDocument();
  });

  it('explains when the user belongs to no farm', async () => {
    signedInApi([]);
    renderWithProviders(<AppRoutes />, { route: '/dashboard' });
    expect(await screen.findByRole('heading', { name: 'No farm yet' })).toBeInTheDocument();
  });

  it('shows the verification banner and logs out from the user menu', async () => {
    const fetchMock = signedInApi(
      [membership('f1', 'YPA FARM', 'administrator', 'Administrator')],
      () => undefined,
      {
        ...ME,
        phone_verified: false,
      },
    );
    renderWithProviders(<AppRoutes />, { route: '/dashboard' });
    expect(await screen.findByText(/Confirm your mobile number/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Account/ }));
    await userEvent.click(screen.getByRole('menuitem', { name: 'Sign out' }));
    expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes('/auth/logout'))).toBe(true);
  });

  it('refreshes once on 401 and retries the request', async () => {
    let calls = 0;
    signedInApi([membership('f1', 'YPA FARM', 'administrator', 'Administrator')], (url) => {
      if (url.pathname === '/api/v1/protected') {
        calls += 1;
        return calls === 1
          ? { status: 401, body: { errors: { detail: ['expired'] } } }
          : { body: { ok: true } };
      }
    });
    renderWithProviders(<AppRoutes />, { route: '/dashboard' });
    await screen.findByRole('navigation', { name: 'Main navigation' });
    const { api } = await import('@/api/client');
    await expect(api('/protected')).resolves.toEqual({ ok: true });
    await waitFor(() => expect(calls).toBe(2));
  });
});
