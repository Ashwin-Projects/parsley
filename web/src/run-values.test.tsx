import { render, screen, within } from '@testing-library/react';
import { expect, it } from 'vitest';
import { ProgramPanel } from './components/ProgramPanel';
import { Conversation, type Message } from './components/Conversation';
import { finalValue, hasPrint } from './run-values';

const program = {
  minilang: 'LET t = 3 + 5;\nt = t + 1;',
  statements: [
    { english: 'set t to 3 plus 5', minilang: 'LET t = 3 + 5;' },
    { english: 'add 1 to t', minilang: 't = t + 1;' },
  ],
};
const messages: Message[] = program.statements.map((statement, index) => ({
  id: index,
  english: statement.english,
  statementIndex: index,
  result: { status: 'accepted', minilang: statement.minilang, diagnostics: [] },
}));
const result = { output: [], variables: { t: 9 } };

it('recognizes a direct PRINT of a variable without mistaking string contents for code', () => {
  expect(finalValue('PRINT t;', result)).toBe('t = 9');
  expect(finalValue('PRINT "t";', result)).toBeNull();
  expect(hasPrint('LET note = "PRINT t";')).toBe(false);
});

it('shows final values for both accepted statements and code lines without changing source', () => {
  render(
    <>
      <Conversation
        messages={messages}
        linked={null}
        busy={false}
        onAnswer={() => {}}
        onInsert={() => {}}
        output={result}
      />
      <ProgramPanel
        program={program}
        output={result}
        linked={null}
        onLink={() => {}}
        onCopy={() => {}}
        onDownload={() => {}}
        busy={false}
      />
    </>,
  );
  expect(within(screen.getByTestId('sentence-0')).getByText('Final value: t = 9')).toBeVisible();
  expect(within(screen.getByTestId('sentence-1')).getByText('Final value: t = 9')).toBeVisible();
  expect(screen.getAllByText('// t = 9')).toHaveLength(2);
  expect(screen.getByText(/This program prints nothing/)).toHaveTextContent(
    "Tip: type 'print t' to add output.",
  );
  expect(program.minilang).toBe('LET t = 3 + 5;\nt = t + 1;');
});

it('does not present partial variables as final on runtime errors', () => {
  render(
    <ProgramPanel
      program={program}
      output={{ ...result, error: 'division by zero' }}
      linked={null}
      onLink={() => {}}
      onCopy={() => {}}
      onDownload={() => {}}
      busy={false}
    />,
  );
  expect(screen.queryByText('// t = 9')).not.toBeInTheDocument();
  expect(screen.queryByText(/This program prints nothing/)).not.toBeInTheDocument();
});

it('does not suggest adding print when a PRINT statement exists', () => {
  const printing = {
    minilang: 'PRINT "PRINT";',
    statements: [{ english: 'print', minilang: 'PRINT "PRINT";' }],
  };
  render(
    <ProgramPanel
      program={printing}
      output={{ output: ['PRINT'], variables: {} }}
      linked={null}
      onLink={() => {}}
      onCopy={() => {}}
      onDownload={() => {}}
      busy={false}
    />,
  );
  expect(screen.queryByText(/This program prints nothing/)).not.toBeInTheDocument();
});
