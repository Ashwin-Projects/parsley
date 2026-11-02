# Real-backend web polish implementation plan

**Goal:** Run the real compiler through Docker and deliver an accessible, documented playground.
**Architecture:** Retain React, plain CSS and the existing API adapter. Add lightweight URL navigation without a routing dependency; keep the workspace mounted across pages. Provider configuration belongs only in the root `.env`, injected into the API at runtime.
**Scope:** `web/`, `docker/`, `docker-compose.yml`, `.github/workflows/web.yml`, `docs/`, plus root `README.md` explicitly requested in step 3. Work in the existing clean `v2` checkout; no worktree, push, merge, rebase or reset.

## Design decisions

Extend the current restrained green playground instead of introducing a separate marketing app or framework. The home pitch and three steps lead directly into the working compiler. How it works uses a semantic HTML pipeline diagram; About identifies the team, VIT and source repository. Navigation preserves the current session. Export offers two explicit downloads, avoiding browser restrictions on multiple automatic downloads.

Targets: 1440x1000 desktop and 375x812 mobile, both themes, keyboard access and reduced motion. Empty states suggest a supported first sentence; a pending sentence stays visible with a progress indicator; connection errors retain the existing recovery flow. Recovered verification stays unreported. No permissions are requested by the product.

## Step 1 — Docker and runtime secrets

- [ ] Build and run `docker compose up --build -d`; inspect failures before changing configuration.
- [ ] Test the image audit against synthetic clean/leaking layers before implementing it.
- [ ] Verify static serving, proxied health, compile, clarification, program query and execution.
- [ ] Audit image configuration, untruncated history and every saved filesystem layer against runtime key values, without printing secrets.
- [ ] Review Python correctness, types, errors and PEP 8; record exact verification and commit step 1.

## Step 2 — Website and accessibility

- [ ] Add failing component tests for navigation/session persistence, sentence progress and transcript export.
- [ ] Add home introduction, How it works and About with existing design tokens.
- [ ] Add per-sentence progress and `.txt` transcript alongside `.ml` export.
- [ ] Add Docker Playwright coverage for real compilation, export, navigation, responsive layout and accessibility.
- [ ] Run existing unit/browser suites, lint, typecheck, build, and Lighthouse accessibility/best-practices (minimum 90).
- [ ] Rebuild the Docker web image; capture real-backend desktop/mobile screenshots and commit step 2.

## Step 3 — Documentation

- [ ] Update web/root READMEs: one-command Docker start, local API/frontend, runtime LLM configuration, screenshots.
- [ ] Record exact commands/results, changed paths, image audit and accessibility limits.
- [ ] Check links and diff; commit step 3 without pushing.

## Review focus

Protect pending sessions while navigating; preserve source/answer history in exports; do not invent missing verification; keep credentials out of build arguments/bundles/artifacts; check mobile overflow and both-theme contrast.

## Execution ledger

Initial state: `v2` at `9f50619`, clean working tree, no upstream configured for this branch. Existing local state is used; no remote integration operation is performed because repository instructions prohibit merges/rebases. Docker Engine 29.8.2 is running. Initial Compose images build successfully. Runtime and image audit still pending.

Ruling: use the user's detailed task as the implementation brief and proceed with routine design choices; execute inline in the requested checkout.
