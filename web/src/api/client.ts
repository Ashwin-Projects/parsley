import type { Api, Transport } from './types';

export function createApi(transport: Transport): Api {
  // The backend owns this contract; UI components only consume the typed client.
  const request = <T>(path: string, body?: Record<string, unknown>) =>
    transport(path, body) as Promise<T>;
  return {
    session: () => request('/api/session', {}),
    compile: (session_id, sentence, mode) =>
      request('/api/compile', { session_id, sentence, mode }),
    answer: (session_id, answer) => request('/api/answer', { session_id, answer }),
    program: (session_id) => request(`/api/program?session_id=${encodeURIComponent(session_id)}`),
    run: (session_id) => request('/api/run', { session_id }),
    undo: (session_id) => request('/api/undo', { session_id }),
    reset: (session_id) => request('/api/reset', { session_id }),
  };
}

export function createHttpTransport(baseUrl = ''): Transport {
  return async (path, body) => {
    const response = await fetch(`${baseUrl.replace(/\/$/, '')}${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok) throw new Error(`API request failed (${response.status}). Please try again.`);
    return response.json() as Promise<unknown>;
  };
}
