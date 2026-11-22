import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AppRoutes } from '@/routes/AppRoutes';
import { clearSession, membership, renderWithProviders, signedInApi } from '@/test/utils';

const summary = {
  own: false,
  today: '2026-11-22',
  from: '2026-11-01',
  to: '2026-11-30',
  period_label: '01 Nov 2026 – 30 Nov 2026',
  tasks_today: 2,
  overdue: 1,
  unread_alerts: 0,
  urgent_alerts: 0,
  activity_overview: { total: 4, completed: 2, pending: 1, overdue: 1, cancelled: 0, completion_rate: 50 },
  herd: { total: 42, males: 10, females: 32, kids: 6, needing_attention: 3, pregnant: 5 },
  health_status: { healthy: 37, sick: 2, under_treatment: 1, quarantined: 0, pregnant: 5, monitoring: 0 },
  health: { vaccinations: 12, treatments: 2, kids_born: 4, deaths: 1 },
  low_stock: 1,
};
const charts = {
  labels: ['Jun 2026', 'Jul 2026'],
  herd_size: [40, 42],
  kids_born: [1, 3],
  deaths: [0, 1],
  vaccinations: [5, 7],
  dewormings: [0, 2],
  treatments: [1, 1],
  activities_completed: [3, 4],
};
const catalog = [
  {
    key: 'vaccination',
    title: 'Vaccination Report',
    description: 'Vaccinations given in the period.',
    section: 'Health',
    default_period: 'month',
    uses_period: true,
    filters: [],
  },
];
const report = {
  key: 'vaccination',
  title: 'Vaccination Report',
  from: '2026-11-01',
  to: '2026-11-30',
  period_label: '01 Nov 2026 – 30 Nov 2026',
  group: 'week',
  filters: {},
  summary: [{ key: 'records', label: 'Vaccinations', value: 12, unit: '' }],
  chart: {
    type: 'bar',
    title: 'Vaccinations',
    labels: ['Wk 02 Nov'],
    series: [{ name: 'Vaccinations', values: [12] }],
    stacked: false,
  },
  tables: [
    {
      key: 'vaccinations',
      title: 'Vaccinations',
      columns: [
        { key: 'date', label: 'Date', type: 'date' },
        { key: 'subject', label: 'Animal / group', type: 'text' },
      ],
      rows: [{ date: '2026-11-03', subject: 'YPA-001' }],
    },
  ],
  row_count: 1,
};

function api(
  role: string,
  extra: (u: URL, i?: RequestInit) => { status?: number; body?: unknown } | undefined = () => undefined,
) {
  return signedInApi([membership('f1', 'YPA FARM', role, role)], (url, init) => {
    const hit = extra(url, init);
    if (hit) return hit;
    if (url.pathname === '/api/v1/dashboard/summary') return { body: summary };
    if (url.pathname === '/api/v1/dashboard/charts') return { body: charts };
    if (url.pathname === '/api/v1/reports') return { body: catalog };
    if (url.pathname === '/api/v1/reports/vaccination') return { body: report };
    if (url.pathname === '/api/v1/report-runs') return { body: { count: 0, next: null, results: [] } };
    if (url.pathname === '/api/v1/notifications/unread-count') return { body: { unread: 0, urgent: 0 } };
    if (url.pathname.startsWith('/api/v1/')) return { body: [] };
  });
}

describe('dashboard and reports', () => {
  beforeEach(clearSession);

  it('shows the staff dashboard with herd, health and activity figures', async () => {
    api('farm_manager');
    renderWithProviders(<AppRoutes />, { route: '/dashboard' });
    const total = await screen.findByRole('region', { name: 'Total animals' });
    expect(within(total).getByText('42')).toBeInTheDocument();
    expect(screen.getByText('1 feed item is running low')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: '50% completed' })).toBeInTheDocument();
    expect(screen.getByText(/12 vaccinations · 2 treatments · 4 kids born · 1 deaths/)).toBeInTheDocument();
  });

  it('shows attendants their own tasks only', async () => {
    api('livestock_attendant', (url) =>
      url.pathname === '/api/v1/dashboard/summary'
        ? { body: { ...summary, own: true, herd: undefined, health_status: undefined, health: undefined } }
        : undefined,
    );
    renderWithProviders(<AppRoutes />, { route: '/dashboard' });
    expect(await screen.findByRole('region', { name: 'My tasks today' })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Total animals' })).not.toBeInTheDocument();
  });

  it('previews a report and downloads the PDF', async () => {
    const fetches: string[] = [];
    api('administrator', (url) => {
      if (url.pathname === '/api/v1/reports/vaccination/export') {
        fetches.push(url.searchParams.get('format') ?? '');
        return { body: {} };
      }
    });
    URL.createObjectURL = vi.fn(() => 'blob:x');
    URL.revokeObjectURL = vi.fn();
    renderWithProviders(<AppRoutes />, { route: '/reports' });
    await userEvent.click(await screen.findByRole('link', { name: /Vaccination Report/ }));
    expect(await screen.findByText('Period: 01 Nov 2026 – 30 Nov 2026')).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '03 Nov 2026' })).toBeInTheDocument();
    expect(screen.getByLabelText('From')).toHaveValue('2026-11-01');
    await userEvent.click(screen.getByRole('button', { name: /PDF/ }));
    expect(fetches).toEqual(['pdf']);
  });
});
