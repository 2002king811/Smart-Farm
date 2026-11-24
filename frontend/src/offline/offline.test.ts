import { api, isQueued, setAccessToken, setActiveFarmId } from '@/api/client';

import { discardAll, getSyncState, syncNow } from './sync';

/** fetch that fails like a phone with no signal. */
function goOffline() {
  return vi.spyOn(window, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'));
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

describe('offline', () => {
  beforeEach(async () => {
    setAccessToken('token');
    setActiveFarmId('farm-1');
    await discardAll();
  });

  it('answers from saved data when offline', async () => {
    const tasks = { count: 1, next: null, results: [{ id: 'a1', title: 'Dip the herd', status: 'pending' }] };
    vi.spyOn(window, 'fetch').mockResolvedValueOnce(json(tasks));
    await api('/activities', { query: { page_size: 200 } });
    goOffline();
    expect(await api('/activities', { query: { page_size: 200 } })).toEqual(tasks);
    // A different filter on the same screen still shows the latest saved list.
    expect(await api('/activities', { query: { status: 'overdue' } })).toEqual(tasks);
    await expect(api('/reports')).rejects.toThrow('No connection');
  });

  it('queues a completed task, shows it at once and syncs it later', async () => {
    const tasks = { count: 1, next: null, results: [{ id: 'a2', title: 'Weigh kids', status: 'pending' }] };
    vi.spyOn(window, 'fetch').mockResolvedValueOnce(json(tasks));
    await api('/activities', { query: { mine: 'true' } });

    goOffline();
    const err = await api('/activities/a2/complete', { method: 'POST', body: {} }).catch((e: unknown) => e);
    expect(isQueued(err)).toBe(true);
    expect(getSyncState().pending).toBe(1);
    const saved = await api<typeof tasks>('/activities', { query: { mine: 'true' } });
    expect(saved.results[0]?.status).toBe('completed');

    vi.restoreAllMocks();
    const sent: { url: string; init: RequestInit }[] = [];
    vi.spyOn(window, 'fetch').mockImplementation(async (input, init) => {
      sent.push({ url: String(input), init: init ?? {} });
      return json({ id: 'a2', status: 'completed' });
    });
    await syncNow();
    expect(getSyncState().pending).toBe(0);
    expect(sent).toHaveLength(1);
    expect(sent[0]!.url).toContain('/api/v1/activities/a2/complete');
    const headers = sent[0]!.init.headers as Record<string, string>;
    expect(headers['Idempotency-Key']).toBeTruthy();
    expect(headers['X-Farm-ID']).toBe('farm-1');
    expect(JSON.parse(String(sent[0]!.init.body)).offline_at).toBeTruthy();
  });

  it('keeps a change the server refuses aside with the reason', async () => {
    goOffline();
    await api('/animals', { method: 'POST', body: { animal_id: 'YPA-021' } }).catch(() => undefined);
    vi.restoreAllMocks();
    vi.spyOn(window, 'fetch').mockResolvedValue(
      json({ errors: { animal_id: ['This ID is already used.'] } }, 400),
    );
    await syncNow();
    const state = getSyncState();
    expect(state.pending).toBe(0);
    expect(state.failed[0]?.error).toBe('This ID is already used.');
  });

  it('does not queue uploads or other changes', async () => {
    goOffline();
    const err = await api('/vaccinations', { method: 'POST', body: {} }).catch((e: unknown) => e);
    expect(isQueued(err)).toBe(false);
    expect(getSyncState().pending).toBe(0);
  });
});

describe('sync loop', () => {
  it('can sync again after an empty run', async () => {
    await discardAll();
    await syncNow(); // nothing to send
    setAccessToken('token');
    vi.spyOn(window, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'));
    await api('/activities/a9/start', { method: 'POST', body: {} }).catch(() => undefined);
    vi.restoreAllMocks();
    const fetch = vi.spyOn(window, 'fetch').mockResolvedValue(new Response('{}', { status: 200 }));
    await syncNow();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(getSyncState().pending).toBe(0);
  });
});
