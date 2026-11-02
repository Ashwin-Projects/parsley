import { expect, test, type Page } from '@playwright/test';

test('LLM reading and derived-value clarification', async ({ page }, info) => {
  await page.goto('/');
  await expect(page.getByLabel('Backend status')).toContainText('LLM configured');
  await page.getByLabel('Compiler mode').selectOption('llm');
  const input = page.getByRole('textbox', { name: 'English sentence' });
  await input.fill('set x to 10');
  await input.press('Enter');
  await expect(page.getByText('via LLM — check the reading')).toBeVisible();
  await expect(page.getByRole('status', { name: 'Compiler warnings' })).toContainText('W513');
  await expect(page.getByRole('button', { name: 'Line 1: LET x = 10;' })).toBeVisible();
  await input.fill('double x');
  await input.press('Enter');
  await expect(page.getByText('Did you mean: multiply x by 2?')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Yes', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'No', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  // Full-page captures should start at the top rather than the mobile keyboard's scroll offset.
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `screenshots/workspace-${info.project.name}.png`, fullPage: true });
  await page.getByRole('button', { name: 'No', exact: true }).click();
  await expect(input).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Line 2: x = x * 2;' })).toHaveCount(0);
  await input.fill('double x');
  await input.press('Enter');
  await page.getByRole('button', { name: 'Yes', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Line 2: x = x * 2;' })).toBeVisible();
  await page.getByRole('button', { name: 'Run program' }).click();
  await expect(page.getByRole('region', { name: 'Final variables' })).toContainText('20');
});

test('long input stays editable and cannot be sent', async ({ page }) => {
  await page.goto('/');
  const input = page.getByRole('textbox', { name: 'English sentence' });
  await expect(input).toBeEnabled();
  await input.fill('a'.repeat(501));
  await input.press('Enter');
  await expect(input).toHaveValue('a'.repeat(501));
  await expect(page.getByRole('button', { name: 'Send sentence' })).toBeDisabled();
  await expect(page.getByText('Use 500 characters or fewer.')).toBeVisible();
  await expect(page.getByRole('button', { name: /^Line 1:/ })).toHaveCount(0);
});

async function stubApi(page: Page, unavailable = false) {
  const state = { unavailable };
  // Match backend routes only, not Vite's /src/api/client.ts module request.
  await page.route('http://127.0.0.1:5174/api/**', async (route) => {
    if (state.unavailable) {
      await route.fulfill({ status: 503, body: 'unavailable' });
      return;
    }
    const path = new URL(route.request().url()).pathname;
    const body =
      path === '/api/health'
        ? { version: 'browser-test', llm_configured: false, mode: 'hybrid' }
        : path === '/api/session'
          ? { session_id: 'browser-fixture' }
          : path === '/api/program'
            ? { minilang: '', statements: [] }
            : { ok: true };
    await route.fulfill({ json: body });
  });
  return state;
}

test.describe('HTTP transport with browser-local API fixtures', () => {
  test.use({ baseURL: 'http://127.0.0.1:5174' });

  test('backend down recovers through explicit retry and reports backend mode', async ({
    page,
  }) => {
    const state = await stubApi(page, true);
    await page.goto('/');
    await expect(page.getByRole('alert')).toContainText('Backend unavailable');
    await expect(page.getByLabel('Backend status')).toContainText('Backend unavailable');
    state.unavailable = false;
    await page.getByRole('button', { name: 'Retry connection' }).click();
    await expect(page.getByRole('textbox', { name: 'English sentence' })).toBeEnabled();
    await expect(page.getByLabel('Backend status')).toContainText('Backend: Hybrid');
    await expect(page.getByLabel('Backend status')).toContainText('LLM not configured');
  });

  test('429 explains Retry-After and preserves the sentence without replaying', async ({
    page,
  }) => {
    await stubApi(page);
    let attempts = 0;
    await page.route('**/api/compile', async (route) => {
      attempts++;
      await route.fulfill({
        status: 429,
        headers: { 'Retry-After': '12' },
        body: 'private provider data',
      });
    });
    await page.goto('/');
    const input = page.getByRole('textbox', { name: 'English sentence' });
    await expect(input).toBeEnabled();
    await input.fill('print hello');
    await input.press('Enter');
    await expect(page.getByRole('alert')).toContainText(
      'Rate limited. Please retry in 12 seconds.',
    );
    await expect(page.getByRole('alert')).not.toContainText('private provider data');
    await expect(input).toHaveValue('print hello');
    expect(attempts).toBe(1);
  });

  test('stalled requests time out and retain the sentence for review', async ({ page }) => {
    await stubApi(page);
    let attempts = 0;
    await page.route('**/api/compile', () => {
      attempts++;
    });
    await page.goto('/');
    const input = page.getByRole('textbox', { name: 'English sentence' });
    await expect(input).toBeEnabled();
    await page.clock.install();
    await input.fill('print hello');
    await input.press('Enter');
    await expect.poll(() => attempts).toBe(1);
    await page.clock.fastForward(30_001);
    await expect(page.getByRole('alert')).toContainText('Request timed out');
    await expect(input).toHaveValue('print hello');
    await expect(input).toBeDisabled();
    await expect(page.getByText(/The last change could not be confirmed/)).toBeVisible();
    expect(attempts).toBe(1);
    await page.getByRole('button', { name: 'Reset session' }).click();
    await expect(input).toBeEnabled();
  });

  test('all five warning codes stay non-blocking and appear in trace', async ({ page }) => {
    await stubApi(page);
    await page.route('**/api/program?**', (route) =>
      route.fulfill({
        json: {
          minilang: 'PRINT "hello";',
          statements: [{ english: 'print hello', minilang: 'PRINT "hello";' }],
        },
      }),
    );
    await page.route('**/api/compile', (route) =>
      route.fulfill({
        json: {
          status: 'accepted',
          minilang: 'PRINT "hello";',
          understood: 'print "hello".',
          source: 'llm',
          checks: { v1: 'ok', v2: 'ok', v3: 'ok' },
          diagnostics: [510, 511, 512, 513, 514].map((code) => ({
            code: `W${code}`,
            stage: 'llm',
            message: `Warning ${code}`,
          })),
        },
      }),
    );
    await page.goto('/');
    const input = page.getByRole('textbox', { name: 'English sentence' });
    await expect(input).toBeEnabled();
    await input.fill('print hello');
    await input.press('Enter');
    const toast = page.getByRole('status', { name: 'Compiler warnings' });
    for (const code of [510, 511, 512, 513, 514]) await expect(toast).toContainText(`W${code}`);
    await expect(input).toBeEnabled();
    await page.getByText('Trace', { exact: true }).click();
    for (const code of [510, 511, 512, 513, 514])
      await expect(page.getByTestId('trace-content')).toContainText(`W${code}`);
  });
});
