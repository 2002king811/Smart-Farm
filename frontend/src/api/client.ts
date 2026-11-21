/**
 * Thin fetch wrapper for the Smart Farm API. Types come from the generated OpenAPI schema
 * (src/api/schema.d.ts, regenerate with `npm run api:generate`).
 *
 * - Sends the access token (kept in memory only; the refresh token is an httpOnly cookie).
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
    super(errors.detail?.[0] ?? errors.non_field_errors?.[0] ?? `Request failed (${status})`);
    this.name = 'ApiError';
  }

  /** Messages for one form field, for showing under the matching input. */
  field(name: string): string[] {
    return this.errors[name] ?? [];
  }
}

let accessToken: string | null = null;
let activeFarmId: string | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}
export function setActiveFarmId(farmId: string | null) {
  activeFarmId = farmId;
}
export function getActiveFarmId() {
  return activeFarmId;
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
  query?: Record<string, string | number | boolean | undefined | null>;
}

export async function api<T>(
  path: string,
  { method = 'GET', body, signal, query }: RequestOptions = {},
): Promise<T> {
  const url = new URL(path.startsWith('http') ? path : `${API_BASE}${path}`, window.location.origin);
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v));
  }

  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  if (activeFarmId) headers['X-Farm-ID'] = activeFarmId;

  const res = await fetch(url, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: 'include',
    signal,
  });

  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    throw new ApiError(res.status, (data && data.errors) || { detail: [res.statusText || 'Request failed'] });
  }
  return data as T;
}
