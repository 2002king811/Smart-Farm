import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AppRoutes } from '@/routes/AppRoutes';
import { clearSession, membership, renderWithProviders, signedInApi } from '@/test/utils';

const page = (results: unknown[]) => ({ count: results.length, next: null, previous: null, results });
const goat = { id: 'a1', animal_id: 'YPA-001', name: 'Simba' };

describe('animal health', () => {
  beforeEach(clearSession);

  it('records a vaccination from the catalogue and fills the next due date', async () => {
    let posted: Record<string, unknown> | null = null;
    signedInApi([membership('f1', 'YPA FARM', 'farm_manager', 'Farm Manager')], (url, init) => {
      if (url.pathname === '/api/v1/health/summary')
        return {
          body: {
            status_counts: { healthy: 4 },
            ongoing_treatments: 1,
            under_withdrawal: 0,
            vaccinations_due_30_days: 2,
            overdue_health_activities: 0,
            observations_7_days: 0,
          },
        };
      if (url.pathname === '/api/v1/vaccinations' && init?.method === 'POST') {
        posted = JSON.parse(String(init.body));
        return { status: 201, body: { id: 'v1' } };
      }
      if (url.pathname === '/api/v1/vaccinations') return { body: page([]) };
      if (url.pathname === '/api/v1/animals') return { body: page([goat]) };
      if (url.pathname === '/api/v1/animal-groups') return { body: [] };
      if (url.pathname === '/api/v1/vaccines')
        return {
          body: [
            {
              id: 'vx',
              name: 'PPR vaccine',
              disease_category: 'ppr',
              default_dose: '1 ml',
              route: 'sc',
              booster_interval_days: 365,
            },
          ],
        };
    });
    renderWithProviders(<AppRoutes />, { route: '/health' });
    expect(await screen.findByText('Vaccinations due (30 days)')).toBeInTheDocument();
    await userEvent.click(await screen.findByRole('button', { name: 'Record vaccination' }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.selectOptions(within(dialog).getByLabelText('Animal'), 'a1');
    await waitFor(() =>
      expect(within(dialog).getByRole('option', { name: 'PPR vaccine' })).toBeInTheDocument(),
    );
    await userEvent.selectOptions(within(dialog).getByLabelText('Vaccine'), 'vx');
    expect(within(dialog).getByLabelText('Disease')).toHaveValue('ppr');
    expect((within(dialog).getByLabelText('Next due date') as HTMLInputElement).value).not.toBe('');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('The vaccination was recorded.')).toBeInTheDocument();
    expect(posted).toMatchObject({
      animal: 'a1',
      vaccine: 'vx',
      disease_category: 'ppr',
      dosage: '1 ml',
    });
    expect(posted).not.toHaveProperty('group'); // empty fields are left out of new records
  });

  it('requires the fields the backend requires', async () => {
    signedInApi([membership('f1', 'YPA FARM', 'livestock_attendant', 'Livestock Attendant')], (url) => {
      if (url.pathname === '/api/v1/health/summary') return { body: { status_counts: {} } };
      if (url.pathname === '/api/v1/treatments') return { body: page([]) };
      if (url.pathname === '/api/v1/animals') return { body: page([goat]) };
      if (url.pathname.startsWith('/api/v1/')) return { body: [] };
    });
    renderWithProviders(<AppRoutes />, { route: '/health/treatments' });
    await userEvent.click(await screen.findByRole('button', { name: 'Record treatment' }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    expect(await within(dialog).findByText('Animal is required.')).toBeInTheDocument();
  });
});
