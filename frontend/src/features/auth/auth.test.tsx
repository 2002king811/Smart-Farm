import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { passwordStrength } from '@/components/forms';
import { AppRoutes } from '@/routes/AppRoutes';
import { clearSession, ME, membership, mockApi, renderWithProviders } from '@/test/utils';

describe('login', () => {
  beforeEach(clearSession);

  it('validates before calling the API', async () => {
    const fetchMock = mockApi(() => undefined);
    renderWithProviders(<AppRoutes />, { route: '/login' });
    await userEvent.click(await screen.findByRole('button', { name: 'Log in' }));
    expect(await screen.findByText('Enter your username, email or phone number.')).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('shows the server error and does not sign in', async () => {
    mockApi((url) =>
      url.pathname === '/api/v1/auth/login'
        ? { status: 400, body: { errors: { detail: ['Incorrect username, email, phone or password.'] } } }
        : undefined,
    );
    renderWithProviders(<AppRoutes />, { route: '/login' });
    await userEvent.type(await screen.findByLabelText('Username, email or phone'), 'grace');
    await userEvent.type(screen.getByLabelText('Password'), 'wrong-pass');
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Incorrect username, email, phone or password.',
    );
    expect(screen.getByRole('heading', { name: 'Log in' })).toBeInTheDocument();
  });

  it('signs in and opens the dashboard', async () => {
    const fetchMock = mockApi((url) => {
      if (url.pathname === '/api/v1/auth/login') return { body: { access: 'a1', user: ME } };
      if (url.pathname === '/api/v1/me/farms')
        return { body: [membership('f1', 'YPA FARM', 'administrator', 'Administrator')] };
    });
    renderWithProviders(<AppRoutes />, { route: '/login' });
    await userEvent.type(await screen.findByLabelText('Username, email or phone'), 'grace');
    await userEvent.type(screen.getByLabelText('Password'), 'Correct-Pass-1');
    await userEvent.click(screen.getByLabelText('Remember me for 30 days'));
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Dashboard' })).toBeInTheDocument();
    const body = JSON.parse(String(fetchMock.mock.calls[0]![1]!.body));
    expect(body).toEqual({ identifier: 'grace', password: 'Correct-Pass-1', remember: true });
  });
});

describe('sign-up', () => {
  beforeEach(clearSession);

  it('walks through three steps and returns server errors to the right step', async () => {
    let posted: Record<string, unknown> = {};
    mockApi((url, init) => {
      if (url.pathname === '/api/v1/auth/signup') {
        posted = JSON.parse(String(init!.body));
        return { status: 400, body: { errors: { email: ['An account with this email already exists.'] } } };
      }
    });
    renderWithProviders(<AppRoutes />, { route: '/signup' });
    await userEvent.click(await screen.findByRole('button', { name: 'Continue' }));
    expect(await screen.findByText('Enter your first name.')).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText('First name'), 'Daniel');
    await userEvent.type(screen.getByLabelText('Last name'), 'Mwangi');
    await userEvent.type(screen.getByLabelText('Email'), 'daniel@ypa.co.ke');
    await userEvent.clear(screen.getByLabelText('Mobile number'));
    await userEvent.type(screen.getByLabelText('Mobile number'), '0712345678');
    await userEvent.type(screen.getByLabelText('Password'), 'Green-Pasture-27');
    expect(screen.getByText(/Password strength: Strong/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Continue' }));

    await userEvent.type(await screen.findByLabelText('Farm name'), 'YPA FARM');
    await userEvent.click(screen.getByRole('button', { name: 'Continue' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Create account' }));

    // Back on step 1 with the server's message under Email.
    expect(await screen.findByText('An account with this email already exists.')).toBeInTheDocument();
    expect(screen.getByText(/Step 1 of 3/)).toBeInTheDocument();
    expect(posted).toMatchObject({ farm_name: 'YPA FARM', livestock_types: ['goats'], phone: '0712345678' });
  });

  it('scores password strength', () => {
    expect(passwordStrength('abc').label).toBe('Too short');
    expect(passwordStrength('abcdefgh').label).toBe('Weak');
    expect(passwordStrength('Abcdefgh').label).toBe('Fair');
    expect(passwordStrength('Green-Pasture-27').label).toBe('Strong');
  });
});
