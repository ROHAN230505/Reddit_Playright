# Playwright Posting Worker

This worker takes APPROVED drafts from the backend and posts the exact text
to the exact Reddit target via a logged-in Playwright browser session. The
backend remains the source of truth — this worker only acts on what it is
told.

## How it works

1. The worker calls `POST /worker/claim` to atomically claim the next
   APPROVED draft.
2. The worker opens the target URL in a persistent Chrome / Chromium
   profile that is already signed in to Reddit.
3. The worker fills the exact draft text and submits.
4. On success: `POST /worker/<id>/posted`.
5. On failure: `POST /worker/<id>/failed` with the error; by default the
   draft is requeued so it can be retried.

## Local setup

```bash
# 1. From repo root, create a venv (recommended)
python -m venv .venv
. .venv/bin/activate          # macOS/Linux
# or:  .venv\Scripts\Activate.ps1   on Windows PowerShell

# 2. Install the worker's dependencies
pip install -r playwright_worker/requirements.txt

# 3. Install the Playwright browser binaries (one-off)
python -m playwright install chromium
# Optional: also install Google Chrome channel
python -m playwright install chrome
```

## One-time Reddit login

The worker uses a *dedicated* persistent profile directory (default:
`~/.reddit-worker-profile`) so it does not fight your everyday Chrome
profile lock. Sign in to Reddit once with:

```bash
python -m playwright_worker login
```

A browser window opens. Log in as the Reddit account you want the worker
to post from, then return to the terminal and press Enter. The session
cookies are saved to the profile directory and reused by every subsequent
worker run.

## Run a single job (test mode)

```bash
# In one terminal, make sure the backend is running:
docker compose up backend db redis

# Approve a draft from the dashboard so it has status APPROVED.

# In another terminal:
BACKEND_BASE_URL=http://localhost:8000 \
python -m playwright_worker run --once
```

The worker claims one job, posts it, and exits. Inspect the dashboard to
verify the draft now shows status POSTED.

## Run the continuous loop

```bash
BACKEND_BASE_URL=http://localhost:8000 \
PLAYWRIGHT_WORKER_NAME=playwright-local \
POLL_INTERVAL_SECONDS=20 \
python -m playwright_worker run
```

Press Ctrl-C to stop.

## Configuration

All settings are environment variables.

| Variable | Default | Purpose |
|---|---|---|
| `BACKEND_BASE_URL` | `http://localhost:8000` | Where the FastAPI backend lives. |
| `PLAYWRIGHT_WORKER_NAME` | `playwright-local` | Identifier the backend stores when this worker claims a job. |
| `POLL_INTERVAL_SECONDS` | `20` | Idle sleep between empty queue checks (continuous mode). |
| `CLAIM_STALE_AFTER_SECONDS` | `600` | A POSTING claim older than this can be re-claimed by another worker. |
| `USER_DATA_DIR` | `~/.reddit-worker-profile` | Persistent browser profile for the logged-in Reddit session. |
| `BROWSER_CHANNEL` | `chrome` | Chromium channel (`chrome`, `msedge`, or empty for bundled Chromium). |
| `HEADLESS` | `false` | Set to `true` for headless runs (recommended only after the login flow has been done once and verified). |
| `SCREENSHOT_DIR` | `./worker-screenshots` | Where failure screenshots are written. |
| `REQUEST_TIMEOUT_SECONDS` | `60` | Backend HTTP timeout. |
| `USE_OLD_REDDIT` | `true` | Rewrite target URLs to `old.reddit.com` (significantly more stable for automation). Disable only if you have a specific reason. |
| `REDDIT_WARMUP_ENABLED` | `true` | Before replying, browse the subreddit/thread with human-paced waits and scrolling. |
| `REDDIT_PRE_REPLY_DELAY_MIN_SECONDS` / `REDDIT_PRE_REPLY_DELAY_MAX_SECONDS` | `3` / `9` | Random delay while warming up before opening the exact target. |
| `REDDIT_READ_DELAY_MIN_SECONDS` / `REDDIT_READ_DELAY_MAX_SECONDS` | `4` / `12` | Random delay after viewing the target context before filling the reply. |
| `REDDIT_SCROLL_STEPS_MIN` / `REDDIT_SCROLL_STEPS_MAX` | `2` / `5` | Number of natural scroll steps before replying. |

## Failure modes

- **Not logged in** — fix by running `python -m playwright_worker login` again.
- **CAPTCHA** — the worker takes a screenshot and reports the failure with a
  CAPTCHA-specific message; the draft is requeued so it can be retried later.
- **Selector / timeout** — a screenshot is saved in `SCREENSHOT_DIR` and the
  draft is requeued. Inspect the screenshot to diagnose.

## Production notes

- Use a *dedicated* Reddit account for automation; do not mix with personal use.
- Use a stable, headed `xvfb` setup or `HEADLESS=true` once verified.
- Persist `USER_DATA_DIR` on durable storage; it contains the session cookies.
- Monitor the worker via `GET /worker/queue` for counts of APPROVED / POSTING /
  POSTED / FAILED.
- Reddit may invalidate sessions after long idle periods — re-run the login
  helper if the worker starts reporting "Not logged in".
