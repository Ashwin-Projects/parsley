import { defineConfig } from '@playwright/test';
import base from './playwright.config';

// The same suite against the real API, which replays tests/fixtures_llm/e2e.json with no
// network. Port 5174 stays for the specs that stub the API inside the browser.
const stubbed = (base.webServer as { url: string }[]).find((server) =>
  server.url.endsWith('5174'),
)!;

export default defineConfig({
  ...base,
  testIgnore: ['**/*.docker.spec.ts'],
  workers: 1,
  fullyParallel: false,
  webServer: [
    {
      command: 'python -m parsley.web --port 8000',
      cwd: '..',
      url: 'http://127.0.0.1:8000/api/health',
      reuseExistingServer: false,
      env: {
        PARSLEY_LLM_PROVIDER: 'fake',
        PARSLEY_LLM_FIXTURES: 'tests/fixtures_llm/e2e.json',
        // One address runs the whole suite here, far above what one visitor sends.
        PARSLEY_RATE_LIMIT_PER_MINUTE: '1000',
        PARSLEY_HARD_RATE_LIMIT_PER_MINUTE: '1000',
      },
    },
    {
      command: 'node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173 --strictPort',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: false,
      env: { VITE_USE_MOCK: 'false', VITE_API_URL: 'http://127.0.0.1:8000' },
    },
    stubbed as never,
  ],
});
