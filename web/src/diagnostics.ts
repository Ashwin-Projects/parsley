import type { CompileResult } from './api/types';

export type Diagnostic = CompileResult['diagnostics'][number];
export function isLlmWarning(diagnostic: Diagnostic) {
  return /^W51[0-5]$/.test(diagnostic.code);
}
