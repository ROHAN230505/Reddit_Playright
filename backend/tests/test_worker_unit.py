"""Unit-level coverage for the Playwright worker's pure-Python helpers.

We don't drive a real browser in CI, but the URL-rewriting and ID-parsing
logic is straightforward to test without one.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Skip these tests entirely if Playwright isn't installed (it's an optional
# dependency for the worker, not for the backend).
import pytest  # noqa: E402

playwright = pytest.importorskip("playwright")  # noqa: F841

from playwright_worker.poster import (  # noqa: E402
    PostingError,
    _comment_id_from_url,
    _detect_network_block,
    _raise_if_blocked_or_logged_out,
    to_old_reddit,
)


def test_to_old_reddit_rewrites_www():
    assert (
        to_old_reddit("https://www.reddit.com/r/x/comments/a/b/")
        == "https://old.reddit.com/r/x/comments/a/b/"
    )


def test_to_old_reddit_leaves_old_alone():
    url = "https://old.reddit.com/r/x/comments/a/b/"
    assert to_old_reddit(url) == url


def test_to_old_reddit_passes_through_non_reddit():
    assert to_old_reddit("https://example.com/foo") == "https://example.com/foo"


def test_comment_id_extraction():
    url = "https://old.reddit.com/r/x/comments/abc/slug/def456/"
    assert _comment_id_from_url(url) == "def456"


def test_comment_id_extraction_post_only():
    url = "https://old.reddit.com/r/x/comments/abc/slug/"
    assert _comment_id_from_url(url) is None


class _FakeLocator:
    def __init__(self, text: str = "", visible: bool = False):
        self._text = text
        self._visible = visible
        self.first = self

    def inner_text(self, timeout=0):
        return self._text

    def is_visible(self, timeout=0):
        return self._visible


class _FakePage:
    def __init__(self, title: str = "", body: str = "", login_visible: bool = False):
        self._title = title
        self._body = body
        self._login_visible = login_visible

    def title(self):
        return self._title

    def locator(self, selector):
        if selector == "body":
            return _FakeLocator(text=self._body)
        if "login-required" in selector:
            return _FakeLocator(visible=self._login_visible)
        return _FakeLocator()


def test_detect_network_block_by_title():
    assert _detect_network_block(_FakePage(title="Blocked")) is True


def test_detect_network_block_by_body_text():
    page = _FakePage(body="You have been blocked by network security.")
    assert _detect_network_block(page) is True


def test_blocked_page_raises_actionable_posting_error():
    with pytest.raises(PostingError, match="blocked_by_reddit"):
        _raise_if_blocked_or_logged_out(_FakePage(title="Blocked"))
