import { useEffect } from 'react';
import type { Diagnostic } from '../diagnostics';

export function WarningToast({
  warnings,
  onDismiss,
}: {
  warnings: Diagnostic[];
  onDismiss: () => void;
}) {
  useEffect(() => {
    const timer = window.setTimeout(onDismiss, 10_000);
    return () => window.clearTimeout(timer);
  }, [warnings, onDismiss]);
  return (
    <div className="warning-toast" role="status" aria-label="Compiler warnings" aria-live="polite">
      <div>
        <strong>A note about this reading</strong>
        {warnings.map((warning, index) => (
          <p key={`${warning.code}-${index}`}>
            <span>{warning.code}</span> {warning.message}
          </p>
        ))}
      </div>
      <button aria-label="Dismiss warnings" onClick={onDismiss}>
        ×
      </button>
    </div>
  );
}
