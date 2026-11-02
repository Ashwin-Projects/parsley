import { describe, expect, it } from 'vitest';
import { createMockTransport } from './api';
import { createApi } from '../api/client';

describe('mock contract', () => {
  it('reports health and requires explicit derived-value confirmation', async () => {
    const transport = createMockTransport();
    expect(await transport('/api/health')).toMatchObject({
      version: expect.any(String),
      llm_configured: true,
    });
    const api = createApi(transport);
    const id = (await api.session()).session_id;
    const reading = await api.compile(id, 'set x to 10', 'llm');
    expect(reading.diagnostics).toEqual(
      expect.arrayContaining([expect.objectContaining({ code: 'W513' })]),
    );
    const result = await api.compile(id, 'double x', 'llm');
    expect(result.question).toEqual({
      kind: 'derived_value',
      text: 'Did you mean: multiply x by 2?',
      options: ['Yes', 'No'],
    });
    expect((await api.answer(id, 'no')).status).toBe('rejected');
    expect((await api.program(id)).statements).toHaveLength(1);
    await api.compile(id, 'double x', 'llm');
    await api.answer(id, 'yes');
    expect((await api.run(id)).variables).toEqual({ x: 20 });
  });
  async function session() {
    const api = createApi(createMockTransport());
    return { api, id: (await api.session()).session_id };
  }

  it('accumulates statements, resolves it, runs, undoes and resets', async () => {
    const { api, id } = await session();
    expect(
      (await api.compile(id, 'make a variable called age and set it to 20', 'rules')).minilang,
    ).toBe('LET age = 20;');
    await api.compile(id, 'add 5 to it', 'hybrid');
    await api.compile(id, 'print age', 'llm');
    expect(await api.run(id)).toEqual({ output: ['25'], variables: { age: 25 } });
    expect((await api.program(id)).statements).toHaveLength(3);
    await api.undo(id);
    expect((await api.run(id)).output).toEqual([]);
    await api.reset(id);
    expect((await api.program(id)).minilang).toBe('');
  });

  it('clarifies alternatives and missing values without prematurely committing', async () => {
    const { api, id } = await session();
    expect((await api.compile(id, 'set age to 10 or 20', 'rules')).question?.options).toEqual([
      '10',
      '20',
    ]);
    expect((await api.program(id)).statements).toHaveLength(0);
    expect((await api.answer(id, 'invalid')).status).toBe('clarify');
    expect((await api.answer(id, '20')).minilang).toBe('LET age = 20;');
    expect((await api.compile(id, 'increase age', 'rules')).question?.options).toEqual([]);
    expect((await api.answer(id, '2')).minilang).toBe('age = age + 2;');
    expect((await api.run(id)).variables).toEqual({ age: 22 });
  });

  it('isolates sessions and rejects unsupported input with a rewrite', async () => {
    const transport = createMockTransport();
    const api = createApi(transport);
    const a = (await api.session()).session_id;
    const b = (await api.session()).session_id;
    const response = await api.compile(a, 'store 50 in bonus', 'rules');
    expect(response.status).toBe('rejected');
    expect(response.suggestion).toBe('set bonus to 50');
    await api.compile(a, 'set bonus to 50', 'rules');
    expect((await api.program(b)).statements).toHaveLength(0);
    await expect(api.run('missing')).rejects.toThrow('Session not found');
  });

  it('treats an option button value as the value before considering option numbers', async () => {
    const { api, id } = await session();
    await api.compile(id, 'set age to 2 or 3', 'rules');
    expect((await api.answer(id, '2')).minilang).toBe('LET age = 2;');
  });

  it('executes all sidebar examples in order and exposes simulated LLM provenance', async () => {
    const { api, id } = await session();
    const { examples } = await import('../examples');
    for (const example of examples) {
      expect((await api.compile(id, example.sentence, 'rules')).status).toBe('accepted');
    }
    expect(await api.run(id)).toEqual({
      output: ['35', 'Hello', 'adult', 'hello', 'hello', 'hello'],
      variables: { age: 35, total: 0 },
    });
    const result = await api.compile(id, 'print age', 'llm');
    expect(result.source).toBe('llm');
    expect(result.trace?.mock).toBe(true);
  });

  it('consumes a resolved question even when semantic checks reject the answer', async () => {
    const { api, id } = await session();
    await api.compile(id, 'increase age', 'rules');
    expect((await api.answer(id, '3')).status).toBe('rejected');
    expect((await api.compile(id, 'set age to 20', 'rules')).status).toBe('accepted');
  });
});
