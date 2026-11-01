import type { CompileResult } from '../api/types';

const descriptions = {
  v1: 'Back-translation',
  v2: 'Structural round-trip',
  v3: 'Execution equivalence',
};
export function VerificationBadges({ checks }: Pick<CompileResult, 'checks'>) {
  return (
    <span className="badges">
      {(['v1', 'v2', 'v3'] as const).map((key) => {
        const state = checks?.[key] ?? 'not reported';
        return (
          <span
            key={key}
            className={`badge ${state === 'not reported' ? 'skipped' : state}`}
            aria-label={`${key.toUpperCase()}: ${state}`}
            title={`${descriptions[key]}: ${state}`}
          >
            <span aria-hidden="true">{state === 'ok' ? '✓' : state === 'fail' ? '×' : '−'}</span>{' '}
            {key.toUpperCase()}
          </span>
        );
      })}
    </span>
  );
}
