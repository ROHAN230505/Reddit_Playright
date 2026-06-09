# Multi-Account Support — Implementation Plan

Spec recap:
- Add Reddit-account management (username, password, 2FA secret).
- Auto-generate TOTP from the 2FA secret during automated login.
- Proxy registry with usage counts; warn if a proxy already has ≥1 account; recommend 1 account per proxy.
- Sequential account onboarding: add one, wait for it to verify, then move to the next.
- One Playwright persistent context per account (per-account profile dir).
- Live-process dashboard with one tab per account.

---

## Phase 0 — Decisions to confirm with the user

These materially shape the implementation. Picking defaults below, but want sign-off before building.

- [ ] **Secret encryption.** Default: Fernet (symmetric AES-128) with a new env var `ACCOUNT_ENCRYPTION_KEY` (URL-safe base64, 32 bytes). Stored ciphertext in DB; key never leaves env. Acceptable, or do you want KMS / a different scheme?
- [ ] **Process model.** Default: a single `playwright_worker` container that internally spawns one thread + one persistent browser context per active account. Simpler ops, single host. (Alternative: one container per account via `docker compose --scale`. More work, but true horizontal.)
- [ ] **Job → account binding.** Default: any active account can claim any APPROVED reply (existing pool). Add an optional `subreddit` allow-list per account later if needed. (Alternative: replies are sticky-assigned to one account at draft time.)
- [ ] **Proxy validation on add.** Default: launch a quick headless context through the proxy and fetch `https://api.ipify.org` to confirm it works before marking the proxy ACTIVE.
- [ ] **Live status transport.** Default: dashboard polls `/accounts/{id}/status` every 3s while the tab is open. (Alternative: SSE — more code, smoother UX. Defer unless asked.)
- [ ] **Headless during automated login.** Default: headless. The TOTP login flow doesn't need a visible window, and it must work in Docker. (Reddit may show a captcha — if so, surface a screenshot + status `NEEDS_REAUTH` and offer a "headed login" fallback button.)

---

## Phase 1 — Database & encryption

- [ ] Add `cryptography` to [backend/requirements.txt](backend/requirements.txt). Add `pyotp` to [playwright_worker/requirements.txt](playwright_worker/requirements.txt) and to backend reqs (so backend can do verification round-trips if needed).
- [ ] New env var: `ACCOUNT_ENCRYPTION_KEY` (document in [.env.example](.env.example)). Add a one-shot `python -m app.cli generate-key` helper.
- [ ] `app/services/crypto.py`: `encrypt(plaintext: str) -> str`, `decrypt(ciphertext: str) -> str` using Fernet.
- [ ] New tables in [backend/app/db/models.py](backend/app/db/models.py):
  - [ ] `Proxy` — id, label, scheme (`http|https|socks5`), host, port, username, password_enc, status (`ACTIVE|DISABLED|FAILED`), notes, last_checked_at, created_at.
  - [ ] `RedditAccount` — id, username (unique), password_enc, totp_secret_enc (nullable), proxy_id (FK→proxies, nullable), status (`NEW|VERIFYING|ACTIVE|NEEDS_REAUTH|DISABLED|FAILED`), last_login_at, last_seen_at (heartbeat), last_action, last_error, user_data_dir (derived: `<base>/<username>`), created_at.
- [ ] Add `posting_account_id` (FK→reddit_accounts, nullable) to `Reply` so we can audit who posted what.
- [ ] Extend `_ensure_runtime_columns()` in [backend/app/main.py](backend/app/main.py) for the new columns + `CREATE TABLE IF NOT EXISTS` for `proxies` / `reddit_accounts`. Keep additive style consistent with the existing pattern.

## Phase 2 — Backend API

New routes (all under bearer of existing dashboard auth):
- [ ] `routes/proxies.py`
  - [ ] `GET /proxies` — list with `account_count` aggregate.
  - [ ] `POST /proxies` — create + run live validation through the proxy (httpbin/ipify). Return 200 with status, or 422 with the failure reason.
  - [ ] `PATCH /proxies/{id}` — update (re-validate on change).
  - [ ] `DELETE /proxies/{id}` — block delete if any account references it.
- [ ] `routes/accounts.py`
  - [ ] `GET /accounts` — list with status, proxy label, last_seen relative.
  - [ ] `POST /accounts` — encrypt secrets, create row in `NEW`, kick off async login verification (Celery task `verify_account_login`).
  - [ ] `GET /accounts/{id}` — full detail incl. `last_action`, `last_error`, recent screenshots paths.
  - [ ] `PATCH /accounts/{id}` — update password / TOTP / proxy. Triggers re-verify.
  - [ ] `POST /accounts/{id}/reverify` — manual re-trigger.
  - [ ] `DELETE /accounts/{id}` — soft-disable. Worker drops it on next loop tick.
  - [ ] `POST /accounts/{id}/heartbeat` — worker → backend. Body: `last_action`, `status`. Updates `last_seen_at`.
- [ ] Update `/worker/claim`: accept optional `account_id` in payload; record `posting_account_id` on the reply at claim time.
- [ ] Schemas for all of the above in [backend/app/schemas.py](backend/app/schemas.py). **Never** return the password/TOTP plaintexts; return `has_totp: bool` instead.

## Phase 3 — Playwright worker rearchitecture

- [ ] `playwright_worker/login.py` — new module:
  - [ ] `automated_login(page, username, password, totp_secret)`:
    1. `page.goto("https://www.reddit.com/login/")`.
    2. Fill `input[name="username"]`, `input[name="password"]`, click submit.
    3. Wait for either: success (redirect to feed / presence of user nav) OR 2FA challenge OR captcha.
    4. If 2FA: locate the OTP input, fill `pyotp.TOTP(totp_secret).now()`, submit.
    5. Verify session (presence of user-menu element).
    6. On captcha → raise `CaptchaEncountered`. On any unexpected → raise `LoginFailed` with screenshot path.
- [ ] `playwright_worker/account_runtime.py` — new module:
  - [ ] `AccountRuntime` class wrapping (account_id, persistent_context, page-pool, heartbeat_thread).
  - [ ] `bootstrap()`: open context with proxy, run `automated_login` if not yet authenticated, send first heartbeat.
  - [ ] `process_loop()`: claim → post → report, posting `last_action` heartbeats at each step.
  - [ ] `shutdown()`: close context cleanly.
- [ ] Update [runner.py](playwright_worker/runner.py):
  - [ ] On startup, fetch active accounts from `/accounts` (decrypted view via authed channel) and start one `AccountRuntime` per account in its own thread.
  - [ ] Refresh the account list every N ticks; gracefully start new ones, stop disabled ones.
- [ ] Per-account profile path: `USER_DATA_DIR_BASE/<account_username>` (the existing `USER_DATA_DIR` becomes `USER_DATA_DIR_BASE`). Backwards compat: if no accounts in DB, fall back to single-context legacy mode.
- [ ] Pass proxy to `launch_persistent_context(proxy={"server": ..., "username": ..., "password": ...})`.
- [ ] Backend client extension: `get_active_accounts()`, `heartbeat(account_id, last_action)`. Keep existing `claim_next` etc.

## Phase 4 — Dashboard UI

- [ ] New top-level tabs alongside the existing reply queue: **Accounts**, **Proxies**, **Live**.
- [ ] **Proxies tab** ([dashboard/app/page.tsx](dashboard/app/page.tsx) split into per-tab components):
  - [ ] Table: label, host:port, scheme, status, account_count.
  - [ ] "Add proxy" form with live validation feedback ("testing… ✓ working / ✗ failed: …").
- [ ] **Accounts tab**:
  - [ ] Table: username, status pill, proxy label, last seen relative, last error (truncated).
  - [ ] "Add account" button → modal with username, password, 2FA secret (textarea, masked), proxy `<select>` showing **`label — host:port — N accounts`** with a yellow warning when N ≥ 1.
  - [ ] Submit posts to `/accounts`, then polls the new account's status every 1s until ACTIVE / FAILED / NEEDS_REAUTH. Disables the modal's "Add another" button until verification finishes — this is the "add accounts one by one and wait" flow.
- [ ] **Live tab**:
  - [ ] One sub-tab per active account (username as label).
  - [ ] Each sub-tab shows: status pill, last_action (relative time), proxy in use, recent screenshots thumbnails, mini-counters of replies posted in the last hour.
  - [ ] Polls `/accounts/{id}` every 3s while visible.

## Phase 5 — Compose / deployment

- [ ] Mount one shared volume `playwright_profiles` at `/home/pwuser/.reddit-worker-profile-base` (renamed from `playwright_profile`). Each account gets its subdir.
- [ ] Add `ACCOUNT_ENCRYPTION_KEY` to [.env.example](.env.example) with a clear "generate with `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`" comment.
- [ ] Document: existing single-account setups continue to work (legacy mode kicks in when no accounts row exists). Migration path: add the existing manual session as Account #1.

## Phase 6 — Tests & verification

- [ ] Unit: encrypt/decrypt round-trip; TOTP code generation matches `pyotp` reference.
- [ ] Unit: `automated_login` against a mocked Page (selectors hit, branches for 2FA / captcha / success).
- [ ] Unit: proxy validation timeout/failure paths.
- [ ] Integration: backend `/accounts` create → worker pulls → heartbeats arrive → `/accounts/{id}` shows ACTIVE.
- [ ] Backward-compat test: no accounts in DB → legacy single-context loop still runs.
- [ ] Manual verification checklist (don't mark done without running these):
  - [ ] Add a proxy, see it become ACTIVE.
  - [ ] Add an account, watch it transition NEW → VERIFYING → ACTIVE.
  - [ ] Approve a reply, see it claimed and posted by the new account.
  - [ ] Add a second account on a fresh proxy; verify both run independently.
  - [ ] Disable an account; verify the worker stops it on the next refresh tick.

---

## Changes log

(Per CLAUDE.md task-management rules — append to this section as work proceeds.)

- _Pending plan approval._
