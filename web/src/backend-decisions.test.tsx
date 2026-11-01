import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import App from './App';
import { createApi } from './api/client';
import { createMockTransport } from './mock/api';

async function send(text: string) {
  const input = screen.getByRole('textbox', { name: 'English sentence' });
  await waitFor(() => expect(input).toBeEnabled());
  fireEvent.change(input, { target: { value: text } });
  fireEvent.keyDown(input, { key: 'Enter' });
}

describe('backend decision UI', () => {
  it('shows configured LLM health, amber W513 reading and a polite warning toast/trace', async () => {
    render(<App api={createApi(createMockTransport())} />);
    await waitFor(() =>
      expect(screen.getByLabelText('Backend status')).toHaveTextContent('LLM configured'),
    );
    await userEvent.selectOptions(screen.getByLabelText('Compiler mode'), 'llm');
    await send('set x to 10');
    const tag = await screen.findByText('via LLM — check the reading');
    expect(tag.closest('.understood')).toHaveTextContent('I understood:');
    expect(tag).toHaveClass('llm-tag');
    expect(tag.closest('.diagnostic-error')).toBeNull();
    const toast = screen.getByRole('status', { name: 'Compiler warnings' });
    expect(toast).toHaveTextContent('W513');
    expect(screen.getByRole('textbox', { name: 'English sentence' })).toBeEnabled();
    expect(screen.getByTestId('trace-content')).toHaveTextContent('W513');
    await userEvent.click(within(toast).getByRole('button', { name: 'Dismiss warnings' }));
    expect(screen.queryByRole('status', { name: 'Compiler warnings' })).not.toBeInTheDocument();
  });

  it('confirms a derived value with Yes and declines it with No without changing program', async () => {
    render(<App api={createApi(createMockTransport())} />);
    await userEvent.selectOptions(screen.getByLabelText('Compiler mode'), 'llm');
    await send('set x to 10');
    await screen.findByRole('button', { name: 'Line 1: LET x = 10;' });
    await send('double x');
    expect(await screen.findByText('Did you mean: multiply x by 2?')).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: 'No' }));
    await waitFor(() =>
      expect(screen.getByRole('textbox', { name: 'English sentence' })).toBeEnabled(),
    );
    expect(screen.queryByRole('button', { name: 'Line 2: x = x * 2;' })).not.toBeInTheDocument();
    await send('double x');
    await userEvent.click(await screen.findByRole('button', { name: 'Yes' }));
    expect(await screen.findByRole('button', { name: 'Line 2: x = x * 2;' })).toBeVisible();
  });

  it('blocks overlength input without truncation or sending it to the API', async () => {
    let compiles = 0;
    const mock = createMockTransport();
    render(
      <App
        api={createApi(async (path, body) => {
          if (path === '/api/compile') compiles++;
          return mock(path, body);
        })}
      />,
    );
    await send('a'.repeat(501));
    expect(screen.getByRole('textbox', { name: 'English sentence' })).toHaveValue('a'.repeat(501));
    expect(screen.getByRole('button', { name: 'Send sentence' })).toBeDisabled();
    expect(screen.getByText('Use 500 characters or fewer.')).toBeVisible();
    expect(compiles).toBe(0);
  });

  it('shows each W510–W514 warning in a non-blocking toast and trace', async () => {
    const mock = createMockTransport();
    render(
      <App
        api={createApi(async (path, body) => {
          const result = await mock(path, body);
          if (path !== '/api/compile') return result;
          return {
            ...(result as object),
            diagnostics: [510, 511, 512, 513, 514].map((code) => ({
              code: `W${code}`,
              stage: 'llm',
              message: `Warning ${code}`,
            })),
          };
        })}
      />,
    );
    await send('print hello');
    const toast = await screen.findByRole('status', { name: 'Compiler warnings' });
    for (const code of [510, 511, 512, 513, 514]) {
      expect(toast).toHaveTextContent(`W${code}`);
      expect(screen.getByTestId('trace-content')).toHaveTextContent(`W${code}`);
    }
    expect(screen.getByRole('textbox', { name: 'English sentence' })).toBeEnabled();
  });
});
