"""URL parsing and ID extraction for 4chan (boards.4chan.org).

Canonical URL shapes:
    https://boards.4chan.org/{board}/thread/{thread_id}
    https://boards.4chan.org/{board}/thread/{thread_id}#p{post_id}

Board names are lowercase, 1-4 chars (e.g. `g`, `biz`, `pol`, `int`).
Thread IDs and post IDs are positive integers; post IDs include the OP.
The JSON API mirrors the same `{board}/thread/{id}` namespace at
`https://a.4cdn.org/{board}/thread/{id}.json`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# Allow www., 2ch., 4channel.org as the same site (4chan migrated boards
# between 4chan.org and 4channel.org around 2019; both still resolve).
_CHAN_HOST_RE = re.compile(
    r"^https?://(?:[a-z]+\.)?(?:4chan|4channel|4cdn)\.org",
    re.IGNORECASE,
)

_CHAN_THREAD_URL_RE = re.compile(
    r"""
    ^https?://(?:www\.|boards\.)?(?:4chan|4channel)\.org
    /(?P<board>[a-z0-9]{1,4})
    /thread/(?P<thread_id>\d+)
    /?
    (?:\#p?(?P<post_id>\d+))?
    $
    """,
    re.IGNORECASE | re.VERBOSE,
)


@dataclass(frozen=True)
class ChanThreadRef:
    board: str
    thread_id: str
    post_id: str | None = None

    @property
    def canonical_url(self) -> str:
        return f"https://boards.4chan.org/{self.board}/thread/{self.thread_id}"

    @property
    def anchored_url(self) -> str:
        if not self.post_id:
            return self.canonical_url
        return f"{self.canonical_url}#p{self.post_id}"

    @property
    def json_url(self) -> str:
        return f"https://a.4cdn.org/{self.board}/thread/{self.thread_id}.json"


def is_chan_url(value: str | None) -> bool:
    if not value:
        return False
    return bool(_CHAN_HOST_RE.match(value.strip()))


def parse_chan_url(value: str) -> ChanThreadRef | None:
    if not value:
        return None
    match = _CHAN_THREAD_URL_RE.match(value.strip())
    if not match:
        return None
    return ChanThreadRef(
        board=match.group("board").lower(),
        thread_id=match.group("thread_id"),
        post_id=match.group("post_id"),
    )


def build_thread_url(board: str, thread_id: str | int) -> str:
    return ChanThreadRef(board=board.lower(), thread_id=str(thread_id)).canonical_url


def build_post_url(board: str, thread_id: str | int, post_id: str | int) -> str:
    return ChanThreadRef(
        board=board.lower(), thread_id=str(thread_id), post_id=str(post_id)
    ).anchored_url


def board_catalog_url(board: str) -> str:
    """JSON API endpoint for a board's catalog (all live threads)."""
    return f"https://a.4cdn.org/{board.lower()}/catalog.json"
