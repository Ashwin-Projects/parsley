# Backend decisions frontend plan

Spec: the user's backend-decision follow-up. Continue in the existing web-frontend worktree. All edits stay under web/, new docker/ files, the new web workflow, and the explicitly requested root docker-compose.yml.

Design: retain the workspace; render derived-value confirmation with Yes/No, LLM readings with an inline amber W513 tag, warnings W510–W514 as polite dismissible toasts and trace diagnostics. Fetch health independently of session creation. The supplied health response has no mode field, so display the requested compile mode honestly unless an optional backend mode is supplied. Add bounded fetch errors and enforce the full 500-character input limit without silently truncating pasted text.

1. Write failing mock, HTTP, component and browser tests for these cases. Implement the contract/client/mock/UI, verify, commit frontend behavior.
2. Run the complete Vitest and Playwright coverage, review desktop/mobile clarification and LLM screenshots, commit final test evidence and screenshots.
3. Add Dockerfiles, nginx proxy, Dockerfile-specific allowlist ignore files and Compose runtime env wiring. Document the backend prerequisite; verify available container/config checks and commit.
4. Add path-filtered GitHub Actions for clean install, lint, explicit typecheck, tests, build and mock Playwright. Validate it, run final checks and commit.

Review focus: No must not append a statement; W513 never uses error styling; health failure does not erase session history; mutation timeouts must not automatically replay writes; 500 characters means Unicode code points, matching Python; no .env or credentials enter image contexts or frontend bundles; Compose must preserve /api paths; CI must force mock mode.

Repository finding: this branch's pyproject.toml currently has no web extra or ASGI module. Do not edit the Python project or import another branch. The API Dockerfile targets the backend web extra and configurable ASGI app, and the docs must clearly identify this prerequisite if still absent at validation time.

Progress: baseline clean at 0d3ca40. User explicitly opted out of further approval/design questions; proceed through all steps.

Verified deliverables: frontend behavior committed as 1dda781; clean npm ci, 24 Vitest cases and 16 desktop/mobile Playwright cases passed; lint, explicit typecheck and build passed. Independent review confirmed the uncertain-write recovery fix after failing compile/answer regressions. Docker Compose and workflow syntax/command wiring validate; image execution is unavailable because Docker Engine is stopped and the backend web extra/app are absent. Exact output and the file inventory are in BACKEND_VERIFICATION.md. Keep all commits local.
