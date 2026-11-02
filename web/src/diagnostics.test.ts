import { describe, expect, it } from 'vitest';
import { isLlmWarning } from './diagnostics';

const diagnostic = (code: string) => ({ code, stage: 'llm', message: '' });

describe('isLlmWarning', () => {
  it('shows every LLM warning, including a usage limit', () => {
    expect(['W510', 'W513', 'W514', 'W515'].map((code) => isLlmWarning(diagnostic(code)))).toEqual([
      true,
      true,
      true,
      true,
    ]);
  });

  it('leaves other diagnostics alone', () => {
    expect(['W301', 'E101', 'W516'].map((code) => isLlmWarning(diagnostic(code)))).toEqual([
      false,
      false,
      false,
    ]);
  });
});
