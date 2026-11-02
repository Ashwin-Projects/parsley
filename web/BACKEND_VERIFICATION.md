# Backend decisions: verification and changed files

Worktree: `C:\Parsley_web_frontend`; branch: `web-frontend`; starting commit: `0d3ca40`. No Python source, Python tests, existing workflows or root package metadata were changed. Root `docker-compose.yml` is the explicit exception requested alongside the allowed web/, docker/ and new workflow files.

## Commands and observed results

`npm ci --no-audit --no-fund`

```text
added 274 packages in 59s
```

`npm test`

```text
Test Files  4 passed (4)
Tests       24 passed (24)
Duration    21.81s
```

`npm run test:e2e`

```text
Running 16 tests using 2 workers
16 passed (44.4s)
```

The desktop (1440×1000) and mobile (375×812) projects cover the mock compile/answer/run workflow, derived-value Yes and No, inline amber W513 tags, W510–W514 toast and trace, configuration/mode health states, backend down and explicit retry, stalled HTTP deadlines, 429 Retry-After without replay, input length blocking, keyboard help, theme, trace and download. The HTTP adapter tests use local browser route fixtures on port 5174; default mock flows use 5173. No provider or real backend is called.

`npm run lint` and `npm run typecheck` exited 0 without diagnostics.

`npm run build`

```text
> tsc -b && vite build
vite v7.3.7 building client environment for production...
✓ 41 modules transformed.
dist/index.html                   0.67 kB │ gzip:  0.40 kB
dist/assets/index-BS0OJZzI.css   23.74 kB │ gzip:  5.84 kB
dist/assets/index-BY3Rsf3V.js   253.60 kB │ gzip: 79.71 kB
✓ built in 2.96s
```

The live-client build was also checked with `VITE_USE_MOCK=false` and empty `VITE_API_URL`; Docker sets those public build flags explicitly.

`docker compose config --quiet`: exit 0, no output. YAML parsing and assertions verified workflow event paths, required CI commands, read-only permissions, mock environment and Compose service/env-file wiring without printing resolved environment values. Prettier checks of workflow, Compose and Docker README passed.

`docker build --check -f docker/Dockerfile.web .` could not run because Docker Engine's Linux named pipe was absent. Images, nginx runtime and real API proxying were therefore **not** validated. This branch also lacks the Python `web` extra and ASGI app; the API Dockerfile intentionally fails with a clear prerequisite message until the backend supplies them. The assumed `parsley.web.app:app` entry point is configurable. A GitHub-hosted CI run was not performed because no push was authorized.

Host warnings: Playwright reports conflicting NO_COLOR/FORCE_COLOR environment settings; npm reports the existing ESLint 9 version as deprecated. These did not fail checks. No dependency upgrade was introduced in this follow-up.

## TDD and review

The initial eight new cases failed before implementing the health/derived/warning/error behavior. A reviewer then reproduced an uncertain-write recovery defect: the backend can commit before its response times out. Two regression cases (compile and answer) failed before the fix and now pass. Writes remain gated while the saved program can be refreshed and exported; Reset creates a new session to isolate late old-session commits. Missing verification on recovered statements is explicitly unreported. An additional test checks exactly 500 Unicode code points. No mutation is automatically replayed.

Independent review confirmed the final recovery fix and found no remaining important issues. The reviewer independently ran the earlier 21-test suite; the final 24-test result above was run by the primary agent after clean install. No Python was changed, so a Python behavior review was not applicable; TypeScript correctness, types, errors, accessibility, Docker inputs and CI commands were reviewed instead.

Screenshots include the pending clarification and accepted LLM reading: [desktop](screenshots/workspace-desktop.png), [mobile](screenshots/workspace-mobile.png). Both were visually inspected; captures are review artifacts, not pixel assertions.

## Changed files

- `.github/workflows/web.yml`
- `docker-compose.yml`
- `docker/Dockerfile.api`
- `docker/Dockerfile.api.dockerignore`
- `docker/Dockerfile.web`
- `docker/Dockerfile.web.dockerignore`
- `docker/nginx.conf`
- `docker/README.md`
- `web/API_CONTRACT.md`
- `web/BACKEND_PLAN.md`
- `web/BACKEND_VERIFICATION.md`
- `web/README.md`
- `web/VERIFICATION.md`
- `web/e2e/backend-decisions.spec.ts`
- `web/e2e/workspace.spec.ts`
- `web/package.json`
- `web/playwright.config.ts`
- `web/screenshots/workspace-desktop.png`
- `web/screenshots/workspace-mobile.png`
- `web/src/App.tsx`
- `web/src/api/client.test.ts`
- `web/src/api/client.ts`
- `web/src/api/types.ts`
- `web/src/backend-decisions.test.tsx`
- `web/src/backend.css`
- `web/src/components/BackendStatus.tsx`
- `web/src/components/Conversation.tsx`
- `web/src/components/WarningToast.tsx`
- `web/src/diagnostics.ts`
- `web/src/main.tsx`
- `web/src/mock/api.test.ts`
- `web/src/mock/api.ts`
- `web/src/styles.css`
