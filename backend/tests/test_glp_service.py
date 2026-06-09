"""Tests for GLP scrape parsing.

Live HTTP is never made — every test passes canned HTML via the `html_fetcher`
seam so the suite runs in CI without a residential proxy.
"""

from __future__ import annotations

from app.services.glp_service import (
    fetch_newthreads,
    fetch_thread,
    parse_newthreads_html,
    parse_thread_html,
    thread_to_items,
)


NEWTHREADS_SNIPPET = """
<html><body>
<table class="threads">
  <tr><td><a href="/forum1/message1234567/pg1">First Cool Thread</a></td></tr>
  <tr><td><a href="/forum1/message9876543">Another One</a></td></tr>
  <tr><td><a href="/forum1/message1234567/pg1">Dupe Should Be Skipped</a></td></tr>
  <tr><td><a href="/some/other/path">not a thread</a></td></tr>
</table>
</body></html>
"""


# Mirrors the real GLP thread-page markup (verified live 2026-06): each post is
# a <tr class="post_member_<id> post_uid_<uid>" id="post_<seq>"> with an author
# cell (a /members/<id>/profile link) and a content cell whose body lives in
# <div class="post_main">. The OP uses messagecontent, replies use replycontent.
THREAD_SNIPPET = """
<html><head><title>Cool Thread - Godlike Productions</title></head><body>
<table class="msg"><tbody>
<tr class="post_member_207430 post_uid_111000111" id="post_1">
  <td class="messageauthor"><div class="author_inner"><a href="/members/207430/profile">user_alpha</a></div></td>
  <td class="messagecontent"><div class="post_wrap"><div class="post_hdr"><b>Cool Thread</b></div><div class="post_main">first reply body</div></div></td>
</tr>
<tr class="post_member_308540 post_uid_111000222" id="post_2">
  <td class="messageauthor"><div class="author_inner"><a href="/members/308540/profile">user_beta</a></div></td>
  <td class="replycontent p1"><div class="post_wrap"><div class="post_hdr"><b>Re: Cool Thread</b></div><div class="post_main">second reply body</div></div></td>
</tr>
</tbody></table>
</body></html>
"""


def test_parse_newthreads_extracts_thread_stubs():
    stubs = parse_newthreads_html(NEWTHREADS_SNIPPET)
    assert len(stubs) == 2
    assert stubs[0].thread_id == "1234567"
    assert stubs[0].title == "First Cool Thread"
    assert stubs[0].url == "https://www.godlikeproductions.com/forum1/message1234567/pg1"
    assert stubs[1].thread_id == "9876543"


def test_fetch_newthreads_shapes_items_for_save_post():
    payload = fetch_newthreads(limit=10, html_fetcher=lambda url: NEWTHREADS_SNIPPET)
    items = payload["items"]
    assert len(items) == 2
    assert items[0]["dataType"] == "post"
    assert items[0]["url"].startswith("https://www.godlikeproductions.com/forum1/message")
    assert items[0]["title"]


def test_fetch_newthreads_respects_limit():
    payload = fetch_newthreads(limit=1, html_fetcher=lambda url: NEWTHREADS_SNIPPET)
    assert len(payload["items"]) == 1


def test_parse_thread_html_finds_posts():
    detail = parse_thread_html(THREAD_SNIPPET, thread_id="111000", page=1)
    assert detail is not None
    assert detail.thread_id == "111000"
    assert detail.op.post_id == "111000111"
    assert detail.op.author == "user_alpha"
    assert detail.op.body_text == "first reply body"
    assert len(detail.replies) == 1
    assert detail.replies[0].post_id == "111000222"
    assert detail.replies[0].author == "user_beta"
    assert detail.replies[0].body_text == "second reply body"


def test_parse_thread_html_returns_none_on_blank():
    assert parse_thread_html("<html>no posts</html>", thread_id="42") is None


def test_fetch_thread_uses_injected_fetcher():
    detail = fetch_thread("111000", page=2, html_fetcher=lambda url: THREAD_SNIPPET)
    assert detail is not None
    # The URL passed to the fetcher must point at pg2.
    assert detail.url.endswith("/pg2")


def test_thread_to_items_emits_post_then_comments():
    detail = parse_thread_html(THREAD_SNIPPET, thread_id="111000", page=1)
    items = list(thread_to_items(detail))
    assert items[0]["dataType"] == "post"
    assert items[1]["dataType"] == "comment"
    assert items[1]["comment_url"].endswith("#post_111000222")
