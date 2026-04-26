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

from playwright_worker.poster import _comment_id_from_url, to_old_reddit  # noqa: E402


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
