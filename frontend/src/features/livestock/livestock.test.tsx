import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AppRoutes } from '@/routes/AppRoutes';
import { clearSession, membership, renderWithProviders, signedInApi } from '@/test/utils';

const simba = {
  id: 'a1',
  animal_id: 'YPA-001',
  ear_tag: 'KE1001',
  name: 'Simba',
  species: 'goat',
  breed: 'Galla',
  sex: 'male',
  date_of_birth: '2024-05-01',
  dob_estimated: false,
  age_months: 30,
  is_kid: false,
  health_status: 'under_treatment',
  breeding_status: 'breeding_male',
  location: { id: 'l1', name: 'Night Pen' },
  group: null,
  latest_weight_kg: '42.50',
  latest_weight_date: '2026-11-01',
  thumbnail: null,
  is_active: true,
  exit_reason: '',
};
const detail = {
  ...simba,
  acquisition_date: null,
  acquisition_source: 'born_on_farm',
  acquisition_details: '',
  dam: null,
  sire: null,
  sire_details: '',
  colour_markings: '',
  current_condition: 'Limping on left foreleg',
  previous_history: '',
  remarks: '',
  exit_date: null,
  exit_notes: '',
  offspring_count: 3,
  created_at: '2026-01-10T08:00:00Z',
  created_by_name: 'Grace Wanjiru',
  updated_at: '2026-01-10T08:00:00Z',
};
const page = (results: unknown[]) => ({ count: results.length, next: null, previous: null, results });
const summary = { total: 1, males: 1, females: 0, kids: 0, needing_attention: 1, pregnant: 0, inactive: 0 };

function farmApi(
  role: string,
  extra: (url: URL, init?: RequestInit) => { status?: number; body?: unknown } | undefined = () => undefined,
) {
  return signedInApi([membership('f1', 'YPA FARM', role, role)], (url, init) => {
    const hit = extra(url, init);
    if (hit) return hit;
    if (url.pathname === '/api/v1/animals/summary') return { body: summary };
    if (url.pathname === '/api/v1/animals/next-id') return { body: { animal_id: 'YPA-002' } };
    if (url.pathname === '/api/v1/animals' && (!init?.method || init.method === 'GET'))
      return { body: page(url.searchParams.get('sex') === 'female' ? [] : [simba]) };
    if (url.pathname === '/api/v1/animals/a1') return { body: detail };
    if (url.pathname === '/api/v1/animals/a1/photos') return { body: [] };
    if (url.pathname === '/api/v1/animals/a1/weights') return { body: [] };
    if (url.pathname === '/api/v1/locations')
      return {
        body: [
          { id: 'l1', name: 'Night Pen', type: 'pen', capacity: null, description: '', animal_count: 1 },
        ],
      };
    if (url.pathname === '/api/v1/animal-groups') return { body: [] };
  });
}

describe('livestock register', () => {
  beforeEach(clearSession);

  it('lists animals with status, age and weight and sends filters to the API', async () => {
    const fetchMock = farmApi('farm_manager');
    renderWithProviders(<AppRoutes />, { route: '/livestock' });
    const table = await screen.findByRole('table');
    expect(within(table).getByRole('link', { name: 'YPA-001 Simba' })).toBeInTheDocument();
    expect(within(table).getByText('Under Treatment')).toBeInTheDocument();
    expect(within(table).getByText('42.5 kg')).toBeInTheDocument();
    expect(await screen.findByText('Needing attention')).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText('Sex'), 'female');
    expect(await screen.findByText('No animals match')).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes('sex=female'))).toBe(true);
    expect(screen.getByRole('link', { name: /Register animal/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Excel/ })).toBeInTheDocument();
  });

  it('hides export and setup from attendants but lets them register', async () => {
    farmApi('livestock_attendant');
    renderWithProviders(<AppRoutes />, { route: '/livestock' });
    await screen.findByRole('table');
    expect(screen.getByRole('link', { name: /Register animal/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Excel/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Locations/ })).not.toBeInTheDocument();
  });

  it('registers an animal with an estimated age and shows server errors under fields', async () => {
    let posted: Record<string, unknown> = {};
    farmApi('farm_manager', (url, init) => {
      if (url.pathname === '/api/v1/animals' && init?.method === 'POST') {
        posted = JSON.parse(String(init.body));
        if (posted.ear_tag === 'KE1001')
          return {
            status: 400,
            body: { errors: { ear_tag: ['This ear tag is already used on this farm.'] } },
          };
        return { status: 201, body: { ...detail, id: 'a2', animal_id: 'YPA-002' } };
      }
      if (url.pathname === '/api/v1/animals/a2')
        return { body: { ...detail, id: 'a2', animal_id: 'YPA-002' } };
      if (url.pathname.startsWith('/api/v1/animals/a2/')) return { body: [] };
    });
    renderWithProviders(<AppRoutes />, { route: '/livestock/new' });
    expect(await screen.findByLabelText('Animal ID *')).toHaveValue('YPA-002');
    await userEvent.type(screen.getByLabelText('Ear tag'), 'KE1001');
    await userEvent.click(screen.getByLabelText('Female'));
    await userEvent.click(screen.getByLabelText('Estimate the age'));
    await userEvent.type(await screen.findByLabelText('Estimated age (months) *'), '18');
    await userEvent.selectOptions(screen.getByLabelText('Location'), 'l1');
    await userEvent.click(screen.getByRole('button', { name: 'Register animal' }));
    expect(await screen.findByText('This ear tag is already used on this farm.')).toBeInTheDocument();
    expect(posted).toMatchObject({
      animal_id: 'YPA-002',
      sex: 'female',
      estimated_age_months: 18,
      location: 'l1',
      dam: null,
    });
    expect(posted).not.toHaveProperty('date_of_birth');

    await userEvent.clear(screen.getByLabelText('Ear tag'));
    await userEvent.type(screen.getByLabelText('Ear tag'), 'KE2002');
    await userEvent.click(screen.getByRole('button', { name: 'Register animal' }));
    expect(await screen.findByText('YPA-002 is registered.')).toBeInTheDocument();
  });
});

describe('animal profile', () => {
  beforeEach(clearSession);

  it('shows the header, tabs and records a weight', async () => {
    let weighed: Record<string, unknown> | null = null;
    farmApi('livestock_attendant', (url, init) => {
      if (url.pathname === '/api/v1/animals/a1/weights' && init?.method === 'POST') {
        weighed = JSON.parse(String(init.body));
        return { status: 201, body: {} };
      }
    });
    renderWithProviders(<AppRoutes />, { route: '/livestock/a1' });
    expect(await screen.findByRole('heading', { name: 'YPA-001 · Simba' })).toBeInTheDocument();
    expect(screen.getAllByRole('tab')).toHaveLength(8);
    expect(screen.getByText('Limping on left foreleg')).toBeInTheDocument();
    // Attendants weigh but don't edit.
    expect(screen.queryByRole('link', { name: 'Edit' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Record weight/ }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText('Weight (kg)'), '43.2');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save weight' }));
    await waitFor(() => expect(weighed).toMatchObject({ weight_kg: '43.20' }));
    expect(await screen.findByText('Weight saved for YPA-001.')).toBeInTheDocument();
  });

  it('says plainly when an animal is not on this farm', async () => {
    farmApi('administrator', (url) =>
      url.pathname === '/api/v1/animals/zz'
        ? { status: 404, body: { errors: { detail: ['Not found.'] } } }
        : undefined,
    );
    renderWithProviders(<AppRoutes />, { route: '/livestock/zz' });
    expect(await screen.findByText('Animal not found')).toBeInTheDocument();
  });
});
