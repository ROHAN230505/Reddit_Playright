"""URL parsing and ID extraction for godlikeproductions.com (GLP).

GLP canonical URL shapes (verified against site recon, 2026-05):

    https://www.godlikeproductions.com/forum1/message{thread_id}/pg{page}
    https://www.godlikeproductions.com/forum1/message{thread_id}/pg{page}#{post_id}

Thread IDs are 7+ digit numerics, monotonically increasing.
Post IDs are 9+ digit numerics within a thread.
There is currently one flat forum namespace (`/forum1/`) — the optional digit
after `forum` is parsed defensively in case the site adds shards later.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


_GLP_HOST_RE = re.compile(
    r"^https?://(?:www\.)?godlikeproductions\.com",
    re.IGNORECASE,
)

# Matches the canonical thread URL: forum1/message<thread_id>[/pgN][#post_id].
# We accept trailing slash, optional /pgN, and an optional #post_id anchor.
_GLP_THREAD_URL_RE = re.compile(
    r"""
    ^https?://(?:www\.)?godlikeproductions\.com
    /forum(?P<forum_id>\d*)
    /message(?P<thread_id>\d+)
    (?:/pg(?P<page>\d+))?
    /?
    (?:\#(?P<post_id>\d+))?
    $
    """,
    re.IGNORECASE | re.VERBOSE,
)


@dataclass(frozen=True)
class GlpThreadRef:
    """Parsed GLP thread/post reference."""

    thread_id: str
    forum_id: str = "1"
    page: int = 1
    post_id: str | None = None

    @property
    def canonical_url(self) -> str:
        """Canonical (no anchor) thread URL pointing at the right page."""
        return (
            f"https://www.godlikeproductions.com/forum{self.forum_id}"
            f"/message{self.thread_id}/pg{self.page}"
        )

    @property
    def anchored_url(self) -> str:
        """Thread URL with a #post_id anchor (falls back to canonical if no post)."""
        if not self.post_id:
            return self.canonical_url
        return f"{self.canonical_url}#{self.post_id}"


def is_glp_url(value: str | None) -> bool:
    """True if the URL points at the GLP domain (any path)."""
    if not value:
        return False
    return bool(_GLP_HOST_RE.match(value.strip()))


def parse_glp_url(value: str) -> GlpThreadRef | None:
    """Parse a canonical GLP thread/post URL. Returns None if it doesn't match.

    Examples accepted:
        https://www.godlikeproductions.com/forum1/message1234567
        https://www.godlikeproductions.com/forum1/message1234567/pg1
        https://www.godlikeproductions.com/forum1/message1234567/pg8#105729964
    """
    if not value:
        return None
    match = _GLP_THREAD_URL_RE.match(value.strip())
    if not match:
        return None
    page_str = match.group("page")
    return GlpThreadRef(
        thread_id=match.group("thread_id"),
        forum_id=match.group("forum_id") or "1",
        page=int(page_str) if page_str else 1,
        post_id=match.group("post_id"),
    )


def build_thread_url(thread_id: str | int, page: int = 1, forum_id: str = "1") -> str:
    """Build a canonical GLP thread URL for the given identifiers."""
    return GlpThreadRef(
        thread_id=str(thread_id), forum_id=forum_id, page=page
    ).canonical_url


def build_post_url(thread_id: str | int, post_id: str | int, page: int = 1,
                   forum_id: str = "1") -> str:
    """Build a canonical GLP post URL (thread URL + #post anchor)."""
    return GlpThreadRef(
        thread_id=str(thread_id),
        forum_id=forum_id,
        page=page,
        post_id=str(post_id),
    ).anchored_url


def build_topic_url(topic: str, page: int = 1) -> str:
    """Build a GLP topic-listing URL like ``/topics/Science/Technology[/pgN]``.

    ``topic`` is the path under ``/topics/`` exactly as GLP slugs it, e.g.
    ``"Science/Technology"`` or ``"Conspiracy/New_World_Order"``. A topic page
    lists the same ``/forum1/message<id>`` thread links as ``/newthreads.php``,
    so the existing thread-link parser consumes it unchanged — the difference is
    every thread on the page is already tagged to that topic.
    """
    slug = topic.strip().strip("/")
    base = f"https://www.godlikeproductions.com/topics/{slug}"
    return base if page <= 1 else f"{base}/pg{page}"
