import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  testIgnore: ['**/*.real.spec.ts', '**/*.docker.spec.ts'],
  fullyParallel: true,
  workers: 2,
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'desktop', use: { browserName: 'chromium', viewport: { width: 1440, height: 1000 } } },
    {
      name: 'mobile',
      use: {
        browserName: 'chromium',
        viewport: { width: 375, height: 812 },
        isMobile: true,
        hasTouch: true,
      },
    },
  ],
  webServer: [
    {
      command: 'node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173 --strictPort',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: !process.env.CI,
      env: { VITE_USE_MOCK: 'true', VITE_API_URL: '' },
    },
    {
      command: 'node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5174 --strictPort',
      url: 'http://127.0.0.1:5174',
      reuseExistingServer: !process.env.CI,
      env: { VITE_USE_MOCK: 'false', VITE_API_URL: '' },
    },
  ],
});
