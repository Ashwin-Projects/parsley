# Frontend verification

For the backend-decisions follow-up, see [BACKEND_VERIFICATION.md](BACKEND_VERIFICATION.md). The results below record the initial frontend delivery.

Run from `C:\Parsley_web_frontend\web` on `web-frontend`, 2026-11-01, Node v22.17.0 / npm 10.9.2.

## Final commands and output

`npm test`

```text
Test Files  3 passed (3)
Tests       13 passed (13)
Duration    12.90s
```

`npm run lint`

```text
> eslint . --max-warnings 0
[exit 0, no warnings or errors]
```

`npm run build`

```text
> tsc -b && vite build
vite v7.3.7 building client environment for production...
✓ 37 modules transformed.
dist/index.html                   0.67 kB │ gzip:  0.40 kB
dist/assets/index-gkQ6ZLxe.css   21.91 kB │ gzip:  5.43 kB
dist/assets/index-B5hNb6qV.js   249.69 kB │ gzip: 78.41 kB
✓ built in 2.71s
```

`npm run test:e2e`

```text
Running 4 tests using 2 workers
✓ [desktop] keyboard help, theme, trace and program download
✓ [desktop] compile, clarify and run a mock session
✓ [mobile] keyboard help, theme, trace and program download
✓ [mobile] compile, clarify and run a mock session
4 passed (13.4s)
```

Chromium viewports: desktop 1440×1000; mobile 375×812. Smoke tests assert compilation, question answering, generated code, run output and variables, no uncaught browser exceptions, and no horizontal page overflow. The second flow checks help/Escape, dark theme, trace and download filename. Both final screenshots were visually inspected.

`npm run format:check`: **All matched files use Prettier code style!** (exit 0). `git diff --check`: exit 0. `git diff main --name-only -- src tests`: no output. The approved `npx playwright install chromium` check also completed with exit 0.

Playwright prints environment warnings because both `NO_COLOR` and `FORCE_COLOR` are set by the host. These are not application warnings. Chromium was already installed; the first sandboxed install attempt could not write its cache lock. Required Windows subprocess checks were run with approved escalation.

## Review and regressions

An independent reviewer found three issues, each reproduced in a failing test before fixing:

1. A literal option `2` was mistaken for the second option. Literal values now take precedence over index answers.
2. A resolved question returning a semantic rejection retained stale mock pending state. The pending question is consumed before recompiling the resolved answer.
3. A program refresh failure following a successful mutation allowed the next mutation to reuse an old source index. The workspace now locks mutations until Retry refreshes the authoritative program and reconciles history. The regression covers both compile recovery and undo recovery.

The reviewer rechecked all fixes and independently ran `npm test -- src/App.test.tsx src/mock/api.test.ts`: **2 files passed; 11 tests passed**. No remaining concrete important issues were found in the fixes. TypeScript correctness, error handling, types, accessibility and formatting were reviewed; no Python was changed, so Python tests/review were not applicable.

## Scope and practical limits

- The branch is based on `main` at `b7ed07c`. All branch additions are under `web/`; `src/` and `tests/` are unchanged.
- The API contract is unchanged from the supplied text. HTTP payload/query and failure behavior are unit-tested; no live backend was available.
- The mock implements documented demo fixtures, not the full compiler. All three verification results and LLM provenance are explicitly simulated in mock mode.
- Refreshing creates a fresh session; only the theme persists locally. No deployment or push was performed.

Screenshots: [desktop](screenshots/workspace-desktop.png), [mobile](screenshots/workspace-mobile.png).
