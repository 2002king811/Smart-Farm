import { screen } from '@testing-library/react';

import { setLanguage } from '@/i18n';
import { AppRoutes } from '@/routes/AppRoutes';
import { clearSession, ME, membership, renderWithProviders, signedInApi } from '@/test/utils';

describe('Kiswahili', () => {
  beforeEach(clearSession);
  afterEach(() => setLanguage('en'));

  it("shows an attendant's tasks in Kiswahili when that is their language", async () => {
    signedInApi(
      [membership('f1', 'YPA FARM', 'livestock_attendant', 'Livestock Attendant')],
      (url) => {
        if (url.pathname === '/api/v1/activities')
          return {
            body: {
              count: 1,
              next: null,
              results: [
                {
                  id: 'a1',
                  title: 'Dip the herd',
                  date: '2026-11-26',
                  all_day: true,
                  status: 'pending',
                  priority: 'high',
                  category: null,
                  assigned_to: { id: 'u1', name: 'Grace Wanjiru' },
                  animals: [],
                },
              ],
            },
          };
        if (url.pathname.startsWith('/api/v1/')) return { body: [] };
      },
      { ...ME, language: 'sw' },
    );
    renderWithProviders(<AppRoutes />, { route: '/activities' });
    expect(await screen.findByRole('heading', { name: 'Kazi zangu' })).toBeInTheDocument();
    expect(await screen.findByText('Dip the herd')).toBeInTheDocument();
    expect(screen.getByText('Inasubiri')).toBeInTheDocument(); // Pending
    expect(screen.getByRole('button', { name: 'Kamilisha' })).toBeInTheDocument(); // Complete
    expect(screen.getByRole('link', { name: 'Kazi' })).toBeInTheDocument(); // bottom nav: Tasks
  });
});
