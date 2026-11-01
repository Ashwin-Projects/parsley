# Parsley frontend implementation plan

Goal: A React/Vite/strict TypeScript workspace matching the supplied API and language examples, isolated in web/ on web-frontend.

Architecture: A typed API client selects fetch or an in-browser mock transport. The mock uses deliberately limited fixtures, never the Python compiler. React owns conversation presentation; GET program owns code and sentence mapping. Plain CSS supplies light/dark themes and a 375px stacked layout.

Design decisions: forest green navigation, warm neutral canvas, a numbered English conversation beside a dark MiniLang editor, examples in a narrow sidebar. Empty sessions begin with guidance, never fabricated accepted statements. Mock and simulated checks are visibly labeled. No publishing or Python changes.

Alternatives: a service worker adds an unnecessary dependency; component-local canned responses would bypass the API contract. Use a transport with session-scoped state instead.

## Steps

- [x] 1. Scaffold configuration, exact API contract, typed client and mock. Write failing mock/client tests; implement fixtures, clarification, undo/reset and run. Verify then commit.
- [x] 2. Write failing component tests; implement conversation, verification badges, questions, suggestion chips, mapped editor, toolbar, output, examples and help. Verify then commit.
- [ ] 3. Write Playwright smoke and accessibility/responsive checks; refine layout, capture desktop/mobile screenshots, document commands and limitations, run lint/build/tests and review. Commit.

Review focus: rejected/clarified inputs never alter the program; undo restores context; invalid clarification answers retain the question; request failures remain visible and recoverable; keyboard and narrow layouts retain every action.

User constraints override skill defaults: use the requested branch in the current checkout, all documentation and test artifacts under web/, no cloud registration, no files under src/ or tests/. No Python changed, so Python review/pytest are inapplicable; review TypeScript correctness, types, errors and formatting instead.

## Progress

Initial state: clean main; branch created from main. No pre-existing web application or frontend-specific installed skills. Use the installed planning/TDD/verification skills and direct ESLint/Playwright tools.

Step 1: three mock contract tests failed on the unimplemented API, then passed. Step 2: four component tests failed on the missing controls, then passed. `npm test`: 2 files, 7 tests passed. `npm run lint`: exit 0. `npm run build`: strict TypeScript and Vite production build passed.

Ruling: another process switched the original shared checkout to llm-hybrid before step 1 committed. Preserve that process's work; use the approved isolated worktree C:/Parsley_web_frontend on web-frontend, created from the original main base and cherry-pick only our frontend commit. No backend changes are included. No files outside web/ changed on this branch.

Ruling: npm 10's optional peer graph resolver crashed (edgesOut); install with --legacy-peer-deps and include @testing-library/dom explicitly. The lockfile is reproducible. Windows sandbox blocks build subprocesses and writes in the isolated worktree; run required checks with approved escalation. Cap Vitest workers at two to avoid overloading this machine.
