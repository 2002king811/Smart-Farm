import { QueryClient } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';

import { Providers } from '@/App';

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
    return new Response(JSON.stringify(res.body ?? null), {
      status: res.status ?? 200,
      headers: { 'Content-Type': 'application/json' },
    });
  });
}
