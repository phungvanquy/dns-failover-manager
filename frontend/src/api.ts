const BASE = '/api';

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `Error ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch { /* ignore parse errors */ }
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  async get<T>(path: string): Promise<T> {
    const res = await fetch(`${BASE}${path}`);
    return handleResponse<T>(res);
  },
  async post<T>(path: string, body?: unknown): Promise<T> {
    const res = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    return handleResponse<T>(res);
  },
  async put<T>(path: string, body: unknown): Promise<T> {
    const res = await fetch(`${BASE}${path}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return handleResponse<T>(res);
  },
  async del(path: string): Promise<void> {
    const res = await fetch(`${BASE}${path}`, { method: 'DELETE' });
    if (!res.ok) {
      let detail = `Error ${res.status}`;
      try {
        const body = await res.json();
        if (body.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
      } catch { /* ignore */ }
      throw new Error(detail);
    }
  },
};
