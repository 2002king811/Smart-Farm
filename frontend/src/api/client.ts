/**
 * Thin fetch wrapper for the Smart Farm API. Types come from the generated OpenAPI schema
 * (src/api/schema.d.ts, regenerate with `npm run api:generate`).
 *
 * - The access token lives in memory only. The refresh token is an httpOnly cookie the browser
 *   sends to /api/v1/auth/refresh; a readable `sf_csrf` cookie is echoed in X-CSRF-Token.
 * - On a 401 the client refreshes once and retries; if that fails the session has ended.
 * - Sends X-Farm-ID for the active farm.
 * - Turns the API's {"errors": {field: [messages]}} shape into an ApiError.
 */
import type { components, paths } from './schema';

export type Schemas = components['schemas'];
export type ApiPaths = paths;

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

export type FieldErrors = Record<string, string[]>;

export class ApiError extends Error {
  constructor(
    public status: number,
    public errors: FieldErrors,
  ) {
    super(
      errors.detail?.[0] ??
        errors.non_field_errors?.[0] ??
        // Otherwise the first field message, e.g. {"token": ["This link has expired…"]}.
        Object.values(errors)
          .flat()
          .find((m) => typeof m === 'string') ??
        `Request failed (${status})`,
    );
    this.name = 'ApiError';
  }

  /** Messages for one form field, for showing under the matching input. */
  field(name: string): string[] {
    return this.errors[name] ?? [];
  }
}

export interface Session {
  access: string;
  user: Schemas['Me'];
}

let accessToken: string | null = null;
let activeFarmId: string | null = null;
let onSessionEnded: (() => void) | null = null;
let refreshing: Promise<Session | null> | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}
export function hasAccessToken() {
  return accessToken !== null;
}
export function setActiveFarmId(farmId: string | null) {
  activeFarmId = farmId;
}
export function getActiveFarmId() {
  return activeFarmId;
}
/** Called when a refresh fails mid-session (expired, revoked, deactivated). */
export function setSessionEndedHandler(fn: (() => void) | null) {
  onSessionEnded = fn;
}

function readCookie(name: string): string | null {
  const match = document.cookie.split('; ').find((c) => c.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

export function hasSessionCookie(): boolean {
  return readCookie('sf_csrf') !== null;
}

/** Exchanges the refresh cookie for a new access token. Concurrent callers share one request. */
export function refreshSession(): Promise<Session | null> {
  if (!refreshing) {
    refreshing = (async () => {
      const csrf = readCookie('sf_csrf');
      if (!csrf) return null;
      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
        headers: { Accept: 'application/json', 'X-CSRF-Token': csrf },
      }).catch(() => null);
      if (!res || !res.ok) return null;
      const session = (await res.json()) as Session;
      accessToken = session.access;
      return session;
    })().finally(() => {
      refreshing = null;
    });
  }
  return refreshing;
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
  query?: Record<string, string | number | boolean | undefined | null>;
  /** Skip the automatic refresh-and-retry (used by the auth endpoints themselves). */
  noRefresh?: boolean;
}

export async function api<T>(
  path: string,
  { method = 'GET', body, signal, query, noRefresh = false }: RequestOptions = {},
): Promise<T> {
  const url = new URL(path.startsWith('http') ? path : `${API_BASE}${path}`, window.location.origin);
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v));
  }

  const send = () => {
    const headers: Record<string, string> = { Accept: 'application/json' };
    const isForm = body instanceof FormData;
    if (body !== undefined && !isForm) headers['Content-Type'] = 'application/json';
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
    if (activeFarmId) headers['X-Farm-ID'] = activeFarmId;
    const csrf = readCookie('sf_csrf');
    if (csrf && path.startsWith('/auth/')) headers['X-CSRF-Token'] = csrf;
    return fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
      credentials: 'include',
      signal,
    });
  };

  let res = await send();
  if (res.status === 401 && !noRefresh && hasSessionCookie()) {
    const session = await refreshSession();
    if (session) {
      res = await send();
    } else {
      accessToken = null;
      onSessionEnded?.();
    }
  }

  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    throw new ApiError(res.status, (data && data.errors) || { detail: [res.statusText || 'Request failed'] });
  }
  return data as T;
}
