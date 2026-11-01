import type { CompileResult, Mode, RunResult, Transport } from '../api/types';

type Variables = Record<string, number | string>;
interface Entry {
  english: string;
  minilang: string;
  ref?: string;
  execute: (vars: Variables, output: string[]) => void;
}
interface Pending {
  sentence: string;
  mode: Mode;
  result: CompileResult;
  resolve: (answer: string) => string | undefined;
}
interface Session {
  entries: Entry[];
  pending?: Pending;
}

function run(entries: Entry[]): RunResult {
  const variables: Variables = {};
  const output: string[] = [];
  try {
    entries.forEach((entry) => entry.execute(variables, output));
  } catch (error) {
    return {
      variables,
      output,
      error: error instanceof Error ? error.message : 'Mock runtime error',
    };
  }
  return { variables, output };
}

function compile(
  session: Session,
  sentence: string,
  mode: Mode,
  original = sentence,
): CompileResult {
  const text = sentence.trim().replace(/[.!?]+$/, '');
  const source = mode === 'llm' ? 'llm' : 'rules';
  const variables = run(session.entries).variables;
  const last = session.entries.findLast((entry) => entry.ref)?.ref;
  const resolveName = (name: string) => (name === 'it' || name === 'that' ? (last ?? name) : name);
  const fail = (message: string, suggestion?: string, code = 'E101'): CompileResult => ({
    status: 'rejected',
    diagnostics: [{ code, stage: code === 'E101' ? 'candidates' : 'semantic', message }],
    suggestion,
    source,
    trace: { mock: true, decision: 'rejected', input: original },
  });
  const ask = (question: string, options: string[], resolve: Pending['resolve']): CompileResult => {
    const result: CompileResult = {
      status: 'clarify',
      question: { text: question, options, kind: options.length ? 'alternatives' : 'missing_slot' },
      diagnostics: [],
      source,
      trace: { mock: true, decision: 'clarify', input: original },
    };
    session.pending = { sentence: original, mode, result, resolve };
    return result;
  };
  const accept = (entry: Omit<Entry, 'english'>, understood: string): CompileResult => {
    session.entries.push({ ...entry, english: original });
    session.pending = undefined;
    return {
      status: 'accepted',
      minilang: entry.minilang,
      understood,
      checks: { v1: 'ok', v2: 'ok', v3: 'ok' },
      diagnostics: [],
      source,
      trace: {
        mock: true,
        decision: 'accepted',
        input: original,
        mode,
        verification: 'Simulated fixture results; no compiler verification was performed.',
      },
    };
  };
  let match = /^set (\w+) to (-?\d+(?:\.\d+)?) or (-?\d+(?:\.\d+)?)$/i.exec(text);
  if (match) {
    const [, name, a, b] = match;
    return ask(`What value should ${name} have?`, [a, b], (answer) => {
      const value = [a, b].includes(answer)
        ? answer
        : answer === '1'
          ? a
          : answer === '2'
            ? b
            : answer;
      return [a, b].includes(value) ? `set ${name} to ${value}` : undefined;
    });
  }
  match = /^increase (\w+)$/i.exec(text);
  if (match) {
    const name = resolveName(match[1]);
    return ask(`By how much should ${name} increase?`, [], (answer) =>
      /^-?\d+(\.\d+)?$/.test(answer) ? `increase ${name} by ${answer}` : undefined,
    );
  }
  match =
    /^(?:make a variable called (\w+) and set it to|define (\w+) as|set (\w+) to) (-?\d+(?:\.\d+)?|"[^"\n]*")$/i.exec(
      text,
    );
  if (match) {
    const name = resolveName(match[1] ?? match[2] ?? match[3]);
    const raw = match[4];
    const value = raw.startsWith('"') ? raw.slice(1, -1) : Number(raw);
    if (name === 'it' || name === 'that')
      return fail('There is no recent variable to refer to.', 'set age to 20', 'E201');
    const declared = Object.hasOwn(variables, name);
    if (declared && typeof variables[name] !== typeof value)
      return fail(`Variable ${name} cannot change type.`, undefined, 'E204');
    return accept(
      {
        minilang: `${declared ? '' : 'LET '}${name} = ${raw};`,
        ref: name,
        execute: (vars) => {
          vars[name] = value;
        },
      },
      `${declared ? 'set' : 'create variable'} ${name} ${declared ? 'to' : 'with value'} ${raw}.`,
    );
  }
  match =
    /^(?:(increase|decrease|multiply|divide) (\w+) by|add (-?\d+(?:\.\d+)?) to) (-?\d+(?:\.\d+)?|\w+)$/i.exec(
      text,
    );
  if (match) {
    const name = resolveName(match[3] ? match[4] : match[2]);
    const amount = Number(match[3] ?? match[4]);
    const op =
      ({ increase: '+', decrease: '-', multiply: '*', divide: '/' } as Record<string, string>)[
        match[1]?.toLowerCase()
      ] ?? '+';
    if (typeof variables[name] !== 'number')
      return fail(`Variable ${name} must be a declared number.`, 'set age to 20', 'E201');
    if (!Number.isFinite(amount)) return fail('This mock supports numeric amounts only.');
    if (op === '/' && amount === 0) return fail('Cannot divide by zero.', undefined, 'E206');
    return accept(
      {
        minilang: `${name} = ${name} ${op} ${amount};`,
        ref: name,
        execute: (vars) => {
          const current = Number(vars[name]);
          vars[name] =
            op === '+'
              ? current + amount
              : op === '-'
                ? current - amount
                : op === '*'
                  ? current * amount
                  : current / amount;
        },
      },
      `${op === '+' ? 'increase' : op === '-' ? 'decrease' : op === '*' ? 'multiply' : 'divide'} ${name} by ${amount}.`,
    );
  }
  if (text.toLowerCase() === 'if age is greater than 17 then print adult else print minor') {
    if (typeof variables.age !== 'number')
      return fail('Variable age is not declared.', 'set age to 20', 'E201');
    return accept(
      {
        minilang: 'IF age > 17 THEN { PRINT "adult"; } ELSE { PRINT "minor"; }',
        ref: 'age',
        execute: (vars, output) => {
          output.push(Number(vars.age) > 17 ? 'adult' : 'minor');
        },
      },
      'if age is greater than 17, print "adult"; otherwise print "minor".',
    );
  }
  if (text.toLowerCase() === 'repeat 3 times print hello') {
    return accept(
      {
        minilang: 'REPEAT 3 TIMES { PRINT "hello"; }',
        execute: (_vars, output) => {
          output.push('hello', 'hello', 'hello');
        },
      },
      'repeat 3 times: print "hello".',
    );
  }
  match = /^(?:print|show|display) (.+)$/i.exec(text);
  if (match) {
    const value = resolveName(match[1]);
    const isVariable = Object.hasOwn(variables, value);
    const literal = /^".*"$/.test(value) ? value.slice(1, -1) : value;
    const code = isVariable
      ? value
      : /^-?\d+(\.\d+)?$/.test(value)
        ? value
        : JSON.stringify(literal);
    return accept(
      {
        minilang: `PRINT ${code};`,
        ref: isVariable ? value : undefined,
        execute: (vars, output) => {
          output.push(String(isVariable ? vars[value] : literal));
        },
      },
      `print ${code}.`,
    );
  }
  match = /^store (\d+) in (\w+)$/i.exec(text);
  return fail(
    'This sentence is not supported by the demo. Try a documented example.',
    match ? `set ${match[2]} to ${match[1]}` : 'set age to 20',
  );
}

export function createMockTransport(): Transport {
  const sessions = new Map<string, Session>();
  return async (path, body) => {
    const url = new URL(path, 'http://mock.local');
    if (url.pathname === '/api/session') {
      const session_id = crypto.randomUUID();
      sessions.set(session_id, { entries: [] });
      return { session_id };
    }
    const id = String(body?.session_id ?? url.searchParams.get('session_id') ?? '');
    const session = sessions.get(id);
    if (!session) throw new Error('Session not found. Reset the page to start again.');
    switch (url.pathname) {
      case '/api/compile': {
        if (session.pending) return session.pending.result;
        return compile(session, String(body?.sentence ?? ''), body?.mode as Mode);
      }
      case '/api/answer': {
        const pending = session.pending;
        if (!pending)
          return {
            status: 'error',
            diagnostics: [
              { code: 'E102', stage: 'ambiguity', message: 'There is no pending question.' },
            ],
          };
        const answer = String(body?.answer ?? '').trim();
        const resolved = pending.resolve(answer);
        if (!resolved) return pending.result;
        session.pending = undefined;
        return compile(session, resolved, pending.mode, pending.sentence);
      }
      case '/api/program':
        return {
          minilang: session.entries.map((entry) => entry.minilang).join('\n'),
          statements: session.entries.map(({ english, minilang }) => ({ english, minilang })),
        };
      case '/api/run':
        return run(session.entries);
      case '/api/undo':
        session.entries.pop();
        session.pending = undefined;
        return { ok: true };
      case '/api/reset':
        session.entries = [];
        session.pending = undefined;
        return { ok: true };
      default:
        throw new Error('Unknown mock endpoint');
    }
  };
}
