"""Unit tests for 4chan URL parsing and builders."""

from __future__ import annotations

import pytest

from app.services.chan_targets import (
    ChanThreadRef,
    board_catalog_url,
    build_post_url,
    build_thread_url,
    is_chan_url,
    parse_chan_url,
)


@pytest.mark.parametrize(
    "url,board,thread_id,post_id",
    [
        ("https://boards.4chan.org/g/thread/12345678", "g", "12345678", None),
        ("https://boards.4chan.org/biz/thread/100/", "biz", "100", None),
        ("https://boards.4chan.org/g/thread/12345678#p12345999", "g", "12345678", "12345999"),
        ("https://boards.4channel.org/biz/thread/42", "biz", "42", None),
    ],
)
def test_parse_chan_url(url, board, thread_id, post_id):
    ref = parse_chan_url(url)
    assert ref is not None
    assert ref.board == board
    assert ref.thread_id == thread_id
    assert ref.post_id == post_id


@pytest.mark.parametrize(
    "url",
    [
        "https://www.reddit.com/r/foo/comments/abc/",
        "https://www.godlikeproductions.com/forum1/message42/pg1",
        "https://4chan.org/",  # no thread path
        "not a url",
        "",
    ],
)
def test_parse_chan_url_rejects_non_thread_urls(url):
    assert parse_chan_url(url) is None


def test_is_chan_url():
    assert is_chan_url("https://boards.4chan.org/g/")
    assert is_chan_url("https://a.4cdn.org/g/catalog.json")
    assert is_chan_url("https://boards.4channel.org/biz/")
    assert not is_chan_url("https://www.reddit.com/")
    assert not is_chan_url(None)


def test_canonical_and_anchored_urls():
    ref = ChanThreadRef(board="g", thread_id="42", post_id="999")
    assert ref.canonical_url == "https://boards.4chan.org/g/thread/42"
    assert ref.anchored_url == "https://boards.4chan.org/g/thread/42#p999"
    assert ref.json_url == "https://a.4cdn.org/g/thread/42.json"


def test_builders():
    assert build_thread_url("g", 42) == "https://boards.4chan.org/g/thread/42"
    assert (
        build_post_url("biz", 7, 99) == "https://boards.4chan.org/biz/thread/7#p99"
    )
    assert board_catalog_url("g") == "https://a.4cdn.org/g/catalog.json"
