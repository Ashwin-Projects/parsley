import { afterEach, describe, expect, it, vi } from 'vitest';
import { createApi, createHttpTransport } from './client';

afterEach(() => vi.unstubAllGlobals());
describe('real HTTP adapter', () => {
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
