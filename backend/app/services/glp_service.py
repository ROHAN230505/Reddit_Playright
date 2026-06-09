"""Godlike Productions scraper.

GLP has no public API. The site sits behind Cloudflare and returns 403 to
plain-HTTP clients (requests, httpx, plain Playwright over a datacenter IP).

**Reading is anonymous** — newthreads/threads can be fetched without an
account. A residential / mobile proxy is still required to get past
Cloudflare's edge from a server IP, but no cookies / storage_state are needed
for read paths. We expose `GLP_STORAGE_STATE_PATH` as an optional knob: set
it if Cloudflare's bot score gets aggressive and pre-logged-in cookies help
the browser pass.

This module produces newthreads listings and per-thread bodies as dicts that
feed straight into the existing `save_post()` / `save_comment()` writers. The
field names mirror Reddit's shape so the writers don't need GLP-specific
branches.

The actual Playwright fetch lives in `_fetch_html_playwright()`. It's
intentionally a thin seam: tests inject canned HTML via the `html_fetcher`
parameter, prod calls real Playwright. CSS selectors are best-effort defaults
that MUST be verified against the live site during Phase 0 recon and patched
in `docs/glp-recon.md` if they shift.
"""

from __future__ import annotations

import os
import re
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Iterable
from urllib.parse import urljoin, urlparse

from app.services.glp_targets import build_thread_url, build_topic_url, parse_glp_url


GLP_HOST = "https://www.godlikeproductions.com"
NEW_THREADS_URL = f"{GLP_HOST}/newthreads.php"

# Storage state captured manually from a logged-in browser (cookies + localStorage).
# Phase 0 recon produces this file. Without it we can read newthreads/threads but
# not post — and Cloudflare may still 403 if the file is too stale.
GLP_STORAGE_STATE_PATH = os.getenv(
    "GLP_STORAGE_STATE_PATH", "/home/pwuser/.glp/storage_state.json"
)

# Residential proxy URL from the provider. Required in prod.
GLP_PROXY_URL = os.getenv("GLP_PROXY_URL", "")

# Persistent browser profile dir for the scraper. Reusing one profile keeps the
# Cloudflare `cf_clearance` cookie between fetches so we don't re-run the
# challenge every time. Must be writable by the runtime user.
GLP_SCRAPER_USER_DATA_DIR = os.getenv(
    "GLP_SCRAPER_USER_DATA_DIR", "/tmp/glp-scraper-profile"
)
# Headful (under xvfb) passes Cloudflare where headless does not. The worker
# image has xvfb; run the celery worker under `xvfb-run`. Set GLP_HEADLESS=1 to
# force headless (will likely fail the challenge — for debugging only).
GLP_HEADLESS = os.getenv("GLP_HEADLESS", "0").lower() in ("1", "true", "yes", "on")
# Real Chrome UA — must stay consistent with navigator.userAgent.
GLP_USER_AGENT = os.getenv(
    "GLP_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
)
# Max seconds to wait for the Cloudflare "Just a moment..." challenge to clear.
GLP_CHALLENGE_TIMEOUT = int(os.getenv("GLP_CHALLENGE_TIMEOUT", "40"))
# Seconds to wait between failed fetch attempts. Spacing retries out keeps us
# from tripping Cloudflare's per-IP rate limit on the challenge interstitial.
GLP_RETRY_BACKOFF_SECONDS = int(os.getenv("GLP_RETRY_BACKOFF_SECONDS", "20"))


def _looks_like_challenge(page) -> bool:
    """True while the Cloudflare interstitial is still showing."""
    try:
        title = page.title() or ""
    except Exception:  # noqa: BLE001
        return True
    return "Just a moment" in title or "Attention Required" in title


def _is_ip_banned(page) -> bool:
    """True if GLP is serving its 'YOUR IP ADDRESS HAS BEEN BANNED' page.

    GLP's IP-check JS records the exit IP in the browser profile (localStorage/
    cookies) and flags a mismatch when the profile is later reused behind a
    different IP — so a profile created behind a now-banned/changed proxy IP
    keeps surfacing this page even after the proxy is swapped. The fix is to
    drop the poisoned profile and retry fresh (handled in the fetch loop)."""
    try:
        title = page.title() or ""
    except Exception:  # noqa: BLE001
        return False
    return "IP ADDRESS IS BANNED" in title.upper() or "IP ADDRESS HAS BEEN BANNED" in title.upper()


def _wipe_profile_dir(path: str) -> None:
    """Delete the persistent browser profile so the next launch starts clean.
    Best-effort: a failure here just means the next attempt reuses the profile."""
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:  # noqa: BLE001
        pass


def _profile_dir_for_process() -> str:
    """Return a per-process Chromium profile dir under GLP_SCRAPER_USER_DATA_DIR.

    Celery's prefork pool runs several fetches concurrently; a single shared
    user_data_dir can only be held by one Chromium at a time, so we suffix the
    base dir with the OS pid. Same process → same dir (cf_clearance persists
    across a run); different workers → different dirs (no lock collision)."""
    return f"{GLP_SCRAPER_USER_DATA_DIR}-pid{os.getpid()}"


def _is_membership_gate(html: str) -> bool:
    """True if the HTML is GLP's 'Membership Contract' interstitial."""
    return 'name="disclaimer"' in html or "Membership Contract:" in html


def _accept_membership_gate(page) -> bool:
    """GLP shows a one-time 'Membership Contract' interstitial before any forum
    content: two checkboxes (c1, c2 — agree to terms / privacy) and a 'Continue'
    submit that GETs ``/newthreads.php?c1=1&c2=1&disclaimer=Continue``. The
    server then sets a persistent ``disclaimer1`` cookie, so this fires once per
    profile.

    We submit the GET form directly via navigation rather than checking boxes +
    clicking — that sidesteps the page's JS validation timing and is far more
    reliable headless/headful. Returns True if the gate was present.
    """
    try:
        if not _is_membership_gate(page.content()):
            return False
        page.goto(
            f"{GLP_HOST}/newthreads.php?c1=1&c2=1&disclaimer=Continue",
            wait_until="domcontentloaded",
            timeout=45_000,
        )
        return True
    except Exception:  # noqa: BLE001
        return False


# --- HTML fetch ----------------------------------------------------------------


def _proxy_to_playwright_dict(proxy_url: str) -> dict:
    """Convert a provider proxy URL into the dict
    Playwright expects: ``{"server": "http://host:port", "username", "password"}``.

    Playwright/patchright does NOT read credentials embedded in the ``server``
    URL — passing the whole URL there yields an HTTP 407 (proxy auth required).
    The username/password must be split out into their own keys.
    """
    parsed = urlparse(proxy_url)
    server = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        server = f"{server}:{parsed.port}"
    out: dict = {"server": server}
    if parsed.username:
        out["username"] = parsed.username
    if parsed.password:
        out["password"] = parsed.password
    return out


def _sync_playwright():
    """Return a sync_playwright factory, preferring patchright (the
    anti-detection fork the posting worker uses) over plain Playwright.

    GLP sits behind Cloudflare; plain headless Playwright gets challenged/403'd.
    patchright + tf-playwright-stealth is the stack that passes. We fall back to
    plain playwright if patchright isn't installed so tests / Reddit-only
    deployments still import cleanly.
    """
    try:
        from patchright.sync_api import sync_playwright  # type: ignore
        return sync_playwright
    except Exception:  # noqa: BLE001
        from playwright.sync_api import sync_playwright  # local import
        return sync_playwright


def _maybe_apply_stealth(page) -> None:
    """Apply tf-playwright-stealth patches to a page if the package is present.
    Best-effort and version-tolerant; a no-op if stealth isn't installed."""
    try:
        from playwright_stealth import Stealth  # type: ignore
        Stealth().apply_stealth_sync(page)
        return
    except Exception:  # noqa: BLE001
        pass
    try:
        from playwright_stealth import stealth_sync  # type: ignore
        stealth_sync(page)
    except Exception:  # noqa: BLE001
        pass


def _fetch_html_playwright(url: str, *, proxy_url: str | None = None,
                            storage_state_path: str | None = None,
                            wait_for_selector: str | None = None,
                            attempts: int = 3) -> str:
    """Fetch a single GLP URL past Cloudflare via patchright.

    The recipe that actually clears GLP's Cloudflare challenge (verified against
    the live site through a residential proxy):
      - **patchright** (anti-detect Playwright fork) — its built-in patches do
        the heavy lifting. We deliberately do NOT stack tf-playwright-stealth on
        top; that double-patches and is itself fingerprinted.
      - **headful** (GLP_HEADLESS=0) under xvfb — headless Chromium is 403'd.
      - **persistent context** on a stable profile dir so the `cf_clearance`
        cookie survives between fetches (avoids re-running the challenge).
      - a **wait loop** for the "Just a moment..." interstitial to clear, with a
        few retries since clearance is probabilistic per session.

    Run the celery worker under `xvfb-run` so a display is available.
    """
    sync_playwright = _sync_playwright()

    # Per-process profile dir. A Chromium user_data_dir can only be opened by one
    # process at a time; celery runs the fetch in a prefork pool (concurrency 8),
    # so a shared dir means two workers collide — the second launch logs "Opening
    # in existing browser session" and dies with TargetClosedError → 0 threads.
    # Scoping the dir to the PID isolates concurrent workers while still keeping a
    # *persistent* profile per process (cf_clearance survives across the many
    # thread fetches in one run).
    user_data_dir = _profile_dir_for_process()

    launch_args: dict = {
        "user_data_dir": user_data_dir,
        "headless": GLP_HEADLESS,
        "user_agent": GLP_USER_AGENT,
        "viewport": {"width": 1366, "height": 900},
        "locale": "en-US",
        # --no-sandbox/--disable-dev-shm-usage for container stability. We do
        # NOT pass --disable-blink-features=AutomationControlled — patchright
        # handles that and duplicating it breaks its stealth.
        "args": [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
        ],
    }
    proxy = proxy_url or GLP_PROXY_URL
    if proxy:
        launch_args["proxy"] = _proxy_to_playwright_dict(proxy)

    last_html = ""
    for attempt in range(1, attempts + 1):
        wipe_profile_after = False
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(**launch_args)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                # Keep the HTTP UA aligned with navigator.userAgent (patchright
                # sets the latter; this matches the header). No stealth_sync.
                try:
                    page.set_extra_http_headers({"User-Agent": GLP_USER_AGENT})
                except Exception:  # noqa: BLE001
                    pass
                page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                # Wait for the Cloudflare interstitial to clear.
                waited = 0
                while waited < GLP_CHALLENGE_TIMEOUT and _looks_like_challenge(page):
                    page.wait_for_timeout(2000)
                    waited += 2
                if _looks_like_challenge(page):
                    # Cloudflare didn't clear. A reused profile with a stale or
                    # corrupt cf_clearance (common after the container that owns
                    # the profile is recreated mid-write) gets stuck here every
                    # time, while a *fresh* profile clears reliably. So drop the
                    # profile before the next attempt rather than retrying into
                    # the same bad state. Skip the wipe on the final attempt
                    # (nothing left to retry).
                    if attempt < attempts:
                        wipe_profile_after = True
                    continue
                # Past Cloudflare. If GLP serves its IP-ban page, the persistent
                # profile is poisoned with a stale stored-IP (e.g. from a
                # previous/banned proxy exit). Wipe it so the next attempt starts
                # fresh and re-stores the current IP. If the IP itself is banned,
                # attempts simply exhaust and we surface empty — operator swaps
                # GLP_PROXY_URL to a clean exit.
                if _is_ip_banned(page):
                    wipe_profile_after = True  # drop poisoned profile post-close
                    continue
                # Accept the membership-contract gate if shown;
                # it sets a persistent `disclaimer1` cookie, then re-load the URL
                # so we land on the real content.
                if _accept_membership_gate(page):
                    page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                    waited = 0
                    while waited < GLP_CHALLENGE_TIMEOUT and _looks_like_challenge(page):
                        page.wait_for_timeout(2000)
                        waited += 2
                if wait_for_selector and not _looks_like_challenge(page):
                    try:
                        page.wait_for_selector(wait_for_selector, timeout=15_000)
                    except Exception:  # noqa: BLE001
                        pass
                last_html = page.content()
                # Only accept clean content — a lingering challenge or gate page
                # means retry (the profile now carries cf_clearance/disclaimer1).
                if not _looks_like_challenge(page) and not _is_membership_gate(last_html):
                    return last_html
            finally:
                context.close()
        # A poisoned profile (stale stored-IP → ban page) must be wiped only
        # after the context is closed, or the dir is still locked/in use.
        if wipe_profile_after:
            _wipe_profile_dir(user_data_dir)
        # else: challenge/gate still up — retry with the (now persisted) profile.
        # Back off before re-challenging. Rapid-fire retries against Cloudflare's
        # interstitial get the exit IP rate-limited (every subsequent challenge
        # then fails for a while, even on a fresh profile), so we space attempts
        # out. Skip the wait after the final attempt.
        if attempt < attempts:
            time.sleep(GLP_RETRY_BACKOFF_SECONDS)
    return last_html


HtmlFetcher = Callable[[str], str]


# --- Parsing -------------------------------------------------------------------


@dataclass
class GlpThreadStub:
    """A single row from the newthreads listing."""

    thread_id: str
    title: str
    url: str
    author: str | None = None
    reply_count: int = 0
    created_at: datetime | None = None
    last_post_at: datetime | None = None
    section: str | None = None  # GLP tag/category if exposed in markup


@dataclass
class GlpPost:
    """A single post within a thread (OP or reply)."""

    post_id: str
    author: str | None
    body_text: str
    created_at: datetime | None = None
    url: str = ""


@dataclass
class GlpThreadDetail:
    """A thread page parsed into OP + replies."""

    thread_id: str
    title: str
    url: str
    op: GlpPost
    replies: list[GlpPost] = field(default_factory=list)
    section: str | None = None


# Thread rows on /newthreads.php, /forum1/pgN and /topics/<...> all link to
# `/forum1/message<id>`. The real title anchor carries a `title="..."` attribute
# (the full thread title) and inner HTML that may contain tags (e.g. <b>).
# There are also pagination anchors to the same URL whose inner text is just a
# page number ("1", "2") — we skip those. Capture the whole anchor so we can
# read the title attribute (preferred) or fall back to the stripped inner text.
_THREAD_ANCHOR_RE = re.compile(
    r'<a\b(?P<attrs>[^>]*?)'
    r'href="(?P<url>/forum\d*/message(?P<thread_id>\d+)(?:/pg\d+)?)"'
    r'(?P<attrs2>[^>]*)>(?P<inner>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_TITLE_ATTR_RE = re.compile(r'title="(?P<t>[^"]*)"', re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_REPLY_COUNT_RE = re.compile(
    r"(?:replies?|posts?)\D*?(?P<n>\d+)", re.IGNORECASE
)


def _strip_tags(html: str) -> str:
    import html as _html  # local import; only needed during parsing
    return _html.unescape(_TAG_RE.sub("", html)).strip()


def parse_newthreads_html(html: str) -> list[GlpThreadStub]:
    """Parse a GLP thread listing (newthreads / forum page / topic page) into
    thread stubs.

    Leans on the stable `/forum1/message<id>` URL pattern. The thread title is
    taken from the anchor's `title=` attribute when present (it holds the full,
    clean title), otherwise from the tag-stripped link text. Pagination anchors
    (inner text is just a page number) are skipped, and we keep the FIRST real
    title seen per thread id.
    """
    stubs: list[GlpThreadStub] = []
    seen: set[str] = set()
    for match in _THREAD_ANCHOR_RE.finditer(html):
        thread_id = match.group("thread_id")
        if thread_id in seen:
            continue
        attrs = match.group("attrs") + match.group("attrs2")
        inner_text = _strip_tags(match.group("inner"))
        # Skip pagination links ("1", "2", "Page 3", "»") — not titles.
        if inner_text.isdigit() or not inner_text:
            title_attr = _TITLE_ATTR_RE.search(attrs)
            if not (title_attr and title_attr.group("t").strip()):
                continue  # nothing usable on this anchor; try the next one
        title_attr = _TITLE_ATTR_RE.search(attrs)
        title = (title_attr.group("t").strip() if title_attr else "") or inner_text
        if not title or title.isdigit():
            continue
        seen.add(thread_id)
        stubs.append(
            GlpThreadStub(
                thread_id=thread_id,
                title=title,
                url=urljoin(GLP_HOST, match.group("url")),
            )
        )
    return stubs


# Each post on a thread page is a table row tagged with the member id and the
# real post UID, e.g. `<tr class="post_member_207430 post_uid_90254794" id="post_1">`.
# Inside: a `messageauthor` cell with a `/members/<id>/profile` link, and a
# content cell (`messagecontent` for the OP, `replycontent` for replies) whose
# body text lives in `<div class="post_main">`.
_POST_ROW_RE = re.compile(
    r'<tr\s+class="post_member_(?P<member>\d+)\s+post_uid_(?P<uid>\d+)"[^>]*'
    r'id="post_(?P<seq>\d+)"',
    re.IGNORECASE,
)
_POST_MAIN_RE = re.compile(r'<div class="post_main">(?P<body>.*?)</div>\s*</div>\s*</td>',
                           re.IGNORECASE | re.DOTALL)
_AUTHOR_RE = re.compile(r'/members/\d+/profile"[^>]*>(?P<name>[^<]+)<', re.IGNORECASE)


def _clean_post_body(fragment: str) -> str:
    """Strip the post_main HTML fragment down to readable text."""
    import html as _html
    x = re.sub(r"<!--.*?-->", " ", fragment, flags=re.DOTALL)
    x = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", x, flags=re.DOTALL | re.IGNORECASE)
    # quoted-reply blocks add noise but are still context; keep their text.
    x = re.sub(r"<br\s*/?>", "\n", x, flags=re.IGNORECASE)
    x = _TAG_RE.sub(" ", x)
    return re.sub(r"[ \t]+", " ", _html.unescape(x)).strip()


def parse_thread_html(html: str, thread_id: str, page: int = 1) -> GlpThreadDetail | None:
    """Parse a GLP thread page into OP + replies with real post UIDs, authors,
    and body text.

    Returns None when the page has no recognizable post rows (e.g. the fetch hit
    a Cloudflare interstitial or membership gate). Caller should retry.
    """
    starts = [(m.start(), m) for m in _POST_ROW_RE.finditer(html)]
    if not starts:
        return None

    title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
    title = (title_match.group(1).strip() if title_match else f"Thread {thread_id}")
    title = re.sub(r"\s*-\s*Godlike Productions.*$", "", title).strip() or f"Thread {thread_id}"

    posts: list[GlpPost] = []
    for idx, (pos, m) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(html)
        block = html[pos:end]
        uid = m.group("uid")
        body_match = _POST_MAIN_RE.search(block)
        body = _clean_post_body(body_match.group("body")) if body_match else ""
        # GLP reply bodies are prefixed with the "Re: <title>" header line;
        # drop a leading "Re: ..." line so it isn't mistaken for content.
        author_match = _AUTHOR_RE.search(block)
        posts.append(
            GlpPost(
                post_id=uid,
                author=author_match.group("name").strip() if author_match else None,
                body_text=body,
                url=f"{GLP_HOST}/forum{1}/message{thread_id}/pg{page}#post_{uid}",
            )
        )

    return GlpThreadDetail(
        thread_id=thread_id,
        title=title,
        url=build_thread_url(thread_id, page=page),
        op=posts[0],
        replies=posts[1:],
    )


# --- High-level fetch + normalize ---------------------------------------------


def fetch_newthreads(
    limit: int = 50,
    *,
    html_fetcher: HtmlFetcher | None = None,
    source_url: str | None = None,
    section: str | None = None,
) -> dict:
    """Fetch a GLP thread listing and return Apify-shaped items so the
    existing `process_subreddit()` flow can consume them unchanged.

    By default this reads `/newthreads.php` (all topics). Pass `source_url`
    (e.g. a `/topics/Science/Technology` page from `build_topic_url`) to scrape
    a topic-scoped listing instead; topic pages carry the same
    `/forum1/message<id>` links, so the parser is unchanged. `section`, when
    given, tags every stub so downstream `assigned_sections` filtering works.

    The returned dict has the same shape as `apify_service.fetch_subreddit`:
    `{"items": [...], "apify_run_id": None}` where each item carries
    `dataType` = "post" or "comment".
    """
    fetcher = html_fetcher or (lambda url: _fetch_html_playwright(url))
    html = fetcher(source_url or NEW_THREADS_URL)
    stubs = parse_newthreads_html(html)[:limit]
    if section:
        for stub in stubs:
            stub.section = section

    items: list[dict] = []
    for stub in stubs:
        items.append(
            {
                "dataType": "post",
                "url": stub.url,
                "title": stub.title,
                "subreddit": stub.section or "glp",
                "communityName": stub.section or "glp",
                "selfText": None,
                "score": 0,
                "numComments": stub.reply_count,
                "createdAt": (stub.created_at or datetime.utcnow()).isoformat(),
            }
        )
    return {"items": items, "apify_run_id": None, "thread_stubs": stubs}


def fetch_topic_threads(
    topic: str,
    *,
    limit: int = 50,
    page: int = 1,
    html_fetcher: HtmlFetcher | None = None,
) -> dict:
    """Fetch a single GLP topic listing (e.g. ``"Science/Technology"``).

    Thin wrapper over `fetch_newthreads` that points at the topic page and tags
    every stub with the topic slug as its `section`.
    """
    return fetch_newthreads(
        limit=limit,
        html_fetcher=html_fetcher,
        source_url=build_topic_url(topic, page=page),
        section=topic,
    )


def fetch_thread(
    thread_id: str,
    *,
    page: int = 1,
    html_fetcher: HtmlFetcher | None = None,
) -> GlpThreadDetail | None:
    """Fetch a single thread page and return the parsed detail."""
    url = build_thread_url(thread_id, page=page)
    fetcher = html_fetcher or (lambda u: _fetch_html_playwright(u))
    html = fetcher(url)
    return parse_thread_html(html, thread_id=thread_id, page=page)


def thread_to_items(detail: GlpThreadDetail) -> Iterable[dict]:
    """Yield Apify-shape items (one post + N comments) from a parsed thread."""
    yield {
        "dataType": "post",
        "url": detail.url,
        "title": detail.title,
        "subreddit": detail.section or "glp",
        "communityName": detail.section or "glp",
        "selfText": detail.op.body_text or None,
        "score": 0,
        "numComments": len(detail.replies),
        "createdAt": (detail.op.created_at or datetime.utcnow()).isoformat(),
    }
    for reply in detail.replies:
        yield {
            "dataType": "comment",
            "text": reply.body_text,
            "post_url": detail.url,
            "comment_url": reply.url,
            "author": reply.author,
            "upvotes": 0,
            "createdAt": (reply.created_at or datetime.utcnow()).isoformat(),
        }
