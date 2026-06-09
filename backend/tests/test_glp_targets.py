"""Unit tests for GLP URL parsing and builders."""

from __future__ import annotations

import pytest

from app.services.glp_targets import (
    GlpThreadRef,
    build_post_url,
    build_thread_url,
    is_glp_url,
    parse_glp_url,
)


@pytest.mark.parametrize(
    "url,thread_id,page,post_id",
    [
        ("https://www.godlikeproductions.com/forum1/message1846486/pg1", "1846486", 1, None),
        ("https://www.godlikeproductions.com/forum1/message5683275/pg8#105729964", "5683275", 8, "105729964"),
        ("http://godlikeproductions.com/forum1/message42/", "42", 1, None),
        ("https://www.godlikeproductions.com/forum1/message42", "42", 1, None),
    ],
)
def test_parse_glp_url_extracts_ids(url, thread_id, page, post_id):
    ref = parse_glp_url(url)
    assert ref is not None
    assert ref.thread_id == thread_id
    assert ref.page == page
    assert ref.post_id == post_id


@pytest.mark.parametrize(
    "url",
    [
        "https://www.reddit.com/r/foo/comments/abc/",
        "https://www.godlikeproductions.com/toc",
        "https://www.godlikeproductions.com/join.php",
        "not a url",
        "",
    ],
)
def test_parse_glp_url_rejects_non_thread_urls(url):
    assert parse_glp_url(url) is None


def test_is_glp_url_matches_any_glp_path():
    assert is_glp_url("https://www.godlikeproductions.com/anything")
    assert is_glp_url("http://godlikeproductions.com/")
    assert not is_glp_url("https://www.reddit.com/")
    assert not is_glp_url(None)
    assert not is_glp_url("")


def test_canonical_and_anchored_urls():
    ref = GlpThreadRef(thread_id="123", page=2, post_id="999")
    assert ref.canonical_url == "https://www.godlikeproductions.com/forum1/message123/pg2"
    assert ref.anchored_url == "https://www.godlikeproductions.com/forum1/message123/pg2#999"


def test_builders():
    assert build_thread_url(42) == "https://www.godlikeproductions.com/forum1/message42/pg1"
    assert build_thread_url(42, page=3) == "https://www.godlikeproductions.com/forum1/message42/pg3"
    assert (
        build_post_url(42, 9999, page=3)
        == "https://www.godlikeproductions.com/forum1/message42/pg3#9999"
    )
