# Parsley web playground

React + Vite + strict TypeScript, plain CSS. All frontend code, tests and artifacts live under `web/`; the Python compiler is untouched.

## Quick start with Docker

From the repository root, run `docker compose up --build`, then open <http://localhost:8080>. The real API runs behind nginx. Live demo: **link coming soon**.

For LLM modes, copy the root `.env.example` to `.env` and set `PARSLEY_LLM_PROVIDER`, the model and its API key. For Groq use `PARSLEY_LLM_PROVIDER=openai`, `PARSLEY_LLM_BASE_URL=https://api.groq.com/openai/v1`, `PARSLEY_LLM_MODEL=<model>`, and `PARSLEY_LLM_API_KEY=<key>`. Restart the API container after changes. The root `.env` is supplied at runtime; do not place credentials in `VITE_*` variables.

## Run without Docker

In one terminal at the repository root, run `pip install -e ".[web]"` and `python -m parsley.web --port 8000`. In another terminal run `cd web`, `npm ci`, and `npm run dev`. Set `VITE_USE_MOCK=false` and `VITE_API_URL=http://localhost:8000` in `web/.env.local` before starting Vite, then open <http://127.0.0.1:5173>. The default is the browser mock; it simulates compiler results and LLM readings.

The workspace offers separate downloads for the MiniLang program and the session transcript. The transcript includes English, readings, code, clarification exchanges and diagnostics. Sessions are held in memory and are reset on refresh.

## New screenshots

| View                                     | Desktop                                          | Mobile                                          |
| ---------------------------------------- | ------------------------------------------------ | ----------------------------------------------- |
| Home                                     | [Home](screenshots/home-desktop.png)             | [Home](screenshots/home-mobile.png)             |
| Workspace with clarification and LLM tag | [Workspace](screenshots/workspace-desktop.png)   | [Workspace](screenshots/workspace-mobile.png)   |
| How it works                             | [Pipeline](screenshots/how-it-works-desktop.png) | [Pipeline](screenshots/how-it-works-mobile.png) |

These screenshots use the deterministic mock. The Playwright axe test checks home, workspace, How it works and About for serious or critical violations at both viewport sizes.

## Run locally

Requires Node.js 22.12+ and npm. In this checkout:

```powershell
cd web
npm ci
npm run dev
```

Open http://127.0.0.1:5173. A fresh checkout defaults to the in-browser mock. The application uses local fonts and SVG icons and needs no external service after installing dependencies.

```sh
npm run build       # strict TypeScript, then production build in dist/
npm run preview     # serve the production build at http://127.0.0.1:4173
npm run lint        # ESLint, zero warnings allowed
npm run typecheck   # strict TypeScript without emitting files
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

The compile contract and health route are documented in [API_CONTRACT.md](API_CONTRACT.md). The client uses POST JSON for mutations and GET for health and program queries. Switching transports does not change components. Sessions are created on page load; refreshing starts a new session. Browser tests can also run against the real backend.

The health pill reports LLM configuration, with version/provider/model in its tooltip. The required health response has no mode field: the pill honestly labels the selected compile mode as **Requested**. If the backend supplies the optional `mode` extension, it shows **Backend** mode instead. Mock health identifies the simulated provider and model.

Accepted LLM readings carry an inline amber **via LLM — check the reading** tag next to V1. W510–W515 diagnostics appear in trace and a polite, dismissible toast that closes after ten seconds; warnings never block input or use error styling. When health reports no remaining LLM budget, a banner says the model is paused and rules are used. For `derived_value` questions the controls are always Yes and No, even if the backend omits option labels. In the mock, select LLM or Hybrid, send `set x to 10`, then `double x`: **Did you mean: multiply x by 2?** Yes appends the multiplication; No leaves the program unchanged. No real LLM or compiler verification runs in mock mode.

HTTP requests have a 30-second deadline. Backend-down and gateway errors give connection guidance; 429 responses show `Retry-After` seconds or date guidance without automatic resubmission. Overlength input stays editable and is blocked before any API call; the 500-character limit counts Unicode code points, matching Python.

If a mutation times out or loses its response, the server may already have committed it. Editing stays disabled. **Retry connection** reloads the saved program for inspection and export, with unavailable verification explicitly unreported. **Reset** then starts a fresh session, so a delayed response from the old session cannot affect new work. The contract cannot recover an unreturned pending question or verification report. A definite rate-limit response remains retryable normally.

## Try it

1. Send `make a variable called age and set it to 20`.
2. Send `add 5 to it`, then `print age`; Run shows `25` and the final variable `age`.
3. Send `set age to 10 or 20`; choose a value to resolve the question.
4. Send `increase age`; enter the missing amount in the clarification box.
5. Send `store 50 in bonus`; click **Try: set bonus to 50** to fill the composer.

The eight sidebar examples come from `LANGUAGE_SPEC.md` sections 4 and 6. Variable-dependent examples need a prior declaration; “it” refers to the last variable. The demo implements a limited fixture vocabulary: numeric/quoted-string creation and assignment, numeric increase/decrease/multiply/divide, print/show/display, numeric `set … or …` alternatives, `increase …` missing amounts, the exact sidebar IF and REPEAT examples, and the `store … in …` rewrite. It is not a second compiler. Unknown phrasing is rejected with a supported suggestion. LLM mode simulates `source: llm` and W513; Hybrid also simulates the derived `double x` fallback. No Python, LLM, paid API or real V1/V2/V3 verification runs in mock mode. Trace and the page footer identify simulated verification.

## Interaction and accessibility

- Enter sends; Shift+Enter adds a line break; Up recalls the last sentence when the composer is empty. IME composition does not accidentally send.
- Clarification blocks new input until resolved or cleared with Undo/Reset. Invalid answers keep the question open.
- Hover or keyboard-focus a code line to highlight its source sentence, including repeated identical sentences and multiline statements.
- Checks show symbols and accessible state labels alongside green/red/grey colors. Missing backend checks display as not reported.
- Help uses a native modal dialog, focus containment, Escape to close, and focus restoration. A skip link goes to the English input.
- Theme choice persists locally. Reduced motion is respected. Mobile stacks conversation above the program and makes examples horizontally scrollable.
- Accepted changes invalidate previous run results. Requests lock conflicting actions; network errors are visible with a connection retry. Undo removes the last accepted statement, and Reset clears the session.

## Screenshots

Playwright regenerates [desktop](screenshots/workspace-desktop.png) and [mobile](screenshots/workspace-mobile.png) screenshots showing an accepted LLM-tagged reading alongside a pending clarification. These are review artifacts, not pixel snapshot assertions. Tests run a mock Vite server on port 5173 and a real-HTTP-adapter Vite server on port 5174; browser route fixtures supply the latter's API, so no Python backend or provider keys are needed.

## Docker

From the repository root:

```sh
docker compose config --quiet
docker compose up --build -d
```

Open http://localhost:8080. The multi-stage `docker/Dockerfile.web` builds with Node 22 and `VITE_USE_MOCK=false`, serves static assets with nginx, and proxies same-origin `/api` requests to the `api` service. `docker/Dockerfile.api` installs `.[web]` in Python slim and runs uvicorn. Both builds use explicit allowlist contexts that exclude `.env`, credentials, Git metadata and node_modules. Root `.env` is passed only to the API container at runtime; provider settings never enter frontend bundles or build arguments. Set `PARSLEY_WEB_PORT` there to change the loopback port and `PARSLEY_ASGI_APP` for a different app import path.

The API comes from `src/parsley/web/`, and Docker Engine must be running. See [docker/README.md](../docker/README.md) for setup and validation limits.

## GitHub Actions

`.github/workflows/web.yml` runs on pushes and pull requests affecting `web/**` or the workflow itself. It uses Node 22, runs `npm ci`, lint, explicit typecheck, unit tests and build, installs Chromium with Linux dependencies, then runs mock and browser-fixture Playwright checks. Reports and failure artifacts are uploaded for review. The job has read-only repository permissions and needs no backend or provider secrets. A GitHub-hosted run requires pushing; no push is part of this delivery.

## Implementation map

| Files                                                                                           | Responsibility                                                        |
| ----------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `src/App.tsx`                                                                                   | Session lifecycle, requests, toolbar, composer and layout             |
| `src/components/Conversation.tsx`                                                               | History, clarification and suggestion controls                        |
| `src/components/VerificationBadges.tsx`                                                         | Accessible verification states                                        |
| `src/components/ProgramPanel.tsx`                                                               | Highlighted code, source mapping and run results                      |
| `src/components/HelpDialog.tsx`, `Icon.tsx`                                                     | Help and local SVG icons                                              |
| `src/api/types.ts`, `client.ts`                                                                 | API types and fetch transport                                         |
| `src/components/BackendStatus.tsx`, `WarningToast.tsx`, `src/diagnostics.ts`, `src/backend.css` | Backend health and amber warning presentation                         |
| `src/backend-decisions.test.tsx`, `e2e/backend-decisions.spec.ts`                               | Backend decisions and network recovery regressions                    |
| `src/mock/api.ts`                                                                               | Session-scoped browser mock                                           |
| `src/examples.ts`, `src/styles.css`, `src/main.tsx`                                             | Examples, themes/responsive styles and entry point                    |
| `src/App.test.tsx`, `src/api/client.test.ts`, `src/mock/api.test.ts`, `src/test/setup.ts`       | Component, HTTP and mock tests                                        |
| `e2e/workspace.spec.ts`, `playwright.config.ts`                                                 | Browser smoke tests and screenshots                                   |
| `package.json`, `package-lock.json`, `.npmrc`                                                   | Dependencies, scripts and deterministic install                       |
| `index.html`, `public/parsley.svg`                                                              | HTML shell and favicon                                                |
| `tsconfig.json`, `vite.config.ts`, `eslint.config.js`                                           | TypeScript, bundler, unit tests and lint configuration                |
| `.prettierrc.json`, `.prettierignore`, `.gitignore`, `.env.example`                             | Formatting, generated-file exclusions and public environment template |
| `API_CONTRACT.md`, `PLAN.md`, `README.md`, `VERIFICATION.md`                                    | Contract, implementation record, usage and verification evidence      |
| `BACKEND_PLAN.md`, `BACKEND_VERIFICATION.md`                                                    | Follow-up plan, exact results and changed-file list                   |
| `../docker/`, `../docker-compose.yml`, `../.github/workflows/web.yml`                           | Containers, runtime configuration and CI                              |

Historical frontend integration notes are in [BACKEND_VERIFICATION.md](BACKEND_VERIFICATION.md).

## Browser tests against the real API

```sh
pip install -e "..[web]"
npx playwright test -c playwright.real.config.ts
```

This starts `python -m parsley.web` and the Vite dev server with `VITE_USE_MOCK=false`, and the API replays the hand-written `tests/fixtures_llm/e2e.json` with no network. The specs under `HTTP transport with browser-local API fixtures` still stub the API in the browser, because they need failures the real API does not produce on demand. `*.real.spec.ts` runs only in this configuration.
