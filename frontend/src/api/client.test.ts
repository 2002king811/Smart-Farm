import { mockApi } from '@/test/utils';

import { api, ApiError, setAccessToken, setActiveFarmId } from './client';

describe('api client', () => {
  afterEach(() => {
    setAccessToken(null);
    setActiveFarmId(null);
  });

  it('sends the token and the active farm header', async () => {
    const fetchMock = mockApi(() => ({ body: { ok: true } }));
    setAccessToken('abc');
    setActiveFarmId('farm-1');
    await api('/animals', { query: { search: 'simba', empty: '' } });
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toContain('/api/v1/animals?search=simba');
    expect((init!.headers as Record<string, string>).Authorization).toBe('Bearer abc');
    expect((init!.headers as Record<string, string>)['X-Farm-ID']).toBe('farm-1');
  });

  it('turns the error shape into field errors', async () => {
    mockApi(() => ({ status: 400, body: { errors: { ear_tag: ['Already used on this farm.'] } } }));
    const err = (await api('/animals', { method: 'POST', body: {} }).catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(400);
    expect(err.field('ear_tag')).toEqual(['Already used on this farm.']);
    expect(err.field('name')).toEqual([]);
    expect(err.message).toBe('Already used on this farm.');
  });
});
