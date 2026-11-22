import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AppRoutes } from '@/routes/AppRoutes';
import { clearSession, membership, renderWithProviders, signedInApi } from '@/test/utils';

const hay = {
  id: 'h1',
  name: 'Rhodes grass hay',
  category: 'forage',
  unit: 'bale',
  reorder_level: '10.00',
  unit_cost_cents: 45000,
  stock_quantity: '6.00',
  is_low: true,
  days_left: 3,
  average_daily_use: '2.00',
  notes: '',
};
const summary = {
  feed_items: 1,
  low_stock_items: 1,
  feedings_today: 2,
  feed_cost_this_month_cents: 900000,
  last_hygiene_score: 4,
};

function nutritionApi(
  role: string,
  extra: (u: URL, i?: RequestInit) => { status?: number; body?: unknown } | undefined = () => undefined,
) {
  return signedInApi([membership('f1', 'YPA FARM', role, role)], (url, init) => {
    const hit = extra(url, init);
    if (hit) return hit;
    if (url.pathname === '/api/v1/nutrition/summary') return { body: summary };
    if (url.pathname === '/api/v1/feed-items') return { body: [hay] };
    if (url.pathname === '/api/v1/feeding-records')
      return { body: { count: 0, next: null, previous: null, results: [] } };
    if (url.pathname.startsWith('/api/v1/')) return { body: [] };
  });
}

describe('nutrition', () => {
  beforeEach(clearSession);

  it('shows stock, low stock and days left, and records a purchase', async () => {
    let posted: Record<string, unknown> | null = null;
    nutritionApi('farm_manager', (url, init) => {
      if (url.pathname === '/api/v1/feed-items/h1/stock' && init?.method === 'POST') {
        posted = JSON.parse(String(init.body));
        return { body: { ...hay, stock_quantity: '26.00' } };
      }
    });
    renderWithProviders(<AppRoutes />, { route: '/nutrition' });
    const table = await screen.findByRole('table');
    expect(within(table).getByText('Low stock')).toBeInTheDocument();
    expect(within(table).getByText('3 days')).toBeInTheDocument();
    expect(screen.getByText('KES 9,000')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Update stock of Rhodes grass hay' }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText('Quantity (bale)'), '20');
    await userEvent.type(within(dialog).getByLabelText('Supplier'), 'Nakuru Agrovet');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('Rhodes grass hay: 26 bale in stock.')).toBeInTheDocument();
    expect(posted).toMatchObject({
      kind: 'purchase',
      quantity: '20',
      unit_cost_cents: 45000,
      supplier: 'Nakuru Agrovet',
    });
  });

  it('lets attendants record feeding but not change stock', async () => {
    let posted: Record<string, unknown> | null = null;
    nutritionApi('livestock_attendant', (url, init) => {
      if (url.pathname === '/api/v1/feeding-records' && init?.method === 'POST') {
        posted = JSON.parse(String(init.body));
        return { status: 201, body: { id: 'f1' } };
      }
    });
    renderWithProviders(<AppRoutes />, { route: '/nutrition/stock' });
    await screen.findByRole('table');
    expect(screen.queryByRole('button', { name: /Update stock/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: 'Feeding' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Record feeding' }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.selectOptions(await within(dialog).findByLabelText('Feed *'), 'h1');
    expect(
      within(dialog).getByRole('option', { name: 'Rhodes grass hay (6 bale in stock)' }),
    ).toBeInTheDocument();
    await userEvent.type(within(dialog).getByLabelText('Quantity given *'), '2');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('The feeding was recorded.')).toBeInTheDocument();
    expect(posted).toMatchObject({ feed_item: 'h1', quantity: '2' });
  });
});
