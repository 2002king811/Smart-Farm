import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AppRoutes } from '@/routes/AppRoutes';
import { clearSession, membership, renderWithProviders, signedInApi } from '@/test/utils';

const member = {
  id: 'm2',
  user_id: 'u2',
  username: 'peter.otieno',
  first_name: 'Peter',
  last_name: 'Otieno',
  full_name: 'Peter Otieno',
  email: 'peter@ypa.co.ke',
  phone: '',
  photo: null,
  email_verified: false,
  phone_verified: false,
  last_login: null,
  role: 'livestock_attendant',
  role_label: 'Livestock Attendant',
  status: 'active',
  job_title: '',
  joined_at: '2026-11-01T00:00:00Z',
  invited_by_name: 'Grace Wanjiru',
};

describe('User Management', () => {
  beforeEach(clearSession);

  it('lists members and invites a new person', async () => {
    let invited: Record<string, unknown> | null = null;
    signedInApi([membership('f1', 'YPA FARM', 'administrator', 'Administrator')], (url, init) => {
      if (url.pathname === '/api/v1/members')
        return { body: { count: 1, next: null, previous: null, results: [member] } };
      if (url.pathname === '/api/v1/invitations' && init?.method === 'POST') {
        invited = JSON.parse(String(init.body));
        return { status: 201, body: { id: 'i1' } };
      }
      if (url.pathname === '/api/v1/invitations')
        return { body: { count: 0, next: null, previous: null, results: [] } };
    });
    renderWithProviders(<AppRoutes />, { route: '/users' });
    const table = await screen.findByRole('table');
    expect(within(table).getByText('Peter Otieno')).toBeInTheDocument();
    expect(within(table).getByText('Livestock Attendant')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Add user' }));
    const dialog = await screen.findByRole('dialog', { name: 'Add user' });
    await userEvent.click(within(dialog).getByRole('button', { name: 'Send invitation' }));
    expect(await within(dialog).findByText('Enter a first name.')).toBeInTheDocument();
    expect(invited).toBeNull();

    await userEvent.type(within(dialog).getByLabelText('First name'), 'Grace');
    await userEvent.type(
      within(dialog).getByLabelText('Email', { selector: 'input[type=email]' }),
      'grace@ypa.co.ke',
    );
    await userEvent.selectOptions(within(dialog).getByLabelText('Role'), 'farm_manager');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Send invitation' }));
    expect(await screen.findByText('Invitation sent to Grace.')).toBeInTheDocument();
    expect(invited).toMatchObject({
      first_name: 'Grace',
      email: 'grace@ypa.co.ke',
      role: 'farm_manager',
      channels: ['email'],
    });
    expect(screen.getByRole('tab', { name: 'Invitations' })).toHaveAttribute('aria-selected', 'true');
  });

  it('does not show a success toast when the API refuses', async () => {
    signedInApi([membership('f1', 'YPA FARM', 'administrator', 'Administrator')], (url, init) => {
      if (url.pathname === '/api/v1/members')
        return { body: { count: 1, next: null, previous: null, results: [member] } };
      if (url.pathname === '/api/v1/members/m2/deactivate' && init?.method === 'POST')
        return { status: 400, body: { errors: { detail: ['You cannot deactivate yourself.'] } } };
    });
    renderWithProviders(<AppRoutes />, { route: '/users' });
    await userEvent.click(await screen.findByRole('button', { name: 'Deactivate Peter Otieno' }));
    const dialog = await screen.findByRole('dialog', { name: 'Deactivate user' });
    await userEvent.click(within(dialog).getByRole('button', { name: 'Deactivate' }));
    expect(await within(dialog).findByText('You cannot deactivate yourself.')).toBeInTheDocument();
    expect(screen.queryByText(/is now inactive/)).not.toBeInTheDocument();
  });

  it('closes dialogs with Escape and keeps focus inside while open', async () => {
    signedInApi([membership('f1', 'YPA FARM', 'administrator', 'Administrator')], (url) => {
      if (url.pathname === '/api/v1/members')
        return { body: { count: 1, next: null, previous: null, results: [member] } };
    });
    renderWithProviders(<AppRoutes />, { route: '/users' });
    await userEvent.click(await screen.findByRole('button', { name: 'Add user' }));
    const dialog = await screen.findByRole('dialog');
    expect(dialog.contains(document.activeElement)).toBe(true);
    for (let i = 0; i < 20; i++) await userEvent.tab();
    expect(dialog.contains(document.activeElement)).toBe(true);
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
