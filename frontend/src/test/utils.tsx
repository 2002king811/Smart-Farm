import { QueryClient } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';

import { Providers } from '@/App';
import { setAccessToken, setActiveFarmId } from '@/api/client';

export function renderWithProviders(ui: ReactElement, { route = '/' } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Providers client={client}>{ui}</Providers>
    </MemoryRouter>,
  );
}

type Handler = (url: URL, init?: RequestInit) => { status?: number; body?: unknown } | undefined;

/** Stubs window.fetch with a router of URL path → JSON response. */
export function mockApi(handler: Handler) {
  return vi.spyOn(window, 'fetch').mockImplementation(async (input, init) => {
    const url = new URL(
      typeof input === 'string' ? input : input instanceof URL ? input.href : input.url,
      'http://localhost',
    );
    const res = handler(url, init) ?? { status: 404, body: { errors: { detail: ['Not found.'] } } };
    return new Response(res.status === 204 ? null : JSON.stringify(res.body ?? null), {
      status: res.status ?? 200,
      headers: { 'Content-Type': 'application/json' },
    });
  });
}

export const ME = {
  id: 'u1',
  username: 'grace',
  first_name: 'Grace',
  last_name: 'Wanjiru',
  full_name: 'Grace Wanjiru',
  email: 'grace@example.com',
  phone: '+254712345678',
  photo: null,
  language: 'en',
  email_verified: true,
  phone_verified: true,
  must_change_password: false,
  alert_channels: ['in_app'],
  last_login: null,
};

export function membership(id: string, name: string, role: string, role_label: string) {
  return {
    id: `m-${id}`,
    farm: { id, name, slug: id, status: 'active' },
    role,
    role_label,
    status: 'active',
    job_title: '',
    joined_at: '2026-01-01T00:00:00Z',
    permissions: {},
  };
}

/** Pretend the browser holds a session cookie, so the app resumes via /auth/refresh. */
export function withSessionCookie() {
  document.cookie = 'sf_csrf=test-csrf; path=/';
}

export function clearSession() {
  document.cookie = 'sf_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
  setAccessToken(null);
  setActiveFarmId(null);
  window.localStorage.clear();
}

/** Signed-in API: refresh works, /me/farms returns the given memberships, plus extra routes. */
export function signedInApi(farms: unknown[], extra: Handler = () => undefined, me: object = ME) {
  withSessionCookie();
  return mockApi((url, init) => {
    if (url.pathname === '/api/v1/auth/refresh') return { body: { access: 'access-1', user: me } };
    if (url.pathname === '/api/v1/me/farms') return { body: farms };
    if (url.pathname === '/api/v1/auth/logout') return { status: 204 };
    return extra(url, init);
  });
}
