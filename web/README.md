# Parsley web playground

React + Vite + strict TypeScript, plain CSS. All frontend code, tests and artifacts live under `web/`; the Python compiler is untouched.

## Run locally

Requires Node.js 22.12+ and npm. In this checkout:

```powershell
cd C:\Parsley_web_frontend\web
npm ci
npm run dev
```

Open http://127.0.0.1:5173. A fresh checkout defaults to the in-browser mock. The application uses local fonts and SVG icons and needs no external service after installing dependencies.

```sh
npm run build       # strict TypeScript, then production build in dist/
npm run preview     # serve the production build at http://127.0.0.1:4173
npm run lint        # ESLint, zero warnings allowed
npm run format:check # consistent source and CSS formatting
npm test            # Vitest mock, HTTP adapter and component tests
npx playwright install chromium
npm run test:e2e    # Chromium desktop and 375px mobile smoke tests
```

The npm lockfile and `.npmrc` keep installs reproducible; legacy peer resolution avoids an npm 10 optional-peer graph resolver crash. Only React/ReactDOM are runtime packages; test, build and formatting tools are development dependencies.

## Backend connection

Copy `.env.example` to `.env.local`, then restart Vite:

```dotenv
VITE_USE_MOCK=false
VITE_API_URL=http://localhost:8000
```

Set `VITE_USE_MOCK=true` for the demo. An absent setting also selects the mock. `VITE_API_URL` is the backend origin, without `/api`; leave it empty to use the frontend origin. A backend on a different origin must allow this frontend origin through CORS. These are public build settings; do not put secrets in them.

The contract is reproduced verbatim in [API_CONTRACT.md](API_CONTRACT.md). The client uses POST JSON for mutations and GET for the program query. Switching transports does not change components. Sessions are created on page load; refreshing starts a new session. The HTTP adapter is tested with a stubbed fetch; a live backend is not part of this delivery.

## Try it

1. Send `make a variable called age and set it to 20`.
2. Send `add 5 to it`, then `print age`; Run shows `25` and the final variable `age`.
3. Send `set age to 10 or 20`; choose a value to resolve the question.
4. Send `increase age`; enter the missing amount in the clarification box.
5. Send `store 50 in bonus`; click **Try: set bonus to 50** to fill the composer.

The eight sidebar examples come from `LANGUAGE_SPEC.md` sections 4 and 6. Variable-dependent examples need a prior declaration; “it” refers to the last variable. The demo implements a limited fixture vocabulary: numeric/quoted-string creation and assignment, numeric increase/decrease/multiply/divide, print/show/display, numeric `set … or …` alternatives, `increase …` missing amounts, the exact sidebar IF and REPEAT examples, and the `store … in …` rewrite. It is not a second compiler. Unknown phrasing is rejected with a supported suggestion. No Python, LLM, paid API or real V1/V2/V3 verification runs in mock mode. All mock modes use the same fixtures; LLM mode simulates `source: llm`. Trace and the page footer identify simulated verification.

## Interaction and accessibility

- Enter sends; Shift+Enter adds a line break; Up recalls the last sentence when the composer is empty. IME composition does not accidentally send.
- Clarification blocks new input until resolved or cleared with Undo/Reset. Invalid answers keep the question open.
- Hover or keyboard-focus a code line to highlight its source sentence, including repeated identical sentences and multiline statements.
- Checks show symbols and accessible state labels alongside green/red/grey colors. Missing backend checks display as not reported.
- Help uses a native modal dialog, focus containment, Escape to close, and focus restoration. A skip link goes to the English input.
- Theme choice persists locally. Reduced motion is respected. Mobile stacks conversation above the program and makes examples horizontally scrollable.
- Accepted changes invalidate previous run results. Requests lock conflicting actions; network errors are visible with a connection retry. Undo removes the last accepted statement, and Reset clears the session.

## Screenshots

Playwright regenerates [desktop](screenshots/workspace-desktop.png) and [mobile](screenshots/workspace-mobile.png) screenshots from a compiled, clarified and executed session. These are review artifacts, not pixel snapshot assertions.

## Implementation map

| Files                                                                                     | Responsibility                                                        |
| ----------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `src/App.tsx`                                                                             | Session lifecycle, requests, toolbar, composer and layout             |
| `src/components/Conversation.tsx`                                                         | History, clarification and suggestion controls                        |
| `src/components/VerificationBadges.tsx`                                                   | Accessible verification states                                        |
| `src/components/ProgramPanel.tsx`                                                         | Highlighted code, source mapping and run results                      |
| `src/components/HelpDialog.tsx`, `Icon.tsx`                                               | Help and local SVG icons                                              |
| `src/api/types.ts`, `client.ts`                                                           | API types and fetch transport                                         |
| `src/mock/api.ts`                                                                         | Session-scoped browser mock                                           |
| `src/examples.ts`, `src/styles.css`, `src/main.tsx`                                       | Examples, themes/responsive styles and entry point                    |
| `src/App.test.tsx`, `src/api/client.test.ts`, `src/mock/api.test.ts`, `src/test/setup.ts` | Component, HTTP and mock tests                                        |
| `e2e/workspace.spec.ts`, `playwright.config.ts`                                           | Browser smoke tests and screenshots                                   |
| `package.json`, `package-lock.json`, `.npmrc`                                             | Dependencies, scripts and deterministic install                       |
| `index.html`, `public/parsley.svg`                                                        | HTML shell and favicon                                                |
| `tsconfig.json`, `vite.config.ts`, `eslint.config.js`                                     | TypeScript, bundler, unit tests and lint configuration                |
| `.prettierrc.json`, `.prettierignore`, `.gitignore`, `.env.example`                       | Formatting, generated-file exclusions and public environment template |
| `API_CONTRACT.md`, `PLAN.md`, `README.md`, `VERIFICATION.md`                              | Contract, implementation record, usage and verification evidence      |

The requested branch is `web-frontend`, based on `main` at `b7ed07c`. A concurrent process changed the original checkout's branch, so development continued in the separate worktree `C:\Parsley_web_frontend`. No push, merge, rebase or reset was performed. The final branch diff contains only `web/` additions.
