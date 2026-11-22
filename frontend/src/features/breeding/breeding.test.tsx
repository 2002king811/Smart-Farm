import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AppRoutes } from '@/routes/AppRoutes';
import { clearSession, membership, renderWithProviders, signedInApi } from '@/test/utils';

const page = (results: unknown[]) => ({ count: results.length, next: null, previous: null, results });
const neema = { id: 'd1', animal_id: 'YPA-002', name: 'Neema', sex: 'female' };
const simba = { id: 'b1', animal_id: 'YPA-001', name: 'Simba', sex: 'male' };

describe('breeding', () => {
  beforeEach(clearSession);

  it('shows pregnancy progress', async () => {
    signedInApi([membership('f1', 'YPA FARM', 'farm_manager', 'Farm Manager')], (url) => {
      if (url.pathname === '/api/v1/pregnancies')
        return {
          body: [
            {
              mating_id: 'm1',
              doe: 'd1',
              doe_label: 'YPA-002 Neema',
              buck_label: 'YPA-001 Simba',
              mating_date: '2026-09-01',
              pregnancy_status: 'confirmed',
              expected_kidding_date: '2027-01-29',
              days_pregnant: 81,
              days_remaining: 69,
              progress_percent: 54,
              trimester: 2,
            },
          ],
        };
    });
    renderWithProviders(<AppRoutes />, { route: '/breeding' });
    expect(await screen.findByRole('link', { name: 'YPA-002 Neema' })).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '54');
    expect(screen.getByText('69')).toBeInTheDocument();
    expect(screen.getByText('Confirmed')).toBeInTheDocument();
  });

  it('registers a birth with two kids, one stillborn', async () => {
    let posted: Record<string, unknown> | null = null;
    signedInApi([membership('f1', 'YPA FARM', 'livestock_attendant', 'Livestock Attendant')], (url, init) => {
      if (url.pathname === '/api/v1/pregnancies') return { body: [] };
      if (url.pathname === '/api/v1/animals') return { body: page([neema, simba]) };
      if (url.pathname === '/api/v1/births' && init?.method === 'POST') {
        posted = JSON.parse(String(init.body));
        return { status: 201, body: { id: 'x', kids: [{ id: 'k1', animal_id: 'YPA-021' }] } };
      }
    });
    renderWithProviders(<AppRoutes />, { route: '/breeding' });
    // Attendants may register births but not record matings.
    expect(screen.queryByRole('button', { name: /Record mating/ })).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole('button', { name: /Register birth/ }));
    const dialog = await screen.findByRole('dialog');
    await waitFor(() =>
      expect(within(dialog).getByRole('option', { name: 'YPA-002 Neema' })).toBeInTheDocument(),
    );
    expect(within(dialog).queryByRole('option', { name: 'YPA-001 Simba' })).not.toBeInTheDocument();
    await userEvent.selectOptions(within(dialog).getByLabelText('Dam (mother) *'), 'd1');
    await userEvent.click(within(dialog).getByRole('button', { name: /Add another kid/ }));
    const sexes = within(dialog).getAllByLabelText('Sex *');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Register birth' }));
    expect(await within(dialog).findAllByText('Choose female or male.')).toHaveLength(1);
    await userEvent.selectOptions(sexes[0]!, 'female');
    await userEvent.selectOptions(sexes[1]!, 'male');
    await userEvent.type(within(dialog).getAllByLabelText('Birth weight (kg)')[0]!, '3.2');
    await userEvent.click(within(dialog).getAllByLabelText('Alive')[1]!);
    await userEvent.click(within(dialog).getByRole('button', { name: 'Register birth' }));
    expect(await screen.findByText('Birth registered. YPA-021 added to the register.')).toBeInTheDocument();
    expect(posted).toMatchObject({
      dam: 'd1',
      kids: [
        { sex: 'female', birth_weight_kg: '3.2', alive: true },
        { sex: 'male', birth_weight_kg: null, alive: false },
      ],
    });
  });
});
