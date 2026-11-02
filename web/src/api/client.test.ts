import { afterEach, describe, expect, it, vi } from 'vitest';
import { createApi, createHttpTransport } from './client';

afterEach(() => vi.unstubAllGlobals());
describe('real HTTP adapter', () => {
  it('reports a retryable rate limit and never exposes the response body', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response('private provider error', { status: 429, headers: { 'Retry-After': '12' } }),
        ),
    );
    await expect(createApi(createHttpTransport()).session()).rejects.toThrow(
      'Rate limited. Please retry in 12 seconds.',
    );
  });

  it('explains backend-down and timeout failures', async () => {
    const fetcher = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));
    vi.stubGlobal('fetch', fetcher);
    await expect(createApi(createHttpTransport()).session()).rejects.toThrow('Backend unavailable');
    fetcher.mockRejectedValueOnce(new DOMException('aborted', 'TimeoutError'));
    await expect(createApi(createHttpTransport()).session()).rejects.toThrow('Request timed out');
  });

  it('aborts a stalled request at its configured deadline', async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(
        (_url, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            init.signal?.addEventListener('abort', () =>
              reject(new DOMException('aborted', 'AbortError')),
            );
          }),
      ),
    );
    try {
      const request = createApi(createHttpTransport('', 50)).session();
      const assertion = expect(request).rejects.toThrow('Request timed out');
      await vi.advanceTimersByTimeAsync(50);
      await assertion;
    } finally {
      vi.useRealTimers();
    }
  });
  it('posts the exact compile payload and uses a GET with an encoded session query', async () => {
    const fetcher = vi
      .fn()
      .mockImplementation(
        async () => new Response(JSON.stringify({ status: 'accepted', diagnostics: [] })),
      );
    vi.stubGlobal('fetch', fetcher);
    const api = createApi(createHttpTransport('http://localhost:8000/'));
    await api.compile('a b&c', 'print age', 'hybrid');
    expect(fetcher).toHaveBeenLastCalledWith(
      'http://localhost:8000/api/compile',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ session_id: 'a b&c', sentence: 'print age', mode: 'hybrid' }),
      }),
    );
    await api.program('a b&c');
    expect(fetcher).toHaveBeenLastCalledWith(
      'http://localhost:8000/api/program?session_id=a%20b%26c',
      expect.objectContaining({ method: 'GET', body: undefined }),
    );
  });
  it('surfaces HTTP and network errors instead of returning accepted results', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('', { status: 503 }));
    vi.stubGlobal('fetch', fetcher);
    await expect(createApi(createHttpTransport()).session()).rejects.toThrow('503');
    fetcher.mockRejectedValueOnce(new Error('Network unavailable'));
    await expect(createApi(createHttpTransport()).session()).rejects.toThrow('Network unavailable');
  });
});
