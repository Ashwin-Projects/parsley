import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import App from './App';
import { createApi } from './api/client';
import { createMockTransport } from './mock/api';
import { VerificationBadges } from './components/VerificationBadges';

function mount() {
  render(<App api={createApi(createMockTransport())} />);
}
async function send(sentence: string) {
  const input = await screen.findByRole('textbox', { name: 'English sentence' });
  await waitFor(() => expect(input).toBeEnabled());
  fireEvent.change(input, { target: { value: sentence } });
  input.focus();
  await userEvent.keyboard('{Enter}');
}

describe('workspace', () => {
  it('compiles, maps source on focus, recalls input, runs, undoes and resets', async () => {
    mount();
    await send('set age to 20');
    const line = await screen.findByRole('button', { name: 'Line 1: LET age = 20;' });
    fireEvent.focus(line);
    expect(screen.getByTestId('sentence-0')).toHaveClass('is-linked');
    expect(screen.getByTestId('sentence-0')).toHaveTextContent(
      'I understood: create variable age with value 20',
    );
    const input = screen.getByRole('textbox', { name: 'English sentence' });
    fireEvent.keyDown(input, { key: 'ArrowUp' });
    expect(input).toHaveValue('set age to 20');
    await userEvent.clear(input);
    await send('print age');
    await userEvent.click(screen.getByRole('button', { name: 'Run program' }));
    expect(await screen.findByTestId('run-output')).toHaveTextContent('20');
    await userEvent.click(screen.getByRole('button', { name: 'Undo last statement' }));
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Line 2: PRINT age;' })).not.toBeInTheDocument(),
    );
    await userEvent.click(screen.getByRole('button', { name: 'Reset session' }));
    await waitFor(() => expect(screen.queryByText(/I understood:/)).not.toBeInTheDocument());
  });

  it('answers options and free text, and inserts a rejected rewrite', async () => {
    mount();
    await send('set age to 10 or 20');
    await userEvent.click(await screen.findByRole('button', { name: '20' }));
    await screen.findByRole('button', { name: 'Line 1: LET age = 20;' });
    await send('increase age');
    await userEvent.type(
      await screen.findByRole('textbox', { name: 'Clarification answer' }),
      '3{Enter}',
    );
    await screen.findByRole('button', { name: 'Line 2: age = age + 3;' });
    await send('store 50 in bonus');
    await userEvent.click(await screen.findByRole('button', { name: 'Try: set bonus to 50' }));
    expect(screen.getByRole('textbox', { name: 'English sentence' })).toHaveValue(
      'set bonus to 50',
    );
  });

  it('provides eight examples, an accessible help dialog and theme control', async () => {
    mount();
    const examples = screen.getByRole('complementary', { name: 'Examples' });
    expect(within(examples).getAllByRole('button', { name: /Insert example/ })).toHaveLength(8);
    await userEvent.click(within(examples).getAllByRole('button', { name: /Insert example/ })[0]);
    expect(screen.getByRole('textbox', { name: 'English sentence' })).not.toHaveValue('');
    await userEvent.click(screen.getByRole('button', { name: 'What can I say?' }));
    expect(screen.getByRole('dialog', { name: 'What can I say?' })).toBeVisible();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Toggle color theme' }));
    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('shows verification state in text as well as color', () => {
    render(<VerificationBadges checks={{ v1: 'ok', v2: 'fail', v3: 'skipped' }} />);
    expect(screen.getByLabelText('V1: ok')).toBeVisible();
    expect(screen.getByLabelText('V2: fail')).toBeVisible();
    expect(screen.getByLabelText('V3: skipped')).toBeVisible();
  });

  it('locks mutations after refresh failure and reconciles mapping and undo on retry', async () => {
    const mock = createMockTransport();
    let failRefresh = true;
    render(
      <App
        api={createApi(async (path, body) => {
          if (path.startsWith('/api/program') && failRefresh) {
            failRefresh = false;
            throw new Error('Program refresh failed');
          }
          return mock(path, body);
        })}
      />,
    );
    await send('set age to 20');
    expect(await screen.findByRole('alert')).toHaveTextContent('Program refresh failed');
    expect(screen.getByRole('textbox', { name: 'English sentence' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Retry connection' }));
    await screen.findByRole('button', { name: 'Line 1: LET age = 20;' });
    await send('print age');
    const line = await screen.findByRole('button', { name: 'Line 2: PRINT age;' });
    fireEvent.focus(line);
    expect(screen.getByTestId('sentence-1')).toHaveClass('is-linked');
    expect(screen.getByTestId('sentence-0')).not.toHaveClass('is-linked');
    failRefresh = true;
    await userEvent.click(screen.getByRole('button', { name: 'Undo last statement' }));
    await screen.findByRole('alert');
    expect(screen.getByRole('textbox', { name: 'English sentence' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Retry connection' }));
    await waitFor(() => expect(screen.queryByTestId('sentence-1')).not.toBeInTheDocument());
    expect(screen.getByRole('textbox', { name: 'English sentence' })).toBeEnabled();
  });
});
