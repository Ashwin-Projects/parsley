import { useState } from 'react';
import type { CompileResult } from '../api/types';
import { VerificationBadges } from './VerificationBadges';
import { Icon } from './Icon';
export interface Message { id: number; english: string; result: CompileResult; statementIndex?: number; answer?: string }
function Question({ result, busy, onAnswer }: { result: CompileResult; busy: boolean; onAnswer: (answer: string) => void }) {
  const [value, setValue] = useState('');
  const question = result.question;
  if (!question) return <p>Clarification is needed, but no question was provided.</p>;
  return <div className="question"><span className="question-label">LET’S CLEAR ONE THING UP</span><p>{question.text}</p>{question.options.length ? <div className="options">{question.options.map((option, i) => <button key={`${i}-${option}`} disabled={busy} onClick={() => onAnswer(option)}>{option}<Icon name="arrow" size={14} /></button>)}</div> : <form className="answer-form" onSubmit={event => { event.preventDefault(); if (value.trim()) onAnswer(value.trim()); }}><input aria-label="Clarification answer" placeholder="Enter a value…" value={value} disabled={busy} onChange={event => setValue(event.target.value)} /><button className="primary" disabled={busy || !value.trim()} aria-label="Submit clarification"><Icon name="arrow" size={16} /></button></form>}</div>;
}
export function Conversation({ messages, linked, busy, onAnswer, onInsert }: {
  messages: Message[]; linked: number | null; busy: boolean; onAnswer: (id: number, answer: string) => void; onInsert: (sentence: string) => void;
}) {
  return <div className="conversation" role="log" aria-label="English conversation" aria-live="polite" aria-relevant="additions text">
    <div className="intro-message"><span className="assistant-avatar"><Icon name="leaf" size={20} /></span><div><strong>Let’s make something in plain English.</strong><p>Tell me what your program should do.<br />I’ll translate it, check it, and ask when I’m unsure.</p></div></div>
    {!messages.length && <div className="conversation-empty"><div className="empty-orbit"><Icon name="chat" size={28} /><span>✦</span></div><h3>Every program starts<br />with a sentence.</h3><p>Try an example on the left,<br />or write your own below.</p><button className="starter-chip" disabled={busy} onClick={() => onInsert('make a variable called age and set it to 20')}>Start with a variable <Icon name="arrow" size={15} /></button></div>}
    {messages.map((message, index) => <article key={message.id} data-testid={`sentence-${message.statementIndex ?? `pending-${message.id}`}`} className={`message ${message.statementIndex !== undefined && linked === message.statementIndex ? 'is-linked' : ''}`}>
      <div className="user-message"><span className="sentence-number">{String(index + 1).padStart(2, '0')}</span><p>{message.english}</p><span className="you-label">YOU</span></div>
      <div className="assistant-message"><span className={`response-marker ${message.result.status}`} aria-hidden="true">{message.result.status === 'accepted' ? '✓' : message.result.status === 'clarify' ? '?' : '!'}</span><div className="response-body">
        {message.answer && <p className="answer-receipt">You clarified: {message.answer}</p>}
        {message.result.status === 'accepted' && <><p className="understood"><strong>I understood:</strong> {message.result.understood ?? 'No back-translation was provided.'}</p><div className="response-meta"><VerificationBadges checks={message.result.checks} />{message.result.source === 'llm' && <span className="llm-tag">✦ via LLM</span>}</div></>}
        {message.result.status === 'clarify' && <Question result={message.result} busy={busy} onAnswer={answer => onAnswer(message.id, answer)} />}
        {message.result.diagnostics.map((diagnostic, i) => <p key={i} className={`diagnostic ${message.result.status === 'accepted' ? '' : 'diagnostic-error'}`}><span title={diagnostic.stage}>{diagnostic.code}</span> {diagnostic.message}</p>)}
        {message.result.suggestion && <button className="suggestion" disabled={busy} onClick={() => onInsert(message.result.suggestion!)}>Try: {message.result.suggestion}<Icon name="arrow" size={14} /></button>}
      </div></div>
    </article>)}
  </div>;
}
