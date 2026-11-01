export type Mode = 'rules' | 'llm' | 'hybrid';
export type Check = 'ok' | 'fail' | 'skipped';
export interface CompileResult {
  status: 'accepted' | 'clarify' | 'rejected' | 'error';
  minilang?: string;
  understood?: string;
  checks?: { v1: 'ok' | 'fail'; v2: Check; v3: Check };
  question?: { text: string; options: string[]; kind: string };
  diagnostics: { code: string; stage: string; message: string }[];
  suggestion?: string;
  source?: 'rules' | 'llm';
  trace?: Record<string, unknown>;
}
export interface Program { minilang: string; statements: { english: string; minilang: string }[] }
export interface RunResult { output: string[]; variables: Record<string, unknown>; error?: string }
export type Transport = (path: string, body?: Record<string, unknown>) => Promise<unknown>;
export interface Api {
  session(): Promise<{ session_id: string }>;
  compile(id: string, sentence: string, mode: Mode): Promise<CompileResult>;
  answer(id: string, answer: string): Promise<CompileResult>;
  program(id: string): Promise<Program>;
  run(id: string): Promise<RunResult>;
  undo(id: string): Promise<{ ok: boolean }>;
  reset(id: string): Promise<{ ok: boolean }>;
}
