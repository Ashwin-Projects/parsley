import type { RunResult } from './api/types';

/** A hint is a final value, not the value at that point in execution. */
export function finalValue(line: string, result: RunResult | null): string | null {
  if (!result || result.error) return null;
  const match =
    /^\s*(?:LET\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(?!=)/.exec(line) ??
    /^\s*PRINT\s+([A-Za-z_][A-Za-z0-9_]*)\s*;/.exec(line);
  if (!match || !Object.hasOwn(result.variables, match[1])) return null;
  return `${match[1]} = ${JSON.stringify(result.variables[match[1]])}`;
}

export function hasPrint(code: string): boolean {
  return /\bPRINT\b/.test(code.replace(/"(?:\\.|[^"\\])*"/g, ''));
}
