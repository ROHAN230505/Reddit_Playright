# Reddit AI Reply Intelligence System

## To-Do List From The Spec

1. Manage a persistent tracked-subreddit list from the dashboard.
2. Queue fetch jobs for all tracked subreddits or manual subreddit entries.
3. Scrape Reddit posts and comments via the Apify Reddit actor.
4. Normalize the actor's flat JSON output of `post` and `comment` rows.
5. Filter comments using an LLM for AI relevance only.
6. Generate Reddit-style draft replies with DeepSeek.
7. Insert `sentx.ai` naturally in about 50% of relevant replies.
8. Store posts, comments, replies, and tracked subreddits in the database.
9. Display replies in a Streamlit dashboard with post/comment links.
10. Support copying reply drafts, marking replies done, and managing subreddit tracking.
11. Run the stack with FastAPI, Celery, Redis, PostgreSQL, and Docker.

## Run

1. Copy `.env.example` to `.env` and fill in your API keys.
2. Start the stack with `docker compose up --build`.
3. Open `http://localhost:8501` for the dashboard by default.
4. Open `http://localhost:8000/docs` for the API docs by default.
5. If your host already uses those ports, set `DASHBOARD_PORT` and `API_PORT` in `.env` before starting Compose.

## Apify Actor Notes

The app is wired for the flat JSON output from `prodiger/reddit-scraper`, where rows come back as a stream of `post` and `comment` items.
The default actor ID is configurable with `APIFY_ACTOR_ID`.

## Playwright Posting Worker (additive)

A separate process can post APPROVED drafts to Reddit automatically using
Playwright. It does not replace any existing functionality — the backend is
still the source of truth, the dashboard still owns approval, and the
Apify-based scrape and DeepSeek-based generation flows are untouched.

### Posting status flow

```
PENDING ──(operator approves in dashboard)──▶ APPROVED ──(worker claims)──▶ POSTING
   │                                                                          │
   │                                                                  ┌───────┴──────┐
   │                                                                  ▼              ▼
   └─(operator marks DONE manually)──▶ DONE                         POSTED         FAILED
                                                                                      │
                                                                       (operator hits Retry → APPROVED)
```

### Backend additions (all additive)

- New columns on `replies`: `target_type`, `target_url`, `reddit_post_id`,
  `reddit_comment_id`, `subreddit`, `posting_attempts`, `posting_claimed_at`,
  `posting_claimed_by`, `posting_error`, `posted_at`, `posted_reddit_comment_id`.
  These are added to existing databases on startup via the same
  `_ensure_runtime_columns()` mechanism used for previous additive changes.
- New endpoints under `/worker/*`:
  - `POST /worker/claim` — atomically claim the next APPROVED reply.
  - `POST /worker/{id}/posted` — mark a claimed reply POSTED.
  - `POST /worker/{id}/failed` — mark a claimed reply FAILED (default: requeue).
  - `GET /worker/queue` — counts by status (APPROVED/POSTING/POSTED/FAILED).
- Existing endpoints (`GET /replies`, `PATCH /replies/{id}`, etc.) are unchanged.

### Runtime data flow

```
[Apify scrape]
      │
      ▼
[backend stores Post + Comment + Reply (PENDING)]
      │
      ▼          (operator clicks "Approve to Post" in dashboard)
[Reply.status = APPROVED]                                 ◀──── single source of truth
      │
      │  POST /worker/claim
      ▼
[Playwright worker pulls {reply_text, target_url, target_type, ...}]
      │
      ▼
[Chromium opens old.reddit.com, fills exact text, submits]
      │
      ├── success ──▶ POST /worker/{id}/posted  ──▶ Reply.status = POSTED
      └── failure ──▶ POST /worker/{id}/failed  ──▶ requeue or hold in FAILED
```

The worker only acts on what the backend tells it to. It never invents
drafts and never edits the text — the exact `reply_text` that was approved
in the dashboard is what gets posted.

### Run the worker locally (development)

See `playwright_worker/README.md` for the full guide. Quick start:

```bash
pip install -r playwright_worker/requirements.txt
python -m playwright install chromium
python -m playwright_worker login          # one-off, sign in to Reddit
python -m playwright_worker run --once     # process one approved draft
python -m playwright_worker run            # continuous polling
```

### Run the worker in production (Docker)

The worker has its own Dockerfile and an opt-in Compose profile so it never
auto-starts alongside the backend. On a server:

```bash
# 1. Bring up backend + db + redis + dashboard as usual.
docker compose up -d backend db redis dashboard

# 2. One-time interactive Reddit login. The session is saved in a named
#    Docker volume (playwright_profile) and reused by every later run.
docker compose --profile playwright run --rm -it playwright_worker login

# 3. Start the continuous worker.
docker compose --profile playwright up -d playwright_worker

# 4. Logs, queue health.
docker compose --profile playwright logs -f playwright_worker
curl http://localhost:8000/worker/queue
```

Restart policy is `unless-stopped`, so the worker survives reboots. Failed
jobs are requeued automatically and surface in the dashboard's **Posting
Queue** tab with a Retry button.

### Production checklist

- Use a dedicated Reddit account for automation; don't mix with personal use.
- Persist the `playwright_profile` named volume on durable storage (it holds
  the Reddit session cookie). Re-running `... login` refreshes it if the
  session ever expires.
- `HEADLESS=true` is the production default. Verify on a test target before
  running unattended.
- Monitor `GET /worker/queue` — alert on growing `FAILED` count.
- Failure screenshots land in `./worker-screenshots` (bind-mounted), one PNG
  per failed attempt, named `reply_<id>_<label>_<utc>.png`.
- Reddit may rate-limit; tune `POLL_INTERVAL_SECONDS` upward if you see 429s.
- For non-Docker deployments (e.g. systemd on Linux), use the same env vars
  and run `python -m playwright_worker run` under your supervisor of choice.

### Tests

```bash
cd backend
pip install -r requirements.txt
pip install -r tests/requirements.txt
pytest
```

Tests cover claim atomicity, mark-posted, mark-failed, stale-claim recovery,
backward compatibility with the existing `/replies` flow, URL/fullname
parsing, and the worker's pure-Python helpers. CI runs them on every push and
PR — see `.github/workflows/backend-tests.yml`.
