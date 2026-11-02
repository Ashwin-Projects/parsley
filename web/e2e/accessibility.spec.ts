import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('home, workspace, pipeline, and about have no serious accessibility violations', async ({
  page,
}, testInfo) => {
  await page.goto('/');
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    ),
  ).toBe(true);
  const check = async (name: string) => {
    const result = await new AxeBuilder({ page }).analyze();
    const serious = result.violations.filter((violation) =>
      ['serious', 'critical'].includes(violation.impact ?? ''),
    );
    expect(
      serious,
      `${name}: ${JSON.stringify(serious.map(({ id, nodes }) => ({ id, nodes: nodes.map((node) => node.target) })))}`,
    ).toEqual([]);
    console.log(
      `${testInfo.project.name} ${name}: ${result.violations.length} total violations; ${serious.length} serious/critical`,
    );
  };
  await check('home');
  await page.getByRole('link', { name: 'Try it' }).click();
  await check('workspace');
  await page.getByRole('button', { name: 'How it works' }).click();
  await check('how it works');
  await page.getByRole('button', { name: 'About' }).click();
  await check('about');
});

test('capture home, clarification workspace and pipeline', async ({ page }, testInfo) => {
  await page.goto('/');
  await expect(page.getByLabel('Backend status')).not.toContainText('Checking backend');
  test.skip(
    !(await page.getByLabel('Backend status').textContent())?.includes('(mock)'),
    'Screenshots use the deterministic mock.',
  );
  const device = testInfo.project.name;
  await page.screenshot({ path: `screenshots/home-${device}.png`, fullPage: true });
  const input = page.getByRole('textbox', { name: 'English sentence' });
  await expect(input).toBeEnabled();
  await page.getByLabel('Compiler mode').selectOption('llm');
  await input.fill('set age to 20');
  await input.press('Enter');
  await expect(page.getByText('via LLM — check the reading')).toBeVisible();
  await page.getByLabel('Compiler mode').selectOption('rules');
  await input.fill('increase age');
  await input.press('Enter');
  await expect(page.getByRole('textbox', { name: 'Clarification answer' })).toBeVisible();
  await page.locator('.workspace-shell').scrollIntoViewIfNeeded();
  await page.screenshot({ path: `screenshots/workspace-${device}.png`, fullPage: true });
  await page.getByRole('button', { name: 'How it works' }).click();
  await page.screenshot({ path: `screenshots/how-it-works-${device}.png`, fullPage: true });
});
