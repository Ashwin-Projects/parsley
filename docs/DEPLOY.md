# Deploying Parsley

The root `Dockerfile` builds the whole site as one service: FastAPI serves the API and the built
frontend on `$PORT`. `docker-compose.yml` stays the two-container setup for local use.

The site spends your model API key, so read [Limits](#limits) first. Every sentence sent in
`hybrid` or `llm` mode, with the variable names in that session, goes to your provider.

## Render (primary)

1. Push the branch named in `render.yaml` (`branch: v2`) to GitHub.
2. In the Render dashboard choose **New > Blueprint**, connect the repository and select it.
3. Render asks for the `sync: false` values. Enter:

   | Name | Value for Groq |
   |---|---|
   | `PARSLEY_LLM_PROVIDER` | `openai` |
   | `PARSLEY_LLM_BASE_URL` | `https://api.groq.com/openai/v1` |
   | `PARSLEY_LLM_MODEL` | `openai/gpt-oss-120b` |
   | `PARSLEY_LLM_API_KEY` | your key |

4. Apply the blueprint, and wait for the first build and for the health check to pass.
5. Open `https://<service>.onrender.com/api/health`. It should show `"llm_configured": true` and
   `"llm_budget_remaining": true`, and it never shows the key.
6. Check that a client cannot fake its address, as the blueprint assumes (see below).

`autoDeploy` is off: choose **Manual Deploy** to release a new commit.

**Check the client address.** The blueprint counts visitors by `CF-Connecting-IP`, which only
protects you if the host overwrites it. This sends 130 requests, each claiming a new address:

```sh
for i in $(seq 1 130); do
  curl -s -o /dev/null -w '%{http_code}\n' -X POST -H "CF-Connecting-IP: 198.51.100.$((i % 250))" \
    https://<service>.onrender.com/api/session
done | sort | uniq -c
```

Some `429`s mean the header is safe. All `200`s mean a client can set it: remove
`PARSLEY_CLIENT_IP_HEADER`, which makes the limit count Render's proxies instead. Visitors may then
share a limit, so raise `PARSLEY_RATE_LIMIT_PER_MINUTE`. The daily cap protects the key either way.

**The free plan sleeps.** After about 15 minutes without traffic the service stops, and the next
visitor waits for it to start, which can outlast the page's 30-second deadline; retrying works.
Sleeping also clears the sessions and every count, **including the daily cap**, so the real ceiling
on spending is the limit at your provider. Set one there.

## Hugging Face Spaces (backup)

1. Create a Space with the **Docker** SDK (blank template).
2. Add these as **Variables** in the Space settings: `PORT=7860` and
   `PARSLEY_FRAME_ANCESTORS=https://huggingface.co`, so the Space page can embed the site.
3. Add the four `PARSLEY_LLM_*` values from the Render table: the key as a **Secret**, the others as
   Secrets or Variables.
4. A Space needs this at the top of its `README.md`. Add it in a commit made only for the Space:

   ```yaml
   ---
   title: Parsley
   sdk: docker
   app_port: 7860
   ---
   ```

5. Push to the Space: `git remote add space https://huggingface.co/spaces/<you>/<space>`, then
   `git push space v2:main`.

Leave `PARSLEY_CLIENT_IP_HEADER` unset unless you have checked a header as above. A free Space also
sleeps, which clears the same counts.

## Limits

All are environment variables, and a malformed value stops the server at start.

| Variable | Default | Effect |
|---|---|---|
| `PARSLEY_RATE_LIMIT_PER_MINUTE` | 20 | Requests a minute per address; above it, no model calls (`W515`) |
| `PARSLEY_HARD_RATE_LIMIT_PER_MINUTE` | 120 | Requests a minute per address; above it, HTTP 429 with `Retry-After` |
| `PARSLEY_LLM_DAILY_CAP` | 500 | Model calls per UTC day across the server; 0 turns the model off (`W515`) |
| `PARSLEY_LLM_SESSION_CAP` | 50 | Model calls per session (`W515`) |
| `PARSLEY_MAX_SESSIONS` | 1000 | Sessions in memory; the least recently used makes room |
| `PARSLEY_SESSION_TTL` | 3600 | Seconds before an unused session is dropped |
| `PARSLEY_ALLOWED_ORIGINS` | the Vite dev server | Comma-separated origins for CORS. The one-service site is same-origin and needs none |
| `PARSLEY_CLIENT_IP_HEADER` | unset (socket address) | A header your host sets itself; its last entry is the client |
| `PARSLEY_FRAME_ANCESTORS` | `'none'` | Who may embed the site |
| `PARSLEY_WEB_DIST` | unset (`/app/web/dist` in the image) | The built frontend to serve |

`W515` keeps the rule result and the request succeeds. `/api/compile`, `/api/answer`, `/api/session`
and `/api/run` count towards the two rates. `/api/health` says whether model budget remains, never how
much. Bodies over 8 KiB get 413, and sentences over 500 characters get 422.

Counts are held in memory, so run one process: more workers would each have their own.

## Before you go public

- Set a spending or usage limit at your provider. Nothing here can see what the key spends elsewhere.
- Use a key made only for this site, so it can be revoked without touching anything else.
- Tell visitors that `hybrid` and `llm` sentences go to a third party.

If the key leaks, revoke it at the provider, then set the new value in the host's settings and
redeploy. A leaked key stays usable until it is revoked, and removing it from a file does not help.
