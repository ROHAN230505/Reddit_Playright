"""Tests for the 4chan JSON scraper. All HTTP is faked via injected fetchers."""

from __future__ import annotations

from app.services.chan_service import (
    _clean_chan_html,
    fetch_boards,
    fetch_catalog,
    fetch_thread,
    parse_catalog,
    parse_thread,
    thread_to_items,
)


CATALOG_PAYLOAD = [
    {
        "page": 0,
        "threads": [
            {
                "no": 12345678,
                "sub": "Best Python framework?",
                "com": "what do you guys use",
                "name": "Anonymous",
                "replies": 42,
                "images": 5,
                "time": 1_700_000_000,
                "last_modified": 1_700_001_000,
            },
            {
                "no": 12345700,
                "sub": "",
                "com": "VIM vs Emacs<br>thoughts?",
                "name": "Anonymous",
                "replies": 99,
                "images": 12,
                "time": 1_700_000_100,
            },
        ],
    },
    {
        "page": 1,
        "threads": [
            {"no": 12345800, "com": "Just a body, no subject"},
        ],
    },
]


THREAD_PAYLOAD = {
    "posts": [
        {
            "no": 100,
            "sub": "AI tools",
            "com": "anyone use ai agents?",
            "name": "Anonymous",
            "time": 1_700_000_000,
        },
        {
            "no": 101,
            "com": "<a class=\"quotelink\">&gt;&gt;100</a><br>nah they all suck",
            "name": "Anonymous",
            "time": 1_700_000_500,
        },
        {
            "no": 102,
            "com": "<span class=\"quote\">&gt;just use python</span><br>fpbp",
            "name": "Anonymous",
            "time": 1_700_001_000,
        },
    ]
}


def test_clean_chan_html_strips_tags_and_unescapes():
    assert _clean_chan_html("<br>hi<br>there") == "hi\nthere"
    assert (
        _clean_chan_html("<span>&gt;greentext</span><br>line2")
        == ">greentext\nline2"
    )
    assert _clean_chan_html(None) == ""
    assert _clean_chan_html("") == ""


def test_parse_catalog_flattens_pages():
    stubs = parse_catalog("g", CATALOG_PAYLOAD)
    assert len(stubs) == 3
    assert stubs[0].thread_id == "12345678"
    assert stubs[0].title == "Best Python framework?"
    assert stubs[0].url == "https://boards.4chan.org/g/thread/12345678"
    # Thread with no subject derives title from body.
    assert stubs[1].thread_id == "12345700"
    assert "VIM" in stubs[1].title


def test_parse_thread_returns_op_and_replies():
    detail = parse_thread("g", THREAD_PAYLOAD)
    assert detail is not None
    assert detail.thread_id == "100"
    assert detail.op.post_id == "100"
    assert detail.op.body_text == "anyone use ai agents?"
    assert len(detail.replies) == 2
    # HTML cleanup: greentext span becomes >greentext.
    assert detail.replies[1].body_text.startswith(">just use python")


def test_parse_thread_empty_returns_none():
    assert parse_thread("g", {"posts": []}) is None


def test_fetch_catalog_uses_injected_fetcher():
    stubs = fetch_catalog("g", json_fetcher=lambda url: CATALOG_PAYLOAD)
    assert len(stubs) == 3
    assert stubs[0].board == "g"


def test_fetch_thread_returns_none_on_404(monkeypatch):
    import requests

    class _Resp:
        status_code = 404

    def _raise_404(url):
        raise requests.HTTPError(response=_Resp())

    detail = fetch_thread("g", "404404404", json_fetcher=_raise_404)
    assert detail is None


def test_fetch_boards_batches_apify_shape_items():
    payload = fetch_boards(
        boards=["g", "biz"],
        json_fetcher=lambda url: CATALOG_PAYLOAD,
        sleep=lambda _s: None,
    )
    # 2 boards × 3 threads each = 6 items.
    assert len(payload["items"]) == 6
    assert all(item["dataType"] == "post" for item in payload["items"])
    # Sleep between boards is bypassed via the sleep injector — test just
    # verifies the function tolerates it.
    assert payload["apify_run_id"] is None


def test_thread_to_items_emits_post_then_comments():
    detail = parse_thread("g", THREAD_PAYLOAD)
    items = list(thread_to_items(detail))
    assert items[0]["dataType"] == "post"
    assert items[1]["dataType"] == "comment"
    assert items[1]["comment_url"].endswith("#p101")
