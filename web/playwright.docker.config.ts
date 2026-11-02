import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.docker.spec.ts',
  workers: 1,
  use: {
    baseURL: process.env.PARSLEY_TEST_URL || 'http://localhost:8080',
    browserName: 'chromium',
    viewport: { width: 1440, height: 1000 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
});
