import { useState } from 'react';
import type { CompileResult, RunResult } from '../api/types';
import { finalValue } from '../run-values';
import { VerificationBadges } from './VerificationBadges';
import { Icon } from './Icon';
import { isLlmWarning } from '../diagnostics';
export interface Message {
  id: number;
  english: string;
  result: CompileResult;
  statementIndex?: number;
  answer?: string;
  exchanges?: { question: string; answer: string; diagnostics: CompileResult['diagnostics'] }[];
}
function Question({
  result,
  busy,
  onAnswer,
}: {
  result: CompileResult;
  busy: boolean;
  onAnswer: (answer: string) => void;
}) {
  const [value, setValue] = useState('');
  const question = result.question;
  if (!question) return <p>Clarification is needed, but no question was provided.</p>;
  const options = question.kind === 'derived_value' ? ['Yes', 'No'] : question.options;
  return (
    <div className="question">
      <span className="question-label">LET’S CLEAR ONE THING UP</span>
      <p>{question.text}</p>
      {options.length ? (
        <div className="options">
          {options.map((option, i) => (
            <button key={`${i}-${option}`} disabled={busy} onClick={() => onAnswer(option)}>
              {option}
              <Icon name="arrow" size={14} />
            </button>
          ))}
        </div>
      ) : (
        <form
          className="answer-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (value.trim()) onAnswer(value.trim());
          }}
        >
          <input
            aria-label="Clarification answer"
            placeholder="Enter a value…"
            value={value}
            disabled={busy}
            onChange={(event) => setValue(event.target.value)}
          />
          <button
            className="primary"
            disabled={busy || !value.trim()}
            aria-label="Submit clarification"
          >
            <Icon name="arrow" size={16} />
          </button>
        </form>
      )}
    </div>
  );
}
export function Conversation({
  messages,
  linked,
  busy,
  onAnswer,
  onInsert,
  output,
}: {
  messages: Message[];
  linked: number | null;
  busy: boolean;
  onAnswer: (id: number, answer: string) => void;
  onInsert: (sentence: string) => void;
  output: RunResult | null;
}) {
  return (
    <div
      className="conversation"
      role="log"
      aria-label="English conversation"
      aria-live="polite"
      aria-relevant="additions text"
    >
      <div className="intro-message">
        <span className="assistant-avatar">
          <Icon name="leaf" size={20} />
        </span>
        <div>
          <strong>Let’s make something in plain English.</strong>
          <p>
            Tell me what your program should do.
            <br /> I’ll translate it, check it, and ask when I’m unsure.
          </p>
        </div>
      </div>
      {!messages.length && (
        <div className="conversation-empty">
          <div className="empty-orbit">
            <Icon name="chat" size={28} />
            <span>✦</span>
          </div>
          <h3>
            Every program starts
            <br />
            with a sentence.
          </h3>
          <p>
            Try an example on the left,
            <br />
            or write your own below.
          </p>
          <button
            className="starter-chip"
            disabled={busy}
            onClick={() => onInsert('make a variable called age and set it to 20')}
          >
            Start with a variable <Icon name="arrow" size={15} />
          </button>
        </div>
      )}
      {messages.map((message, index) => (
        <article
          key={message.id}
          data-testid={`sentence-${message.statementIndex ?? `pending-${message.id}`}`}
          className={`message ${message.statementIndex !== undefined && linked === message.statementIndex ? 'is-linked' : ''}`}
        >
          <div className="user-message">
            <span className="sentence-number">{String(index + 1).padStart(2, '0')}</span>
            <p>{message.english}</p>
            <span className="you-label">YOU</span>
          </div>
          <div className="assistant-message">
            <span className={`response-marker ${message.result.status}`} aria-hidden="true">
              {message.result.status === 'accepted'
                ? '✓'
                : message.result.status === 'clarify'
                  ? '?'
                  : '!'}
            </span>
            <div className="response-body">
              {message.answer && <p className="answer-receipt">You clarified: {message.answer}</p>}
              {message.result.status === 'accepted' && (
                <>
                  <p className="understood">
                    <strong>I understood:</strong>{' '}
                    {message.result.understood ?? 'No back-translation was provided.'}
                    {(message.result.source === 'llm' ||
                      message.result.diagnostics.some(
                        (diagnostic) => diagnostic.code === 'W513',
                      )) && <span className="llm-tag">via LLM — check the reading</span>}
                  </p>
                  <div className="response-meta">
                    <VerificationBadges checks={message.result.checks} />
                  </div>
                  {message.result.minilang?.split('\n').map((line, i) => {
                    const value = finalValue(line, output);
                    return value ? (
                      <p className="final-value" key={i}>
                        Final value: {value}
                      </p>
                    ) : null;
                  })}
                </>
              )}
              {message.result.status === 'clarify' && (
                <Question
                  result={message.result}
                  busy={busy}
                  onAnswer={(answer) => onAnswer(message.id, answer)}
                />
              )}
              {message.result.diagnostics
                .filter((diagnostic) => !isLlmWarning(diagnostic))
                .map((diagnostic, i) => (
                  <p
                    key={i}
                    className={`diagnostic ${message.result.status === 'accepted' ? '' : 'diagnostic-error'}`}
                  >
                    <span title={diagnostic.stage}>{diagnostic.code}</span> {diagnostic.message}
                  </p>
                ))}
              {message.result.suggestion && (
                <button
                  className="suggestion"
                  disabled={busy}
                  onClick={() => onInsert(message.result.suggestion!)}
                >
                  Try: {message.result.suggestion}
                  <Icon name="arrow" size={14} />
                </button>
              )}
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}
