# Docker deployment

The frontend image builds Vite with Node 22 and serves the result with nginx. The
API image installs the Python package with its optional `web` dependencies and
runs uvicorn. Docker Engine with Linux containers and Docker Compose 2.24.0 or
newer are required (`env_file.required` permits running without a root `.env`).

## Backend prerequisite

**This frontend branch currently has no `web` extra in `pyproject.toml` and no
ASGI backend.** The full stack is an integration scaffold until the backend
branch supplies both. No Python modules or dependencies are added by this Docker
setup. The API build deliberately reports the missing `web` extra instead of
producing an image that silently installed only the core package.

The backend must provide a `web` extra including uvicorn, an ASGI app implementing
[the API contract](../web/API_CONTRACT.md), and its runtime LLM configuration.
`parsley.web.app:app` is the assumed entry point; set `PARSLEY_ASGI_APP` in the root
`.env` if the backend uses another import path. The application must listen at
`/api/...`; nginx preserves that prefix and the query string. The API health check
requests the contract's `GET /api/health` route and fails on HTTP errors.

## Run

Run these commands from the repository root, after the backend is integrated:

```sh
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

Open <http://localhost:8080>. Set `PARSLEY_WEB_PORT` in the root `.env` to change
the host port. The frontend is published only on loopback; the API is reachable
through nginx on the Compose network and has no host port. nginx resolves `api`
through Docker DNS on requests, so static pages can start while the API is absent
and later API replacement does not require an nginx restart.

Until the backend is available, run the frontend alone:

```sh
docker compose up --build -d web
```

The page loads and API requests return a gateway error. The Docker build uses
the live API client, so a working compiler session requires the backend. For a
canned demo without a backend, use the [local frontend workflow](../web/README.md).
A healthy web container confirms static serving, not API availability.

```sh
docker compose logs --tail=100 web api
docker compose down
```

## Runtime configuration and build inputs

Place backend provider keys, model names and endpoint settings in the repository
root `.env`, using the variable names supported by the backend. Compose passes
that file to **only the API container at runtime**. This branch does not define
backend LLM setting names. The file is optional for offline/rules operation; any
LLM mode still requires the backend's configuration. Recreate the API container
after changing runtime settings (`docker compose up -d --force-recreate api`).

The frontend build sets the public switches `VITE_USE_MOCK=false` and an empty
`VITE_API_URL` so it uses same-origin `/api` requests. There are no provider settings,
credentials or `.env` files in its build. Each Dockerfile has its own allowlist
`.dockerignore`, so the repository `.env`, `web/.env`, Git metadata, `node_modules`
and unrelated files are excluded from both build contexts. Only package/source
inputs needed for each image are copied. Do not put credentials in source files
or public assets; allowlists cannot identify secrets embedded in ordinary code.

Use `docker compose config --quiet` to validate configuration without printing
resolved environment values. `docker compose config` without `--quiet` can show
the API's credentials.

## Validation limits

Compose configuration can be validated without a running Docker Engine. Building
images, checking nginx syntax inside its image, confirming static serving and
exercising API proxying require an engine. A complete API smoke test additionally
requires the backend prerequisite above. These checks cannot be replaced by a
successful frontend build or a successful Compose parse.

References: [Docker build contexts and ignore files](https://docs.docker.com/build/concepts/context/),
[Compose env files](https://docs.docker.com/reference/compose-file/services/#env_file),
[nginx proxy_pass](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass).
