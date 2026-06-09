# GLP Recon — Source of Truth for Selectors & Behavior

This document is the **single source of truth** for what godlikeproductions.com
looks like to the scraper and the poster. The code in
`backend/app/services/glp_service.py` and `playwright_worker/glp_poster.py`
falls back to *inferred* defaults — when those break, fix them here first,
then update the code to match.

Fill this out **before** running anything against the live site.

---

## 1. Environment

| Item | Value |
|---|---|
| Residential proxy provider | `<fill in>` (e.g. Evomi / Bright Data / Smartproxy) |
| Proxy URL | Provider proxy URL (set as env `GLP_PROXY_URL`) |
| Sticky session | yes / no — required: yes (1 IP per account) |
| Storage state path | `<fill in>` (env `GLP_STORAGE_STATE_PATH`, optional for reading) |
| Last verified | `<YYYY-MM-DD>` |

---

## 2. Reading (anonymous, no login required) — VERIFIED WORKING 2026-06-02

**How to actually reach GLP content** (verified live through a Decodo SG
residential proxy). Two gates sit in front of every page:

1. **Cloudflare "Just a moment..." challenge.** Cleared by:
   - **patchright** (anti-detect Playwright fork) — rely on its built-in
     patches; do NOT stack tf-playwright-stealth (double-patch is detectable).
   - **headful** Chromium under **xvfb** — headless is 403'd / gets
     `ERR_TUNNEL_CONNECTION_FAILED` through the proxy. Run the worker under
     `xvfb-run`.
   - **persistent context** on a stable profile dir → the `cf_clearance` cookie
     survives between fetches.
   - Proxy creds MUST be split into `{server, username, password}` (embedding
     them in the server URL yields HTTP 407).
2. **Membership Contract gate.** A one-time interstitial (title "Godlike
   Productions - Membership Contract") with checkboxes `c1`/`c2` + a "Continue"
   submit. It's a **GET** form → just navigate to
   `…/newthreads.php?c1=1&c2=1&disclaimer=Continue`, which sets a persistent
   `disclaimer1` cookie. (Clicking the boxes is flaky due to JS validation
   timing — the direct GET is reliable.) `glp_service._accept_membership_gate`
   does this automatically.

Both cookies (`cf_clearance`, `disclaimer1`) persist in the browser profile, so
after the first fetch the gates are skipped. Persist the profile across worker
restarts via a Docker volume on `GLP_SCRAPER_USER_DATA_DIR`.

### Listings (all link to `/forum1/message<id>`)
- **Newthreads:** `https://www.godlikeproductions.com/newthreads.php` (~46 rows)
- **Forum:** `https://www.godlikeproductions.com/forum1/pg1` (~90 rows; NOTE the
  listing is at `/forum1/pgN`, not `/forum1/`)
- **Topic (tech/AI target):** `https://www.godlikeproductions.com/topics/Science/Technology` (~90 rows)
- **Thread-link markup:** the real title anchor carries `title="<full title>"`
  and inner HTML (may contain `<b>` etc.); pagination anchors to the same URL
  have inner text "1"/"2". `parse_newthreads_html` prefers the `title=` attr and
  skips numeric pagination links. VERIFIED extracting real titles.

### Thread page
- **URL:** `https://www.godlikeproductions.com/forum1/message{thread_id}/pg{page}`
- **Post-block selector:** `_POST_BLOCK_RE` = `name|id="post_<digits>"`.
- **Body / author selectors:** `<verify — see §test of fetch_thread>`

### Pagination
- Page param is `/pgN`. Topic/forum listing pagination via `/pgN` too.

---

## 3. Account creation (one-time, manual)

- Registration URL: `https://www.godlikeproductions.com/join.php`
- **reCAPTCHA on signup**: yes (confirmed).
- Account tier: free is sufficient for posting in `/forum1/`.
- Verification email: required `<yes / no>`.

---

## 4. Login (poster)

- **URL:** `https://www.godlikeproductions.com/login.php` (loads form), POST
  goes to `/loginrespond.php`.
- **Username field:** `<verify selector — try `input[name='nick']`>`.
- **Password field:** `<verify — input[name='password']>`.
- **Captcha at login?** `<yes / no — go/no-go gate>`.
- **Logged-in markers** to detect a valid session:
  - `<fill in selectors — e.g. a[href*='logout.php']>`

---

## 5. Posting

### Reply form (inline at the bottom of a thread page)
- Form selector: `<verify — form[name='replyform'] or form[action*='/bbs/reply.php']>`
- Message textarea: `<verify — textarea[name='message']>`
- Subject field (optional): `<verify — input[name='subject']>`
- Submit button: `<verify — input[type='submit']>`
- Hidden tokens (CSRF, postid, etc.): list every hidden input on the form
  and whether it's static, per-thread, or per-session.

### After-submit signals
- **Success URL pattern:** `<verify — does it gain `#post_<id>`?>`
- **Captcha after submit?** `<yes / no>` — and on what condition (first
  post, after N posts, flagged thread, etc.)
- **Flood-control message text:** `<paste actual error wording so the
  regexes in glp_poster.py::_FLOOD_PATTERNS match>`
- **Ban message text:** `<paste actual wording>`

### Observed cadence
- Minimum seconds between posts before flood control fires: `<fill in>`
- Per-account posts/hour before getting flagged: `<fill in>`
- Per-account posts/day before getting flagged: `<fill in>`

---

## 6. TOS / risk register

- Automation: **explicitly prohibited** in TOS.
- Harvest/screenshot: **explicitly prohibited** in TOS.
- Mod behavior: aggressive bans for low-effort / promotional posting.
- Mitigations baked in:
  - GLP-default cadence: 2 posts/hr · 12/day · 10-30 min jitter
  - Per-account residential sticky IP
  - Automatic disable on ban detection (`status=BANNED` via heartbeat)
  - Cooldown bump on detected flood-control
  - Conservative beat schedule: scrape every 15 min

---

## 6b. Forum sections / topic taxonomy

GLP organizes content as `/topics/<Category>/<Subtopic>` (a tag/category
browser). Actual threads are *posted* in `/forum1/` (free tier), but each
thread carries one of these topic tags. The list below is from Google-indexed
`/topics/` pages + the topic-count signals on `/members/interests.php`
(the live site 403s direct bot fetches, so this was assembled from the search
index rather than scraped — re-verify against the live site when possible).

**Top-level categories** (high-activity ones marked with approx thread counts):

| Category | Notable subtopics (verified via indexed URLs) | Activity |
|---|---|---|
| Conspiracy | `9-11_Conspiracies`, `HAARP`, `Terrorism`, `Vaccination`, `New_World_Order` | NWO ~43k |
| Aliens / UFOs | `UFOs_and_Aliens` | ~41k |
| Spirituality | — | ~43k |
| Paranormal | `Psychics`, `Mind_Control`, `Predictions_and_Prophecies` | high |
| Religion | — | ~29k |
| Politics | — | ~28k |
| Science | `Technology` | active |
| Disasters | `Earthquakes` | active |
| US_Agencies | `DEA` | niche |

**Recommended high-traffic sections to target** (most active = most reply
opportunities): `Conspiracy`, `Aliens`/`UFOs_and_Aliens`, `Spirituality`,
`Paranormal`, `Religion`, `Politics`, `Science`, `Disasters`.

### Tech/AI targeting (implemented 2026-06-01)

GLP has **no dedicated AI forum** — AI discussion lives in `Science/Technology`
and scattered general threads. To keep accounts tech/AI-only we scrape the
**topic page** rather than `/newthreads.php`:

- `settings.glp_topics` (env `GLP_TOPICS`, default `Science/Technology`) lists
  the topic slugs to scrape.
- `glp_service.fetch_topic_threads(topic)` fetches `/topics/<slug>` via
  `build_topic_url()`; topic pages carry the same `/forum1/message<id>` links
  so the existing parser is unchanged. Every stub is tagged with the topic slug
  as its `section`.
- `processor.process_glp()` iterates `glp_topics`, so **only tech threads ever
  become GLP replies** — off-topic threads are never scraped or drafted.
- The tag flows `section → post.subreddit → Reply.platform_section`, so the 6
  accounts' `assigned_sections="Science/Technology"` is accurate metadata.

> Note: the worker's `/worker/claim` filters by **platform** but not yet by
> `assigned_sections` — the tech restriction is enforced at *scrape* time
> (above), which is sufficient. If you later want per-account section routing
> (e.g. split topics across accounts), add an `assigned_sections` filter to
> `claim_next` in `app/routes/worker.py` matching `Reply.platform_section`.

## 7. Changelog

| Date | Change | By |
|---|---|---|
| 2026-06-01 | Forum/topic taxonomy captured (§6b) from search index | Claude |
| `<YYYY-MM-DD>` | Initial recon captured | `<you>` |
