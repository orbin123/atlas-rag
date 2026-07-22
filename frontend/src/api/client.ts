export interface ApiErrorBody {
  code: string;
  message: string;
  details: Record<string, unknown> | unknown[] | null;
  requestId: string;
}

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly body: ApiErrorBody) {
    super(body.message);
    this.name = 'ApiError';
  }
}

const configuredBase = import.meta.env.VITE_API_BASE_URL?.trim();
export const API_BASE_URL = (configuredBase || 'http://127.0.0.1:8000/api/v1').replace(/\/$/, '');

function fallbackError(status: number): ApiErrorBody {
  return { code: `HTTP_${status}`, message: `The Atlas API returned HTTP ${status}.`, details: null, requestId: '' };
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { Accept: 'application/json', ...init.headers },
    });
  } catch (cause) {
    throw new ApiError(0, { code: 'NETWORK_ERROR', message: 'Cannot reach the Atlas API. Confirm the backend is running.', details: cause instanceof Error ? { cause: cause.message } : null, requestId: '' });
  }
  if (!response.ok) {
    let body = fallbackError(response.status);
    try {
      const payload = await response.json() as { error?: ApiErrorBody };
      if (payload.error) body = payload.error;
    } catch { /* retain safe HTTP fallback */ }
    throw new ApiError(response.status, body);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function queryString(values: Record<string, string | number | undefined | null>): string {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  });
  const encoded = params.toString();
  return encoded ? `?${encoded}` : '';
}
