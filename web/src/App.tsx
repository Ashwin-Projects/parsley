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
import { RequestError } from './api/client';

const emptyProgram: Program = { minilang: '', statements: [] };
export default function App({ api, mock = true }: { api: Api; mock?: boolean }) {
  const [page, setPage] = useState<'home' | 'how' | 'about'>('home');
  const [sessionId, setSessionId] = useState('');
  const [program, setProgram] = useState<Program>(emptyProgram);
  const [messages, setMessages] = useState<Message[]>([]);
  const [mode, setMode] = useState<Mode>('rules');
  const [sentence, setSentence] = useState('');
  const [lastSentence, setLastSentence] = useState('');
  const [busy, setBusy] = useState(false);
  const [pendingSentence, setPendingSentence] = useState('');
  const [syncRequired, setSyncRequired] = useState(false);
  const [mutationUncertain, setMutationUncertain] = useState(false);
  const unavailable = busy || syncRequired || mutationUncertain;
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
    conversationEnd.current?.scrollIntoView?.({ block: 'nearest', behavior: 'auto' });
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
  async function mutation<T>(work: () => Promise<T>): Promise<T> {
    try {
      return await work();
    } catch (cause) {
      setHealthRevision((revision) => revision + 1);
      if (cause instanceof RequestError && cause.outcomeUncertain) {
        setMutationUncertain(true);
        setSyncRequired(true);
        setOutput(null);
        setWarnings([]);
      }
      throw cause;
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
      exchanges:
        id === undefined
          ? []
          : [
              ...(messages.find((item) => item.id === id)?.exchanges ?? []),
              ...(answer && messages.find((item) => item.id === id)?.result.question
                ? [
                    {
                      question: messages.find((item) => item.id === id)!.result.question!.text,
                      answer,
                      diagnostics: messages.find((item) => item.id === id)!.result.diagnostics,
                    },
                  ]
                : []),
            ],
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
    setMessages((current) => {
      const retained = current.filter(
        (message) =>
          (!mutationUncertain || message.result.status !== 'clarify') &&
          (message.statementIndex === undefined ||
            message.statementIndex < updated.statements.length),
      );
      if (!mutationUncertain) return retained;
      const recovered: Message[] = updated.statements.flatMap((statement, index) =>
        retained.some((message) => message.statementIndex === index)
          ? []
          : [
              {
                id: -(index + 1),
                english: statement.english,
                statementIndex: index,
                result: {
                  status: 'accepted' as const,
                  minilang: statement.minilang,
                  diagnostics: [],
                  trace: { recovered: true, verification: 'Not returned; response was lost.' },
                },
              },
            ],
      );
      return [...retained, ...recovered];
    });
    setSyncRequired(false);
    return updated;
  }
  async function send() {
    if (
      overlong ||
      !sentence.trim() ||
      !sessionId ||
      pending ||
      syncRequired ||
      mutationUncertain ||
      lock.current
    )
      return;
    const english = sentence.trim();
    setPendingSentence(english);
    await action(async () => {
      const result = await mutation(() => api.compile(sessionId, english, mode));
      rememberResult(result, english);
      setSyncRequired(true);
      setSentence('');
      setLastSentence(english);
      await refreshProgram();
    });
    setPendingSentence('');
    inputRef.current?.focus();
  }
  async function answer(id: number, value: string) {
    const original = messages.find((message) => message.id === id);
    if (!original || syncRequired || mutationUncertain) return;
    setPendingSentence(original.english);
    await action(async () => {
      const result = await mutation(() => api.answer(sessionId, value));
      rememberResult(result, original.english, id, value);
      setSyncRequired(true);
      await refreshProgram();
      if (result.status === 'clarify')
        setNotice('That answer did not resolve the question. Please try again.');
    });
    setPendingSentence('');
    inputRef.current?.focus();
  }
  async function undo() {
    if (syncRequired || mutationUncertain) return;
    await action(async () => {
      if (!(await mutation(() => api.undo(sessionId))).ok)
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
      if (sessionId && !mutationUncertain) {
        if (!(await mutation(() => api.reset(sessionId))).ok)
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
      setMutationUncertain(false);
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
  function downloadTranscript() {
    const text = messages
      .map((message) =>
        [
          `English: ${message.english}`,
          ...(message.exchanges ?? []).flatMap(({ question, answer, diagnostics }) => [
            `Question: ${question}`,
            `Answer: ${answer}`,
            ...diagnostics.map((diagnostic) => `${diagnostic.code}: ${diagnostic.message}`),
          ]),
          ...(message.result.question ? [`Question: ${message.result.question.text}`] : []),
          ...(message.result.understood ? [`I understood: ${message.result.understood}`] : []),
          ...(message.result.minilang ? [`MiniLang: ${message.result.minilang}`] : []),
          ...message.result.diagnostics.map(
            (diagnostic) => `${diagnostic.code}: ${diagnostic.message}`,
          ),
        ].join('\n'),
      )
      .join('\n\n');
    const url = URL.createObjectURL(new Blob([text + '\n'], { type: 'text/plain;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'transcript.txt';
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    setNotice('Downloaded transcript.txt.');
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
        <nav aria-label="Main navigation" className="page-nav">
          <button onClick={() => setPage('home')}>Home</button>
          <button onClick={() => setPage('how')}>How it works</button>
          <button onClick={() => setPage('about')}>About</button>
        </nav>
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
      {page === 'how' && (
        <main className="info-page">
          <h1>How it works</h1>
          <p>Parsley uses context and verification to translate each sentence.</p>
          <ol className="pipeline">
            <li>
              <strong>English</strong> — describe an instruction.
            </li>
            <li>
              <strong>N1</strong> — resolve names and references using context.
            </li>
            <li>
              <strong>N2</strong> — ask a question when the meaning is unclear.
            </li>
            <li>
              <strong>MiniLang</strong> — build and check the program.
            </li>
            <li>
              <strong>V1 / V2 / V3</strong> — review the interpretation, compare structure, and
              check execution.
            </li>
          </ol>
          <p>These checks do not prove that the English was interpreted correctly.</p>
        </main>
      )}
      {page === 'about' && (
        <main className="info-page">
          <h1>About</h1>
          <p>Parsley is an English-to-MiniLang compiler built at VIT.</p>
          <ul>
            <li>Ashwin L</li>
            <li>Aditya Kishor</li>
            <li>Maheep Singh</li>
          </ul>
          <p>
            <a href="https://github.com/Ashwin-Projects/parsley">Explore Parsley on GitHub</a>
          </p>
        </main>
      )}
      <div hidden={page !== 'home'}>
        <div className="page-heading">
          <div>
            <div className="eyebrow">
              <span className="small-line" /> THE PARSLEY PLAYGROUND
            </div>
            <h1>
              Your words. <span>Working code.</span>
            </h1>
            <p>Build a little program, one English sentence at a time.</p>
            <a href="#english-input" className="primary try-link">
              Try it
            </a>
            <ol className="intro-steps">
              <li>Write in English</li>
              <li>Answer questions when unclear</li>
              <li>Get verified MiniLang</li>
            </ol>
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
                  disabled={unavailable || pending}
                  onClick={() => insert(example.sentence)}
                >
                  <span className="sr-only">Insert example: </span>
                  <span className="example-index" aria-hidden="true">
                    {String(i + 1).padStart(2, '0')}
                  </span>
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
                <small className="privacy-note">
                  Hybrid and LLM modes send your sentence to a third-party model (Groq).
                </small>
              </div>
              <div className="toolbar-actions">
                <button
                  className="toolbar-button"
                  disabled={busy || !messages.length}
                  onClick={downloadTranscript}
                >
                  Download transcript
                </button>
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
                  {pendingSentence && <p role="status">Compiling: {pendingSentence}</p>}
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
                        mutationUncertain
                          ? 'Reset session to continue…'
                          : syncRequired
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
                      disabled={
                        unavailable || !sessionId || pending || !sentence.trim() || overlong
                      }
                    >
                      <Icon name="arrow" size={19} />
                    </button>
                  </div>
                  <div className="input-hints">
                    <span>
                      {busy ? (
                        'Working…'
                      ) : mutationUncertain ? (
                        'Reset session to continue'
                      ) : pending ? (
                        'Waiting for your clarification'
                      ) : (
                        <>
                          <kbd>↵</kbd> to send <span className="hint-divider">·</span> <kbd>↑</kbd>{' '}
                          to recall
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
                busy={busy || syncRequired}
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
      </div>
      <div className="feedback" aria-live="polite">
        {mutationUncertain && (
          <p className="uncertain-note">
            The last change could not be confirmed. Retry connection to inspect and export the saved
            program, then Reset session before continuing. Verification for recovered statements is
            not reported.
          </p>
        )}
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
