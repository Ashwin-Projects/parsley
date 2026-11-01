import { useEffect, useRef } from 'react';
import { Icon } from './Icon';
export function HelpDialog({ onClose }: { onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const dialog = ref.current;
    if (dialog?.showModal) dialog.showModal(); else dialog?.setAttribute('open', '');
    dialog?.querySelector('button')?.focus();
    return () => { dialog?.close?.(); previous?.focus(); };
  }, []);
  return <dialog ref={ref} aria-labelledby="help-title" onCancel={event => { event.preventDefault(); onClose(); }} onKeyDown={event => { if (event.key === 'Escape') onClose(); }}>
    <div className="help-heading"><span className="eyebrow">A SMALL LANGUAGE, BIG IDEAS</span><button onClick={onClose} aria-label="Close help"><Icon name="close" /></button></div>
    <h2 id="help-title">What can I say?</h2><p>One sentence, one instruction. Start with a variable, then build on it.</p>
    <dl className="help-examples"><div><dt>Create</dt><dd>make a variable called age and set it to 20</dd></div><div><dt>Change</dt><dd>set age to 30 · add 5 to it</dd></div><div><dt>Print</dt><dd>print age · show "Hello"</dd></div><div><dt>Decide</dt><dd>if age is greater than 17 then print adult else print minor</dd></div><div><dt>Repeat</dt><dd>repeat 3 times print hello</dd></div></dl>
    <p>Use quotes for literal text. “It” refers to your most recently used variable. If a value is missing or ambiguous, Parsley asks you to clarify.</p>
    <div className="help-verification"><strong>Three ways to check understanding</strong><p><b>V1</b> reads the meaning back to you.<br /><b>V2</b> checks the generated code’s structure.<br /><b>V3</b> compares two independent executions.</p><small>These checks don’t prove that every interpretation is correct. Mock mode simulates the results.</small></div>
    <p className="muted">MiniLang has numbers, strings, arithmetic, IF / ELSE and REPEAT. Functions, lists and while loops are outside its scope.</p>
    <button className="primary" onClick={onClose}>Got it, let’s build <Icon name="arrow" size={16} /></button>
  </dialog>;
}
