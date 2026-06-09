"""4chan scraper.

Unlike GLP, 4chan exposes a public read-only JSON API at `a.4cdn.org` — no
auth, no Cloudflare gauntlet, no Playwright required for reading. Posting
still requires either a CAPTCHA solver or a 4chan Pass cookie; that's the
poster's problem (see `playwright_worker/chan_poster.py`).

This module produces newest-threads-per-board listings and per-thread bodies
as dicts that feed straight into the existing `save_post()` / `save_comment()`
writers. Field names mirror Reddit's shape so the writers don't need a
4chan-specific branch.

API rate limit: 4chan asks for ≤1 request/second per IP. The Celery beat
runs every 5 minutes by default and processes 2 boards (/g/, /biz/) with a
small per-thread fetch budget, well under that ceiling.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import unescape
from typing import Callable, Iterable

import requests

from app.services.chan_targets import board_catalog_url, build_post_url, build_thread_url


logger = logging.getLogger(__name__)

# 4chan asks for ≥1 second between API hits per IP. We default to a polite
# 1.1s sleep between requests; tests inject `sleep=lambda _s: None` to skip.
DEFAULT_BOARDS = ("g", "biz")
DEFAULT_INTER_REQUEST_SECONDS = 1.1
DEFAULT_TIMEOUT_SECONDS = 20


# --- Types --------------------------------------------------------------------


@dataclass
class ChanThreadStub:
    board: str
    thread_id: str
    title: str
    url: str
    op_body_text: str = ""
    op_author: str = "Anonymous"
    reply_count: int = 0
    image_count: int = 0
    created_at: datetime | None = None
    last_modified: datetime | None = None


@dataclass
class ChanPost:
    post_id: str
    author: str
    body_text: str
    created_at: datetime | None = None
    url: str = ""


@dataclass
class ChanThreadDetail:
    board: str
    thread_id: str
    title: str
    url: str
    op: ChanPost
    replies: list[ChanPost] = field(default_factory=list)


# --- HTTP fetch ---------------------------------------------------------------

JsonFetcher = Callable[[str], dict | list]


def _chan_proxies() -> dict | None:
    """Build a requests `proxies` dict from settings.chan_proxy_url, or None.

    The same proxy is used for http and https so the CONNECT tunnel to
    a.4cdn.org (https) is routed through it too.
    """
    from app.config import settings

    url = (settings.chan_proxy_url or "").strip()
    if not url:
        return None
    return {"http": url, "https": url}


def _fetch_json(url: str, *, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> dict | list:
    """Default JSON fetcher. Tests inject a fake via `json_fetcher`."""
    resp = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": "reddit-reply-draft/1.0"},
        proxies=_chan_proxies(),
    )
    resp.raise_for_status()
    return resp.json()


# --- HTML comment cleaning ----------------------------------------------------

# 4chan returns post bodies in HTML with these substitutions we have to undo:
#   <br>           → newline
#   <wbr>          → empty (zero-width break)
#   <s>...</s>     → spoiler (we just strip tags)
#   <a class="quotelink">>>123</a> → leave the >>123 text
#   <span class="quote">>greentext</span> → leave the >greentext text
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean_chan_html(html: str | None) -> str:
    if not html:
        return ""
    text = _BR_RE.sub("\n", html)
    text = _TAG_RE.sub("", text)
    return unescape(text).strip()


# --- Parsing ------------------------------------------------------------------


def _parse_catalog_thread(board: str, raw: dict) -> ChanThreadStub:
    thread_id = str(raw.get("no") or "")
    sub = unescape(raw.get("sub") or "").strip()
    com = _clean_chan_html(raw.get("com"))
    title = sub or (com.splitlines()[0][:120] if com else f"Thread {thread_id}")
    ts = raw.get("time")
    created = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
    last_mod = raw.get("last_modified")
    last_mod_dt = datetime.fromtimestamp(last_mod, tz=timezone.utc) if last_mod else None
    return ChanThreadStub(
        board=board,
        thread_id=thread_id,
        title=title,
        url=build_thread_url(board, thread_id),
        op_body_text=com,
        op_author=raw.get("name") or "Anonymous",
        reply_count=int(raw.get("replies") or 0),
        image_count=int(raw.get("images") or 0),
        created_at=created,
        last_modified=last_mod_dt,
    )


def parse_catalog(board: str, payload: list) -> list[ChanThreadStub]:
    """Catalog endpoint returns a list of pages; flatten to thread stubs."""
    stubs: list[ChanThreadStub] = []
    for page in payload or []:
        for thread in page.get("threads") or []:
            stubs.append(_parse_catalog_thread(board, thread))
    return stubs


def parse_thread(board: str, payload: dict) -> ChanThreadDetail | None:
    posts = payload.get("posts") or []
    if not posts:
        return None
    op_raw = posts[0]
    op = ChanPost(
        post_id=str(op_raw.get("no")),
        author=op_raw.get("name") or "Anonymous",
        body_text=_clean_chan_html(op_raw.get("com")),
        created_at=(
            datetime.fromtimestamp(op_raw["time"], tz=timezone.utc)
            if op_raw.get("time")
            else None
        ),
        url=build_post_url(board, op_raw.get("no"), op_raw.get("no")),
    )
    title = unescape(op_raw.get("sub") or "").strip() or op.body_text.splitlines()[0][:120] if op.body_text else f"Thread {op.post_id}"
    replies: list[ChanPost] = []
    for r in posts[1:]:
        replies.append(
            ChanPost(
                post_id=str(r.get("no")),
                author=r.get("name") or "Anonymous",
                body_text=_clean_chan_html(r.get("com")),
                created_at=(
                    datetime.fromtimestamp(r["time"], tz=timezone.utc)
                    if r.get("time")
                    else None
                ),
                url=build_post_url(board, op.post_id, r.get("no")),
            )
        )
    return ChanThreadDetail(
        board=board,
        thread_id=op.post_id,
        title=title,
        url=build_thread_url(board, op.post_id),
        op=op,
        replies=replies,
    )


# --- High-level fetch + normalize --------------------------------------------


def fetch_catalog(
    board: str,
    *,
    json_fetcher: JsonFetcher | None = None,
) -> list[ChanThreadStub]:
    fetcher = json_fetcher or _fetch_json
    payload = fetcher(board_catalog_url(board))
    if not isinstance(payload, list):
        logger.warning("Unexpected /catalog.json shape for /%s/: %r", board, type(payload))
        return []
    return parse_catalog(board, payload)


def fetch_thread(
    board: str,
    thread_id: str,
    *,
    json_fetcher: JsonFetcher | None = None,
) -> ChanThreadDetail | None:
    fetcher = json_fetcher or _fetch_json
    url = f"https://a.4cdn.org/{board.lower()}/thread/{thread_id}.json"
    try:
        payload = fetcher(url)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            # Thread 404'd (4chan threads expire) — not an error worth surfacing.
            logger.info("Thread /%s/%s 404'd (expired)", board, thread_id)
            return None
        raise
    if not isinstance(payload, dict):
        return None
    return parse_thread(board, payload)


def thread_to_items(detail: ChanThreadDetail) -> Iterable[dict]:
    """Yield Apify-shape items (one post + N comments) for save_post/save_comment."""
    yield {
        "dataType": "post",
        "url": detail.url,
        "title": detail.title,
        "subreddit": detail.board,
        "communityName": detail.board,
        "selfText": detail.op.body_text,
        "score": 0,
        "numComments": len(detail.replies),
        "createdAt": (detail.op.created_at or datetime.utcnow()).isoformat(),
    }
    for r in detail.replies:
        yield {
            "dataType": "comment",
            "text": r.body_text,
            "post_url": detail.url,
            "comment_url": r.url,
            "author": r.author,
            "upvotes": 0,
            "createdAt": (r.created_at or datetime.utcnow()).isoformat(),
        }


def fetch_boards(
    boards: Iterable[str] = DEFAULT_BOARDS,
    *,
    json_fetcher: JsonFetcher | None = None,
    sleep: Callable[[float], None] = time.sleep,
    inter_request_seconds: float = DEFAULT_INTER_REQUEST_SECONDS,
) -> dict:
    """Fetch catalogs for `boards`. Returns an Apify-shape payload of OP-only
    items so the existing process_subreddit-style writer path lights up.
    The deep per-thread fetch is done by `process_chan()` in processor.py so
    LLM calls only happen on threads we choose to drill into.
    """
    items: list[dict] = []
    stubs_by_thread: dict[str, ChanThreadStub] = {}
    for i, board in enumerate(boards):
        if i > 0:
            sleep(inter_request_seconds)
        try:
            stubs = fetch_catalog(board, json_fetcher=json_fetcher)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to fetch /%s/ catalog: %s", board, exc)
            continue
        for stub in stubs:
            stubs_by_thread[f"{stub.board}/{stub.thread_id}"] = stub
            items.append(
                {
                    "dataType": "post",
                    "url": stub.url,
                    "title": stub.title,
                    "subreddit": stub.board,
                    "communityName": stub.board,
                    "selfText": stub.op_body_text or None,
                    "score": 0,
                    "numComments": stub.reply_count,
                    "createdAt": (stub.created_at or datetime.utcnow()).isoformat(),
                }
            )
    return {"items": items, "apify_run_id": None, "thread_stubs": list(stubs_by_thread.values())}
