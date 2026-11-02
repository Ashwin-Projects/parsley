import { expect, test } from '@playwright/test';

test('run shows final values without changing the downloaded program', async ({ page }, info) => {
  await page.goto('/');
  const input = page.getByRole('textbox', { name: 'English sentence' });
  await expect(input).toBeEnabled();
  await input.fill('set t to 3 plus 5');
  await input.press('Enter');
  await expect(page.getByRole('button', { name: 'Line 1: LET t = 3 + 5;' })).toBeVisible();
  await page.getByRole('button', { name: 'Run program' }).click();
  await expect(page.getByText('Final value: t = 8')).toBeVisible();
  await expect(page.getByText('// t = 8')).toBeVisible();
  await expect(page.getByText(/This program prints nothing/)).toContainText('print t');
  if (info.project.name === 'mobile') {
    await expect
      .poll(() =>
        page.getByRole('region', { name: 'Program results' }).evaluate((el) => {
          const rect = el.getBoundingClientRect();
          return rect.top >= 0 && rect.top < innerHeight;
        }),
      )
      .toBe(true);
  }
  await page.screenshot({
    path: `screenshots/run-values-${info.project.name}.png`,
    fullPage: true,
  });
  const pending = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download MiniLang file' }).click();
  const download = await pending;
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream) chunks.push(Buffer.from(chunk));
  expect(Buffer.concat(chunks).toString()).toBe('LET t = 3 + 5;\n');
});

test('compile, clarify and run a mock session', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  const input = page.getByRole('textbox', { name: 'English sentence' });
  await expect(input).toBeEnabled();
  await input.fill('make a variable called age and set it to 20');
  await input.press('Enter');
  await expect(page.getByRole('button', { name: 'Line 1: LET age = 20;' })).toBeVisible();
  await input.fill('set age to 10 or 20');
  await input.press('Enter');
  await page.getByRole('button', { name: '20', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Line 2: age = 20;' })).toBeVisible();
  await input.fill('print age');
  await input.press('Enter');
  await expect(page.getByRole('button', { name: 'Line 3: PRINT age;' })).toBeVisible();
  await page.getByRole('button', { name: 'Run program' }).click();
  await expect(page.getByTestId('run-output')).toHaveText('20');
  await expect(page.getByRole('region', { name: 'Final variables' })).toContainText('20');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(errors).toEqual([]);
  // The backend-decision flow owns the main workspace screenshots.
});

test('keyboard help, theme, trace and program download', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'What can I say?' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Tab');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await page.getByRole('button', { name: 'Toggle color theme' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  const input = page.getByRole('textbox', { name: 'English sentence' });
  await input.fill('print "Hello"');
  await input.press('Enter');
  await expect(page.getByRole('button', { name: 'Download MiniLang file' })).toBeEnabled();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download MiniLang file' }).click();
  expect((await download).suggestedFilename()).toBe('program.ml');
  await page.getByText('Trace', { exact: true }).click();
  await expect(page.getByTestId('trace-content')).toContainText('accepted');
});
