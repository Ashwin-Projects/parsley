import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import App from './App';
import { createApi } from './api/client';
import { createMockTransport } from './mock/api';

it('shows the introduction and navigates between project pages', async () => {
  render(<App api={createApi(createMockTransport())} />);
  expect(screen.getByRole('link', { name: 'Try it' })).toHaveAttribute('href', '#english-input');
  await userEvent.click(screen.getByRole('button', { name: 'How it works' }));
  expect(screen.getByRole('heading', { name: 'How it works' })).toBeVisible();
  expect(screen.getByText(/N1/)).toBeVisible();
  await userEvent.click(screen.getByRole('button', { name: 'About' }));
  expect(screen.getByText(/Ashwin L/)).toBeVisible();
  expect(screen.getByText(/Aditya Kishor/)).toBeVisible();
  expect(screen.getByText(/Maheep Singh/)).toBeVisible();
});

it('shows a budget banner and a non-blocking W515 warning', async () => {
  const api = createApi(createMockTransport());
  api.health = async () => ({ version: '1', llm_configured: true, llm_budget_remaining: false });
  const compile = api.compile;
  api.compile = async (...args) => ({
    ...(await compile(...args)),
    diagnostics: [{ code: 'W515', stage: 'llm', message: 'Using rules only' }],
  });
  render(<App api={api} />);
  expect(await screen.findByText('LLM paused for today, using rules only')).toBeVisible();
  const input = await screen.findByRole('textbox', { name: 'English sentence' });
  await waitFor(() => expect(input).toBeEnabled());
  fireEvent.change(input, { target: { value: 'set age to 20' } });
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(await screen.findByText('W515', { exact: true })).toBeVisible();
});

it('shows a pending sentence while the compiler is working', async () => {
  const api = createApi(createMockTransport());
  api.compile = () => new Promise(() => {});
  render(<App api={api} />);
  const input = await screen.findByRole('textbox', { name: 'English sentence' });
  await waitFor(() => expect(input).toBeEnabled());
  fireEvent.change(input, { target: { value: 'set age to 20' } });
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(await screen.findByText('Compiling: set age to 20')).toBeVisible();
  expect(input).toBeDisabled();
});

it('shows the original sentence while its clarification is being answered', async () => {
  const api = createApi(createMockTransport());
  api.answer = () => new Promise(() => {});
  render(<App api={api} />);
  const input = await screen.findByRole('textbox', { name: 'English sentence' });
  await waitFor(() => expect(input).toBeEnabled());
  fireEvent.change(input, { target: { value: 'set age to 10 or 20' } });
  fireEvent.keyDown(input, { key: 'Enter' });
  await userEvent.click(await screen.findByRole('button', { name: '20' }));
  expect(await screen.findByText('Compiling: set age to 10 or 20')).toBeVisible();
  expect(input).toBeDisabled();
});

it('exports a transcript with the question, answer and reading', async () => {
  const create = vi.fn((blob: Blob) => (blob.size ? 'blob:transcript' : 'blob:empty'));
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: create });
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  const api = createApi(createMockTransport());
  const compile = api.compile;
  api.compile = async (...args) => {
    const result = await compile(...args);
    if (result.status === 'clarify')
      result.diagnostics.push({ code: 'W515', stage: 'llm', message: 'rules only' });
    return result;
  };
  render(<App api={api} />);
  const input = await screen.findByRole('textbox', { name: 'English sentence' });
  await waitFor(() => expect(input).toBeEnabled());
  fireEvent.change(input, { target: { value: 'set age to 10 or 20' } });
  fireEvent.keyDown(input, { key: 'Enter' });
  await userEvent.click(await screen.findByRole('button', { name: '20' }));
  await screen.findByRole('button', { name: 'Line 1: LET age = 20;' });
  await userEvent.click(screen.getByRole('button', { name: 'Download transcript' }));
  const blob = create.mock.calls.at(-1)?.[0] as Blob;
  const text = await new Promise<string>((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.readAsText(blob);
  });
  expect(text).toContain('set age to 10 or 20');
  expect(text).toContain('What value should age have?');
  expect(text).toContain('20');
  expect(text).toContain('LET age = 20;');
  expect(text).toContain('I understood:');
  expect(text).toContain('W515: rules only');
  click.mockRestore();
});
