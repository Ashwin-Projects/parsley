import type { Program, RunResult } from '../api/types';
import { Icon } from './Icon';

function Highlight({ code }: { code: string }) {
  const tokens = code.split(/("(?:\\.|[^"\\])*"|\b(?:LET|PRINT|IF|THEN|ELSE|REPEAT|TIMES)\b|\b\d+(?:\.\d+)?\b|[=+*/<>-])/g);
  return <>{tokens.map((token, i) => <span key={i} className={token.startsWith('"') ? 'token-string' : /^(LET|PRINT|IF|THEN|ELSE|REPEAT|TIMES)$/.test(token) ? 'token-keyword' : /^\d/.test(token) ? 'token-number' : /^[=+*/<>-]$/.test(token) ? 'token-op' : ''}>{token}</span>)}</>;
}
export function ProgramPanel({ program, output, linked, onLink, onCopy, onDownload, busy }: {
  program: Program; output: RunResult | null; linked: number | null; onLink: (index: number | null) => void;
  onCopy: () => void; onDownload: () => void; busy: boolean;
}) {
  let lineNumber = 0;
  return <section className="program-panel" aria-label="MiniLang program">
    <div className="panel-heading"><div className="panel-title"><span className="section-icon"><Icon name="code" /></span><h2>Your program</h2><span className="count">{program.statements.length}</span></div><span className="micro-label">MINILANG</span></div>
    <div className="editor"><div className="editor-toolbar"><span className="file-tab"><span className="file-dot" /> program.ml</span><div className="editor-actions"><button aria-label="Copy program" title="Copy program" disabled={!program.minilang || busy} onClick={onCopy}><Icon name="copy" size={16} /></button><button aria-label="Download MiniLang file" title="Download .ml file" disabled={!program.minilang || busy} onClick={onDownload}><Icon name="download" size={16} /></button></div></div>
      <div className="code-body"><div className="code-comment">// A little English. A real program.</div>
        {!program.statements.length ? <div className="code-empty"><span>01</span><span>Your MiniLang will appear here<span className="cursor" /></span></div> : program.statements.flatMap((statement, index) => statement.minilang.split('\n').map((line, subline) => {
          const number = ++lineNumber;
          return <button key={`${index}-${subline}`} className={`code-line ${linked === index ? 'is-linked' : ''}`} aria-label={`Line ${number}: ${line}`} onMouseEnter={() => onLink(index)} onMouseLeave={() => onLink(null)} onFocus={() => onLink(index)} onBlur={() => onLink(null)}><span className="line-number" aria-hidden="true">{String(number).padStart(2, '0')}</span><code><Highlight code={line} /></code></button>;
        }))}
      </div><div className="editor-footer"><span><span className="status-dot" /> {program.statements.length ? `${program.statements.length} statements compiled` : 'Waiting for your first sentence'}</span><span>UTF-8</span></div></div>
    <p className="mapping-hint"><span aria-hidden="true">↖</span> Hover or focus a line to find its English sentence.</p>
    <section className="output-panel" aria-label="Program results"><div className="output-heading"><h3><span aria-hidden="true">›_</span> Console</h3><span>{output ? output.error ? 'Runtime error' : 'Execution complete' : 'Ready to run'}</span></div>
      {output ? <><div className="console-output" data-testid="run-output">{output.output.length ? output.output.map((line, i) => <div key={i}>{line}</div>) : <span className="muted">Program finished without output.</span>}</div>{output.error && <p className="runtime-error" role="alert">{output.error}</p>}<section className="variables" aria-label="Final variables"><h4>FINAL VARIABLES</h4>{Object.keys(output.variables).length ? <dl>{Object.entries(output.variables).map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{JSON.stringify(value)}</dd></div>)}</dl> : <p className="muted">No variables declared.</p>}</section></> : <div className="console-placeholder">Run your program to see its output and final variables.</div>}
    </section>
  </section>;
}
