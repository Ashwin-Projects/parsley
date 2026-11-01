import type { Api, Transport } from './types';

export class RequestError extends Error {
  constructor(
    message: string,
    readonly outcomeUncertain = false,
  ) {
    super(message);
    this.name = 'RequestError';
  }
}

export function createApi(transport: Transport): Api {
  // The backend owns this contract; UI components only consume the typed client.
  const request = <T>(path: string, body?: Record<string, unknown>) =>
    transport(path, body) as Promise<T>;
  return {
    health: () => request('/api/health'),
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

export function createHttpTransport(baseUrl = '', timeoutMs = 30_000): Transport {
  return async (path, body) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(`${baseUrl.replace(/\/$/, '')}${path}`, {
        method: body === undefined ? 'GET' : 'POST',
        headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
      if (response.status === 429) {
        const retry = response.headers.get('Retry-After');
        const seconds =
          retry && /^\d+$/.test(retry)
            ? Number(retry)
            : retry
              ? Math.ceil((Date.parse(retry) - Date.now()) / 1000)
              : NaN;
        throw new Error(
          Number.isFinite(seconds) && seconds > 0
            ? `Rate limited. Please retry in ${seconds} seconds.`
            : 'Rate limited. Please wait and retry.',
        );
      }
      if ([502, 503, 504].includes(response.status))
        throw new RequestError(
          `Backend unavailable (${response.status}). Check that the API is running, then retry.`,
          true,
        );
      if (!response.ok)
        throw new RequestError(
          `API request failed (${response.status}). Please try again.`,
          response.status >= 500,
        );
      return (await response.json()) as unknown;
    } catch (cause) {
      if (
        controller.signal.aborted ||
        (cause instanceof DOMException && ['AbortError', 'TimeoutError'].includes(cause.name))
      ) {
        throw new RequestError(
          'Request timed out. The request was not retried; check the program before resending.',
          true,
        );
      }
      if (cause instanceof TypeError)
        throw new RequestError(
          'Backend unavailable. Check that the API is running, then retry.',
          true,
        );
      throw cause;
    } finally {
      clearTimeout(timer);
    }
  };
}
