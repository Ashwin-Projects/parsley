import { useCallback, useEffect, useRef, useState } from 'react';
import type { Api, CompileResult, Mode, Program, RunResult } from './api/types';
import { Conversation, type Message } from './components/Conversation';
import { ProgramPanel } from './components/ProgramPanel';
import { HelpDialog } from './components/HelpDialog';
import { Icon } from './components/Icon';
import { examples } from './examples';
import { BackendStatus } from './components/BackendStatus';
import { WarningToast } from './components/WarningToast';
import { isLlmWarning, type Diagnostic } from './diagnostics';

const emptyProgram: Program = { minilang: '', statements: [] };
export default function App({ api, mock = true }: { api: Api; mock?: boolean }) {
  const [sessionId, setSessionId] = useState('');
  const [program, setProgram] = useState<Program>(emptyProgram);
  const [messages, setMessages] = useState<Message[]>([]);
  const [mode, setMode] = useState<Mode>('rules');
  const [sentence, setSentence] = useState('');
  const [lastSentence, setLastSentence] = useState('');
  const [busy, setBusy] = useState(false);
  const [syncRequired, setSyncRequired] = useState(false);
  const unavailable = busy || syncRequired;
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [warnings, setWarnings] = useState<Diagnostic[]>([]);
  const dismissWarnings = useCallback(() => setWarnings([]), []);
  const [healthRevision, setHealthRevision] = useState(0);
  const sentenceLength = [...sentence].length;
  const overlong = sentenceLength > 500;
  const [linked, setLinked] = useState<number | null>(null);
  const [output, setOutput] = useState<RunResult | null>(null);
  const [help, setHelp] = useState(false);
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem('parsley-theme') ?? 'light';
    } catch {
      return 'light';
    }
  });
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const conversationEnd = useRef<HTMLDivElement>(null);
  const lock = useRef(false);
  const messageId = useRef(0);
  const pending = messages.some((message) => message.result.status === 'clarify');

  useEffect(() => {
    let active = true;
    api
      .session()
      .then((result) => {
        if (active) setSessionId(result.session_id);
      })
      .catch((cause) => {
        if (active)
          setError(cause instanceof Error ? cause.message : 'Backend unavailable. Please retry.');
      });
    return () => {
      active = false;
    };
  }, [api]);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem('parsley-theme', theme);
    } catch {
      /* Theme works even without storage. */
    }
  }, [theme]);
  useEffect(() => {
    conversationEnd.current?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' });
  }, [messages]);

  async function action(work: () => Promise<void>) {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await work();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Something went wrong. Please try again.');
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  function insert(text: string) {
    setSentence(text);
    inputRef.current?.focus();
  }
  function rememberResult(result: CompileResult, english: string, id?: number, answer?: string) {
    setWarnings(result.diagnostics.filter(isLlmWarning));
    setHealthRevision((revision) => revision + 1);
    const message: Message = {
      id: id ?? messageId.current++,
      english,
      result,
      answer,
      statementIndex: result.status === 'accepted' ? program.statements.length : undefined,
    };
    setMessages((current) =>
      id === undefined
        ? [...current, message]
        : current.map((item) => (item.id === id ? message : item)),
    );
    setOutput(null);
  }
  async function refreshProgram() {
    const updated = await api.program(sessionId);
    setProgram(updated);
    // A mutation may have succeeded even when the following refresh failed.
    // Reconcile only after the backend supplies the authoritative program.
    setMessages((current) =>
      current.filter(
        (message) =>
          message.statementIndex === undefined ||
          message.statementIndex < updated.statements.length,
      ),
    );
    setSyncRequired(false);
    return updated;
  }
  async function send() {
    if (overlong || !sentence.trim() || !sessionId || pending || syncRequired || lock.current)
      return;
    const english = sentence.trim();
    await action(async () => {
      const result = await api.compile(sessionId, english, mode);
      rememberResult(result, english);
      setSyncRequired(true);
      setSentence('');
      setLastSentence(english);
      await refreshProgram();
    });
    inputRef.current?.focus();
  }
  async function answer(id: number, value: string) {
    const original = messages.find((message) => message.id === id);
    if (!original || syncRequired) return;
    await action(async () => {
      const result = await api.answer(sessionId, value);
      rememberResult(result, original.english, id, value);
      setSyncRequired(true);
      await refreshProgram();
      if (result.status === 'clarify')
        setNotice('That answer did not resolve the question. Please try again.');
    });
    inputRef.current?.focus();
  }
  async function undo() {
    if (syncRequired) return;
    await action(async () => {
      if (!(await api.undo(sessionId)).ok)
        throw new Error('Undo was not completed. Please try again.');
      setSyncRequired(true);
      setMessages((current) => current.filter((message) => message.result.status !== 'clarify'));
      setLinked(null);
      setOutput(null);
      await refreshProgram();
      setLinked(null);
      setOutput(null);
      setNotice('Last statement removed.');
    });
  }
  async function reset() {
    await action(async () => {
      if (sessionId) {
        if (!(await api.reset(sessionId)).ok)
          throw new Error('Reset was not completed. Please try again.');
      } else setSessionId((await api.session()).session_id);
      setProgram(emptyProgram);
      setMessages([]);
      setWarnings([]);
      setOutput(null);
      setSentence('');
      setLastSentence('');
      setLinked(null);
      setSyncRequired(false);
      setNotice('A fresh start. Your session is empty.');
    });
    inputRef.current?.focus();
  }
  async function copy() {
    await action(async () => {
      await navigator.clipboard.writeText(program.minilang);
      setNotice('Program copied to clipboard.');
    });
  }
  function download() {
    const url = URL.createObjectURL(
      new Blob([program.minilang + '\n'], { type: 'text/plain;charset=utf-8' }),
    );
    const link = document.createElement('a');
    link.href = url;
    link.download = 'program.ml';
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    setNotice('Downloaded program.ml.');
  }
  return (
    <div className="app-shell">
      <a className="skip-link" href="#english-input">
        Skip to English input
      </a>
      <header className="site-header">
        <a className="brand" href="./" aria-label="Parsley home">
          <span className="brand-mark">
            <Icon name="leaf" size={25} />
          </span>
          <span>
            parsley<span className="brand-period">.</span>
          </span>
        </a>
        <div className="header-divider" />
        <span className="header-tagline">English, compiled.</span>
        <div className="header-right">
          <BackendStatus api={api} mode={mode} mock={mock} revision={healthRevision} />
          <button
            className="icon-button theme-button"
            aria-label="Toggle color theme"
            title="Toggle color theme"
            onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
          >
            <Icon name={theme === 'light' ? 'moon' : 'sun'} />
          </button>
        </div>
      </header>
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            <span className="small-line" /> THE PARSLEY PLAYGROUND
          </div>
          <h1>
            Your words. <span>Working code.</span>
          </h1>
          <p>Build a little program, one English sentence at a time.</p>
        </div>
        <div className="verification-note">
          <span className="verification-symbol">
            ✓<span>3</span>
          </span>
          <p>
            Understood. Checked. Ready.
            <br />
            <strong>Three layers of verification.</strong>
          </p>
        </div>
      </div>
      <main className="workspace-shell">
        <aside className="examples-sidebar" aria-label="Examples">
          <div className="sidebar-heading">
            <span className="eyebrow">A LITTLE INSPIRATION</span>
            <h2>Start with an example</h2>
            <p>Click to add. Make it yours.</p>
          </div>
          <div className="example-list">
            {examples.map((example, i) => (
              <button
                key={example.sentence}
                aria-label={`Insert example: ${example.sentence}`}
                disabled={unavailable || pending}
                onClick={() => insert(example.sentence)}
              >
                <span className="example-index">{String(i + 1).padStart(2, '0')}</span>
                <span>
                  <strong>{example.category}</strong>
                  <span className="example-sentence">{example.sentence}</span>
                </span>
                <span className="example-arrow" aria-hidden="true">
                  ↗
                </span>
              </button>
            ))}
          </div>
          <div className="sidebar-bottom">
            <div className="context-note">
              <span aria-hidden="true">✦</span>
              <p>
                A little context goes a long way.
                <br />
                <strong>Try “add 5 to it” after a variable.</strong>
              </p>
            </div>
            <button className="help-button" onClick={() => setHelp(true)}>
              <Icon name="help" size={17} /> What can I say? <span aria-hidden="true">↗</span>
            </button>
          </div>
        </aside>
        <div className="workspace-main">
          <div className="workspace-toolbar">
            <div className="mode-control">
              <label htmlFor="mode">Compiler mode</label>
              <select
                id="mode"
                value={mode}
                disabled={unavailable || pending}
                onChange={(event) => setMode(event.target.value as Mode)}
              >
                <option value="rules">Rules</option>
                <option value="hybrid">Hybrid</option>
                <option value="llm">LLM</option>
              </select>
            </div>
            <div className="toolbar-actions">
              <button
                className="toolbar-button"
                aria-label="Undo last statement"
                title="Undo last statement"
                onClick={() => void undo()}
                disabled={unavailable || !sessionId || (!program.statements.length && !pending)}
              >
                <Icon name="undo" size={16} />
                <span>Undo</span>
              </button>
              <button
                className="toolbar-button"
                aria-label="Reset session"
                onClick={() => void reset()}
                disabled={busy}
              >
                <Icon name="reset" size={16} />
                <span>Reset</span>
              </button>
              <span className="toolbar-divider" />
              <button
                className="primary run-button"
                aria-label="Run program"
                disabled={unavailable || !sessionId || !program.statements.length || pending}
                onClick={() =>
                  void action(async () => {
                    setOutput(await api.run(sessionId));
                  })
                }
              >
                <Icon name="play" size={14} /> Run <span className="run-suffix">program</span>
              </button>
            </div>
          </div>
          <div className="workspace-columns">
            <section className="english-panel" aria-label="English workspace">
              <div className="panel-heading">
                <div className="panel-title">
                  <span className="section-icon">
                    <Icon name="chat" size={17} />
                  </span>
                  <h2>Your instructions</h2>
                </div>
                <span className="micro-label">ENGLISH</span>
              </div>
              <div className="conversation-scroll">
                <Conversation
                  messages={messages}
                  linked={linked}
                  busy={unavailable}
                  onAnswer={(id, value) => void answer(id, value)}
                  onInsert={insert}
                />
                <div ref={conversationEnd} />
              </div>
              <form
                className="composer"
                onSubmit={(event) => {
                  event.preventDefault();
                  void send();
                }}
              >
                <label className="sr-only" htmlFor="english-input">
                  English sentence
                </label>
                <div className="input-wrap">
                  <textarea
                    id="english-input"
                    ref={inputRef}
                    rows={2}
                    value={sentence}
                    aria-invalid={overlong}
                    aria-describedby={overlong ? 'sentence-limit' : undefined}
                    disabled={unavailable || !sessionId || pending}
                    placeholder={
                      syncRequired
                        ? 'Reconnect to refresh your program…'
                        : pending
                          ? 'Answer the clarification above to continue…'
                          : 'Tell Parsley what to do…'
                    }
                    onChange={(event) => setSentence(event.target.value)}
                    onKeyDown={(event) => {
                      if (
                        event.key === 'Enter' &&
                        !event.shiftKey &&
                        !event.nativeEvent.isComposing
                      ) {
                        event.preventDefault();
                        void send();
                      }
                      if (event.key === 'ArrowUp' && !sentence) {
                        event.preventDefault();
                        setSentence(lastSentence);
                      }
                    }}
                  />
                  <button
                    className="send-button"
                    aria-label="Send sentence"
                    disabled={unavailable || !sessionId || pending || !sentence.trim() || overlong}
                  >
                    <Icon name="arrow" size={19} />
                  </button>
                </div>
                <div className="input-hints">
                  <span>
                    {busy ? (
                      'Working…'
                    ) : pending ? (
                      'Waiting for your clarification'
                    ) : (
                      <>
                        <kbd>↵</kbd> to send <span className="hint-divider">·</span> <kbd>↑</kbd> to
                        recall
                      </>
                    )}
                  </span>
                  <span className={overlong ? 'input-too-long' : ''}>{sentenceLength}/500</span>
                </div>
                {overlong && (
                  <p id="sentence-limit" className="input-limit" role="alert">
                    Use 500 characters or fewer.
                  </p>
                )}
              </form>
            </section>
            <ProgramPanel
              program={program}
              output={output}
              linked={linked}
              onLink={setLinked}
              onCopy={() => void copy()}
              onDownload={download}
              busy={unavailable}
            />
          </div>
          <details className="trace-panel">
            <summary>
              <Icon name="code" size={15} />
              <span>Trace</span>
              <span className="trace-description">A look behind the translation</span>
              <span className="trace-chevron" aria-hidden="true">
                ⌄
              </span>
            </summary>
            <pre data-testid="trace-content">
              {JSON.stringify(
                messages.map((message) => ({
                  sentence: message.english,
                  status: message.result.status,
                  diagnostics: message.result.diagnostics,
                  trace: message.result.trace ?? 'No trace provided.',
                })),
                null,
                2,
              )}
            </pre>
          </details>
        </div>
      </main>
      <div className="feedback" aria-live="polite">
        {notice && <span role="status">✓ {notice}</span>}
        {error && (
          <div role="alert">
            {error}{' '}
            <button
              disabled={busy}
              onClick={() =>
                void action(async () => {
                  if (!sessionId) setSessionId((await api.session()).session_id);
                  else await refreshProgram();
                  setHealthRevision((revision) => revision + 1);
                })
              }
            >
              Retry connection
            </button>
          </div>
        )}
      </div>
      <footer className="site-footer">
        <span>
          <Icon name="leaf" size={14} /> Small language. Clear intentions.
        </span>
        <span>
          {mock
            ? 'Demo responses & simulated verification · no backend required'
            : 'Verification results are provided by your compiler backend'}
        </span>
      </footer>
      {warnings.length > 0 && <WarningToast warnings={warnings} onDismiss={dismissWarnings} />}
      {help && <HelpDialog onClose={() => setHelp(false)} />}
    </div>
  );
}
