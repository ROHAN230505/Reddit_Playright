"""GLP auto-approve: drafts created by process_glp should land as APPROVED
by default so the Playwright worker picks them up automatically."""

from __future__ import annotations

import pytest

from app.config import settings
from app.db.models import Comment, Post, Reply
from app.services import processor


@pytest.fixture(autouse=True)
def _stub_llm(monkeypatch):
    # Make the classifier always say "relevant" and the generator return
    # a fixed string so we exercise the save_reply path deterministically.
    monkeypatch.setattr(processor, "classify_ai_relevance", lambda _text: True)
    monkeypatch.setattr(
        processor, "generate_reply", lambda comment, include_promo, platform="reddit": "yes, exactly."
    )
    monkeypatch.setattr(processor, "should_insert_promo", lambda: False)


def _seed_thread(db_session) -> Comment:
    post = Post(
        subreddit="glp",
        title="Test thread",
        url="https://www.godlikeproductions.com/forum1/message42/pg1",
        upvotes=0,
        number_of_comments=1,
    )
    db_session.add(post)
    db_session.flush()
    comment = Comment(
        post_id=post.id,
        text="they say AI is going to take over jobs",
        comment_url="https://www.godlikeproductions.com/forum1/message42/pg1#post_999",
        post_url=post.url,
        author="alpha",
        upvotes=0,
    )
    db_session.add(comment)
    db_session.commit()
    db_session.refresh(comment)
    return comment


def test_glp_save_reply_lands_approved_by_default(db_session, monkeypatch):
    monkeypatch.setattr(settings, "glp_auto_approve", True)
    comment = _seed_thread(db_session)
    saved = processor.save_reply(
        db_session,
        comment_id=comment.id,
        reply_text="yes, exactly.",
        is_ai_relevant=True,
        includes_promo=False,
        platform="glp",
        status="APPROVED",
    )
    assert saved is not None
    row = db_session.get(Reply, saved.id)
    assert row.platform == "glp"
    assert row.status == "APPROVED"


def test_glp_save_reply_respects_explicit_pending(db_session):
    """If the operator turns off auto-approve, process_glp passes PENDING."""
    comment = _seed_thread(db_session)
    saved = processor.save_reply(
        db_session,
        comment_id=comment.id,
        reply_text="yes, exactly.",
        is_ai_relevant=True,
        includes_promo=False,
        platform="glp",
        status="PENDING",
    )
    assert saved is not None
    row = db_session.get(Reply, saved.id)
    assert row.status == "PENDING"


def test_glp_scrape_now_endpoint_returns_task_id(client, monkeypatch):
    captured: dict = {}

    class _FakeTask:
        id = "fake-task-123"

    def _fake_delay(*args, **kwargs):
        captured["called"] = True
        captured["args"] = args
        return _FakeTask()

    import worker.tasks as worker_tasks

    monkeypatch.setattr(worker_tasks.process_glp_job, "delay", _fake_delay)
    resp = client.post("/glp/scrape-now?limit=10")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["task_id"] == "fake-task-123"
    assert body["limit"] == 10
    assert captured["called"] is True


def test_glp_config_reports_auto_approve_flag(client):
    resp = client.get("/glp/config")
    assert resp.status_code == 200
    assert "auto_approve" in resp.json()
