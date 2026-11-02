import { useEffect, useState } from 'react';
import type { Api, Health, Mode } from '../api/types';

const labels = { rules: 'Rules', llm: 'LLM', hybrid: 'Hybrid' };
export function BackendStatus({
  api,
  mode,
  mock,
  revision,
}: {
  api: Api;
  mode: Mode;
  mock: boolean;
  revision: number;
}) {
  const [health, setHealth] = useState<Health | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    api
      .health()
      .then((result) => {
        if (active) {
          setHealth(result);
          setFailed(false);
        }
      })
      .catch(() => {
        if (active) {
          setHealth(null);
          setFailed(true);
        }
      });
    return () => {
      active = false;
    };
  }, [api, revision]);
  const backendMode = health?.mode && Object.hasOwn(labels, health.mode) ? health.mode : undefined;
  return (
    <span
      aria-label="Backend status"
      className={`backend-status ${failed ? 'is-offline' : ''}`}
      title={
        health
          ? `Version ${health.version}${health.provider ? ` · ${health.provider}` : ''}${health.model ? ` / ${health.model}` : ''}${mock ? ' · Simulated backend' : ''}`
          : 'Backend health status'
      }
    >
      <span className="status-dot" />
      <span>
        {backendMode ? 'Backend' : 'Requested'}: {labels[backendMode ?? mode]}
      </span>
      <span className="status-separator" aria-hidden="true">
        ·
      </span>
      <span>
        {failed
          ? 'Backend unavailable'
          : health
            ? health.llm_configured
              ? 'LLM configured'
              : 'LLM not configured'
            : 'Checking backend…'}
        {mock ? ' (mock)' : ''}
      </span>
      {health?.llm_budget_remaining === false && (
        <span role="status">LLM paused for today, using rules only</span>
      )}
    </span>
  );
}
