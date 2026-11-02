import { expect, test } from '@playwright/test';

test('a whole session against the real backend', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByLabel('Backend status')).not.toContainText('(mock)');
  const input = page.getByRole('textbox', { name: 'English sentence' });
  const line = (n: number, code: string) =>
    page.getByRole('button', { name: `Line ${n}: ${code}`, exact: true });
  const send = async (sentence: string) => {
    await expect(input).toBeEnabled();
    await input.fill(sentence);
    await input.press('Enter');
  };

  // Several sentences, and a pronoun resolved through the real symbol table.
  await send('make a variable called score and set it to 10');
  await expect(line(1, 'LET score = 10;')).toBeVisible();
  await send('add 5 to it');
  await expect(line(2, 'score = score + 5;')).toBeVisible();
  await expect(page.getByLabel('V3: ok').last()).toBeVisible();

  // A clarification answered by button.
  await send('set bonus to 1 or 2');
  await expect(page.getByText('1 or 2?')).toBeVisible();
  await page.getByRole('button', { name: '2', exact: true }).click();
  await expect(line(3, 'LET bonus = 2;')).toBeVisible();

  // A rejected sentence, recovered through its suggestion chip.
  await send('store 50 in bonus');
  await expect(page.getByText(/^E101/)).toBeVisible();
  await page.getByRole('button', { name: 'Try: set bonus to 50' }).click();
  await expect(input).toHaveValue('set bonus to 50');
  await input.press('Enter');
  await expect(line(4, 'bonus = 50;')).toBeVisible();

  // A derived amount needs a yes, and an accepted LLM reading says so.
  await page.getByLabel('Compiler mode').selectOption('hybrid');
  await send('double score');
  await expect(page.getByText('Did you mean: multiply score by 2?')).toBeVisible();
  await expect(line(5, 'score = score * 2;')).toHaveCount(0);
  await page.getByRole('button', { name: 'Yes', exact: true }).click();
  await expect(line(5, 'score = score * 2;')).toBeVisible();
  await expect(page.getByText('via LLM — check the reading')).toBeVisible();
  await expect(page.getByRole('status', { name: 'Compiler warnings' })).toContainText('W513');

  // Running goes through the real interpreter.
  await page.getByLabel('Compiler mode').selectOption('rules');
  await send('print score');
  await expect(line(6, 'PRINT score;')).toBeVisible();
  await page.getByRole('button', { name: 'Run program' }).click();
  await expect(page.getByTestId('run-output')).toHaveText('30');
  const variables = page.getByRole('region', { name: 'Final variables' });
  await expect(variables).toContainText('score');
  await expect(variables).toContainText('50');

  // Undo removes one statement on the server, and "it" follows.
  await page.getByRole('button', { name: 'Undo last statement' }).click();
  await expect(page.getByText('Last statement removed.')).toBeVisible();
  await expect(line(6, 'PRINT score;')).toHaveCount(0);
  await send('add 1 to it');
  await expect(line(6, 'score = score + 1;')).toBeVisible();

  // Reset empties the session on the server, not only on the page.
  await page.getByRole('button', { name: 'Reset session' }).click();
  await expect(page.getByText('A fresh start. Your session is empty.')).toBeVisible();
  await expect(page.getByRole('button', { name: /^Line 1:/ })).toHaveCount(0);
  await send('print score');
  await expect(line(1, 'PRINT "score";')).toBeVisible();

  expect(errors).toEqual([]);
});
