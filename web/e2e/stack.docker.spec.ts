import { expect, test } from '@playwright/test';

test('nginx serves the site and protects content types', async ({ request }) => {
  const response = await request.get('/');
  expect(response.status()).toBe(200);
  expect(await response.text()).toContain('Parsley');
  expect(response.headers()['x-content-type-options']).toBe('nosniff');
});

test('real API compiles, clarifies and runs through nginx', async ({ request }) => {
  const health = await request.get('/api/health');
  expect(health.ok()).toBe(true);
  expect(await health.json()).toMatchObject({ version: expect.any(String) });
  const healthText = await health.text();
  expect(healthText).not.toMatch(/api_key|base_url/i);
  const created = await request.post('/api/session', { data: {} });
  const { session_id } = await created.json();
  const compile = async (sentence: string) => {
    const result = await request.post('/api/compile', {
      data: { session_id, sentence, mode: 'rules' },
    });
    expect(result.ok()).toBe(true);
    return result.json();
  };
  expect(await compile('set score to 10')).toMatchObject({
    status: 'accepted',
    minilang: 'LET score = 10;',
    checks: { v1: 'ok', v2: 'ok', v3: 'ok' },
  });
  expect(await compile('increase score')).toMatchObject({ status: 'clarify' });
  const answered = await request.post('/api/answer', { data: { session_id, answer: '5' } });
  expect(await answered.json()).toMatchObject({ status: 'accepted' });
  await compile('print score');
  const program = await request.get('/api/program', { params: { session_id } });
  expect((await program.json()).minilang).toContain('score = score + 5;');
  const run = await request.post('/api/run', { data: { session_id } });
  expect(await run.json()).toMatchObject({ output: ['15'], variables: { score: 15 } });
});
