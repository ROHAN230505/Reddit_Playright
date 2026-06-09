"""4chan auto-approve + scrape-now endpoint + prompt selection."""

from __future__ import annotations

import pytest

from app.config import settings
from app.db.models import Comment, Post, Reply
from app.services import processor
from app.services.processor import (
    _SYSTEM_PROMPT,
    _SYSTEM_PROMPT_CHAN,
    _SYSTEM_PROMPT_GLP,
    _build_reply_prompt,
    generate_reply,
)


@pytest.fixture(autouse=True)
def _stub_llm(monkeypatch):
    monkeypatch.setattr(processor, "classify_ai_relevance", lambda _text: True)
    monkeypatch.setattr(processor, "should_insert_promo", lambda: False)


def _seed_thread(db_session) -> Comment:
    post = Post(
        subreddit="g",  # 4chan board lands in the same column
        title="AI thread",
        url="https://boards.4chan.org/g/thread/42",
        upvotes=0,
        number_of_comments=1,
    )
    db_session.add(post)
    db_session.flush()
    comment = Comment(
        post_id=post.id,
        text="anyone using ai agents for work?",
        comment_url="https://boards.4chan.org/g/thread/42#p43",
        post_url=post.url,
        author="Anonymous",
        upvotes=0,
    )
    db_session.add(comment)
    db_session.commit()
    db_session.refresh(comment)
    return comment


def test_chan_save_reply_lands_approved_by_default(db_session, monkeypatch):
    monkeypatch.setattr(settings, "chan_auto_approve", True)
    comment = _seed_thread(db_session)
    saved = processor.save_reply(
        db_session,
        comment_id=comment.id,
        reply_text="nah, they all suck",
        is_ai_relevant=True,
        includes_promo=False,
        platform="chan",
        status="APPROVED",
    )
    assert saved is not None
    row = db_session.get(Reply, saved.id)
    assert row.platform == "chan"
    assert row.status == "APPROVED"
    # platform_post_id should be set from the parsed thread URL.
    assert row.platform_post_id == "42"
    assert row.platform_comment_id == "43"


def test_chan_scrape_now_endpoint(client, monkeypatch):
    captured: dict = {}

    class _FakeTask:
        id = "chan-task-1"

    def _fake_delay(*args, **kwargs):
        captured["args"] = args
        return _FakeTask()

    import worker.tasks as worker_tasks
    monkeypatch.setattr(worker_tasks.process_chan_job, "delay", _fake_delay)

    resp = client.post("/chan/scrape-now?threads_per_board=5")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["task_id"] == "chan-task-1"
    assert body["threads_per_board"] == 5
    assert "boards" in body


def test_chan_config_endpoint(client):
    resp = client.get("/chan/config")
    assert resp.status_code == 200
    body = resp.json()
    assert "auto_approve" in body
    assert "boards" in body
    assert "threads_per_board" in body


def test_chan_prompt_uses_chan_voice():
    prompt = _build_reply_prompt("they say AI is taking jobs", include_promo=False, platform="chan")
    assert "anon" in prompt.lower() or "imageboard" in prompt.lower() or "greentext" in prompt.lower()
    # Must not carry Reddit framing.
    assert "Reddit user" not in prompt
    # Must not carry GLP framing.
    assert "GLP poster" not in prompt


def test_chan_system_prompt_is_distinct():
    assert _SYSTEM_PROMPT_CHAN != _SYSTEM_PROMPT
    assert _SYSTEM_PROMPT_CHAN != _SYSTEM_PROMPT_GLP


def test_generate_reply_chan_uses_chan_system_prompt(monkeypatch):
    captured: dict = {"system_prompts": []}

    def _fake(prompt, system_prompt=None):
        captured["system_prompts"].append(system_prompt)
        return "kek, nah"

    monkeypatch.setattr("app.services.processor.deepseek_call", _fake)
    out = generate_reply("ai is replacing everyone", include_promo=False, platform="chan")
    assert out
    assert captured["system_prompts"][0] == _SYSTEM_PROMPT_CHAN
