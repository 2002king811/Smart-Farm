/**
 * Offline storage in IndexedDB (falls back to memory where IndexedDB is missing, e.g. tests).
 * - "cache": the last answer for each GET the app may need offline.
 * - "queue": changes made offline, waiting to be sent in order.
 */

export interface CacheEntry {
  key: string;
  path: string;
  data: unknown;
  savedAt: number;
}

export interface QueuedChange {
  id?: number;
  farmId: string | null;
  method: 'POST' | 'PATCH';
  path: string;
  body: unknown;
  idempotencyKey: string;
  createdAt: string;
  label: string;
  error?: string;
}

const DB_NAME = 'smartfarm-offline';
const VERSION = 1;
let dbPromise: Promise<IDBDatabase | null> | null = null;

function openDb(): Promise<IDBDatabase | null> {
  if (typeof indexedDB === 'undefined') return Promise.resolve(null);
  dbPromise ??= new Promise((resolve) => {
    const req = indexedDB.open(DB_NAME, VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains('cache')) db.createObjectStore('cache', { keyPath: 'key' });
      if (!db.objectStoreNames.contains('queue'))
        db.createObjectStore('queue', { keyPath: 'id', autoIncrement: true });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => resolve(null);
  });
  return dbPromise;
}

// Memory fallback.
const memCache = new Map<string, CacheEntry>();
const memQueue = new Map<number, QueuedChange>();
let memId = 1;

function run<T>(
  store: 'cache' | 'queue',
  mode: IDBTransactionMode,
  fn: (s: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  return openDb().then(
    (db) =>
      new Promise<T>((resolve, reject) => {
        if (!db) return reject(new Error('no-idb'));
        const tx = db.transaction(store, mode);
        const req = fn(tx.objectStore(store));
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      }),
  );
}

export async function cachePut(entry: CacheEntry): Promise<void> {
  try {
    await run('cache', 'readwrite', (s) => s.put(entry));
  } catch {
    memCache.set(entry.key, entry);
  }
}

export async function cacheGet(key: string): Promise<CacheEntry | undefined> {
  try {
    return (await run<CacheEntry | undefined>('cache', 'readonly', (s) => s.get(key))) ?? undefined;
  } catch {
    return memCache.get(key);
  }
}

export async function cacheAll(): Promise<CacheEntry[]> {
  try {
    return await run<CacheEntry[]>('cache', 'readonly', (s) => s.getAll());
  } catch {
    return [...memCache.values()];
  }
}

export async function cacheClear(): Promise<void> {
  try {
    await run('cache', 'readwrite', (s) => s.clear());
  } catch {
    memCache.clear();
  }
}

export async function queueAdd(change: QueuedChange): Promise<number> {
  try {
    return Number(await run<IDBValidKey>('queue', 'readwrite', (s) => s.add(change)));
  } catch {
    const id = memId++;
    memQueue.set(id, { ...change, id });
    return id;
  }
}

export async function queueAll(): Promise<QueuedChange[]> {
  try {
    const all = await run<QueuedChange[]>('queue', 'readonly', (s) => s.getAll());
    return all.sort((a, b) => (a.id ?? 0) - (b.id ?? 0));
  } catch {
    return [...memQueue.values()];
  }
}

export async function queuePut(change: QueuedChange): Promise<void> {
  try {
    await run('queue', 'readwrite', (s) => s.put(change));
  } catch {
    if (change.id !== undefined) memQueue.set(change.id, change);
  }
}

export async function queueDelete(id: number): Promise<void> {
  try {
    await run('queue', 'readwrite', (s) => s.delete(id));
  } catch {
    memQueue.delete(id);
  }
}
