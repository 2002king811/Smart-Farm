/**
 * Offline behaviour for the API client.
 *
 * Reading: answers to GET requests the field screens need are saved; when the phone is offline
 * the saved answer is used (the exact one, or the latest for the same screen).
 *
 * Writing: completing or starting a task, task notes, feeding records, weights and new animals
 * are queued when offline, shown at once on this phone, and sent in order when the connection
 * is back. Each carries an Idempotency-Key so a resend is never saved twice; a task change also
 * carries when it was done ("last write wins", noted in the task history).
 */

import {
  cacheAll,
  cacheGet,
  cachePut,
  queueAdd,
  queueAll,
  queueDelete,
  queuePut,
  type QueuedChange,
} from './store';

export const QUEUED_MESSAGE = 'Saved on this phone. It will sync when you are back online.';

/** GET paths worth keeping for offline use. */
const CACHEABLE = [
  /^\/dashboard\//,
  /^\/activities(\/|$|\?)/,
  /^\/activity-categories/,
  /^\/animals(\/|$|\?)/,
  /^\/locations/,
  /^\/animal-groups/,
  /^\/feed-items/,
  /^\/feeding-records/,
  /^\/notifications/,
  /^\/me$/,
  /^\/me\/farms/,
  /^\/farm$/,
  /^\/countries/,
];

/** Changes that may be made offline: [pattern, label]. */
const QUEUEABLE: [RegExp, string][] = [
  [/^\/activities\/[^/]+\/complete$/, 'Task completed'],
  [/^\/activities\/[^/]+\/start$/, 'Task started'],
  [/^\/activities\/[^/]+\/notes$/, 'Task note'],
  [/^\/feeding-records$/, 'Feeding record'],
  [/^\/animals\/[^/]+\/weights$/, 'Weight'],
  [/^\/animals$/, 'New animal'],
];

export function isCacheable(path: string) {
  return CACHEABLE.some((re) => re.test(path));
}

export function queueLabel(method: string, path: string, body: unknown): string | null {
  if (method !== 'POST' || body instanceof FormData) return null;
  const hit = QUEUEABLE.find(([re]) => re.test(path));
  return hit ? hit[1] : null;
}

export function cacheKey(farmId: string | null, url: URL) {
  const params = [...url.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b));
  return `${farmId ?? '-'}|${url.pathname}?${new URLSearchParams(params).toString()}`;
}

export async function saveResponse(farmId: string | null, url: URL, data: unknown) {
  await cachePut({
    key: cacheKey(farmId, url),
    path: `${farmId ?? '-'}|${url.pathname}`,
    data,
    savedAt: Date.now(),
  });
}

/** The saved answer for this request, or the latest one for the same path. */
export async function savedResponse(farmId: string | null, url: URL): Promise<unknown | undefined> {
  const exact = await cacheGet(cacheKey(farmId, url));
  if (exact) return exact.data;
  const path = `${farmId ?? '-'}|${url.pathname}`;
  const all = await cacheAll();
  const same = all.filter((e) => e.path === path).sort((a, b) => b.savedAt - a.savedAt);
  if (same[0]) return same[0].data;
  // A task's or animal's own page: use the row from a saved list.
  const detail = url.pathname.match(/\/(activities|animals)\/([0-9a-f-]{36})$/);
  if (detail) {
    for (const e of all.sort((a, b) => b.savedAt - a.savedAt)) {
      if (!e.path.startsWith(`${farmId ?? '-'}|`)) continue;
      const found = findById(e.data, detail[2]!);
      if (found) return found;
    }
  }
  // Notes and history not saved yet: show them as empty rather than as an error.
  if (/\/activities\/[^/]+\/(notes|history)$/.test(url.pathname)) return [];
  return undefined;
}

function findById(v: unknown, id: string): unknown {
  if (Array.isArray(v)) {
    for (const x of v) {
      const f = findById(x, id);
      if (f) return f;
    }
  } else if (v && typeof v === 'object') {
    const o = v as Record<string, unknown>;
    if (o.id === id && ('status' in o || 'animal_id' in o)) return o;
    for (const x of Object.values(o)) {
      const f = findById(x, id);
      if (f) return f;
    }
  }
  return undefined;
}

// --- Queue -----------------------------------------------------------------------------------------

type Listener = (state: SyncState) => void;
export interface SyncState {
  pending: number;
  failed: QueuedChange[];
  online: boolean;
  syncing: boolean;
}
const listeners = new Set<Listener>();
let state: SyncState = {
  pending: 0,
  failed: [],
  online: typeof navigator === 'undefined' ? true : navigator.onLine,
  syncing: false,
};

function set(patch: Partial<SyncState>) {
  state = { ...state, ...patch };
  listeners.forEach((l) => l(state));
}

export function subscribe(fn: Listener) {
  listeners.add(fn);
  fn(state);
  return () => {
    listeners.delete(fn);
  };
}

export function getSyncState() {
  return state;
}

async function refreshCount() {
  const all = await queueAll();
  set({ pending: all.filter((c) => !c.error).length, failed: all.filter((c) => c.error) });
}

function uuid() {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export async function enqueue(farmId: string | null, path: string, body: unknown, label: string) {
  const isTask = /\/(complete|start)$/.test(path);
  const now = new Date().toISOString();
  const payload = isTask ? { ...(body as object | undefined), offline_at: now } : body;
  await queueAdd({
    farmId,
    method: 'POST',
    path,
    body: payload,
    idempotencyKey: uuid(),
    createdAt: now,
    label,
  });
  if (isTask)
    await patchCachedActivity(path.split('/')[2]!, path.endsWith('complete') ? 'completed' : 'in_progress');
  await refreshCount();
}

/** Show an offline task change straight away in the saved lists. */
async function patchCachedActivity(id: string, status: string) {
  const entries = await cacheAll();
  for (const e of entries) {
    let changed = false;
    const walk = (v: unknown): unknown => {
      if (Array.isArray(v)) return v.map(walk);
      if (v && typeof v === 'object') {
        const o = v as Record<string, unknown>;
        const out: Record<string, unknown> = {};
        for (const [k, x] of Object.entries(o)) out[k] = walk(x);
        if (o.id === id && 'status' in o) {
          out.status = status;
          changed = true;
        }
        return out;
      }
      return v;
    };
    const data = walk(e.data);
    if (changed) await cachePut({ ...e, data });
  }
}

export type Sender = (change: QueuedChange) => Promise<Response>;
let sender: Sender | null = null;
let onSynced: (() => void) | null = null;

export function configureSync(send: Sender, afterSync: () => void) {
  sender = send;
  onSynced = afterSync;
}

let running: Promise<void> | null = null;

/** Sends queued changes in order. Stops at the first network failure; a change the server
 * refuses (e.g. the animal ID was taken meanwhile) is kept aside with the reason. */
export function syncNow(): Promise<void> {
  running ??= (async () => {
    const queue = sender ? (await queueAll()).filter((c) => !c.error) : [];
    if (!sender || !queue.length) {
      running = null;
      return;
    }
    set({ syncing: true });
    let sent = 0;
    try {
      for (const change of queue) {
        let res: Response;
        try {
          res = await sender(change);
        } catch {
          set({ online: false });
          break;
        }
        if (res.ok) {
          await queueDelete(change.id!);
          sent += 1;
        } else if (res.status === 401) {
          break;
        } else {
          const body = (await res.json().catch(() => null)) as { errors?: Record<string, string[]> } | null;
          const first = body?.errors ? Object.values(body.errors)[0]?.[0] : undefined;
          await queuePut({ ...change, error: first ?? `Refused (${res.status})` });
        }
      }
    } finally {
      await refreshCount();
      set({ syncing: false });
      running = null;
      if (sent) onSynced?.();
    }
  })();
  return running;
}

/** On logout: nothing from this person stays on a shared phone. */
export async function discardAll() {
  for (const c of await queueAll()) await queueDelete(c.id!);
  await refreshCount();
}

export async function discardFailed() {
  for (const c of state.failed) await queueDelete(c.id!);
  await refreshCount();
}

export function startSyncLoop() {
  if (typeof window === 'undefined') return () => {};
  const online = () => {
    set({ online: true });
    void syncNow();
  };
  const offline = () => set({ online: false });
  window.addEventListener('online', online);
  window.addEventListener('offline', offline);
  const timer = window.setInterval(() => {
    if (navigator.onLine) void syncNow();
  }, 30_000);
  void refreshCount().then(() => {
    if (navigator.onLine) void syncNow();
  });
  return () => {
    window.removeEventListener('online', online);
    window.removeEventListener('offline', offline);
    window.clearInterval(timer);
  };
}

export function markOnline(on: boolean) {
  if (state.online !== on) set({ online: on });
}
