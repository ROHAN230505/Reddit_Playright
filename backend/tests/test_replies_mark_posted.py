"""POST /replies/{id}/mark-posted — operator marks a reply as posted by a
specific account, applying cooldown after the manual free-burst allowance."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.db.models import RedditAccount, Reply
from app.routes import proxies as proxies_route


VALID_URL = "https://www.reddit.com/r/test/comments/abc123/some_title/comment_xyz/"


@pytest.fixture(autouse=True)
def _stub_validate(monkeypatch):
    monkeypatch.setattr(
        proxies_route,
        "validate_proxy",
        lambda **kw: (True, "203.0.113.42", None),
    )


def _create_account(client, username, **overrides):
    body = {
        "username": username,
        "password": "p",
        "posts_per_hour_limit": overrides.get("posts_per_hour_limit", 4),
        "posts_per_day_limit": overrides.get("posts_per_day_limit", 30),
        "min_seconds_between_posts": overrides.get("min_seconds_between_posts", 60),
        "max_seconds_between_posts": overrides.get("max_seconds_between_posts", 90),
    }
    resp = client.post("/accounts", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_mark_posted_sets_posted_status_and_account_without_initial_cooldown(client, make_reply, db_session):
    account = _create_account(client, "live1")
    reply = make_reply(status="PENDING")
    before = datetime.utcnow()
    resp = client.post(
        f"/replies/{reply.id}/mark-posted",
        json={"account_id": account["id"], "posted_url": VALID_URL},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "POSTED"
    assert body["posted_url"] == VALID_URL

    db_session.expire_all()
    persisted = db_session.get(Reply, reply.id)
    assert persisted.status == "POSTED"
    assert persisted.posting_account_id == account["id"]
    assert persisted.posted_at is not None
    assert persisted.posted_url == VALID_URL
    # First post in the free-burst window does not apply cooldown.
    acc_row = db_session.get(RedditAccount, account["id"])
    assert acc_row.next_eligible_at is None


def test_mark_posted_applies_cooldown_on_third_burst_post(client, make_reply, db_session):
    account = _create_account(client, "live_burst")
    replies = [make_reply(status="PENDING") for _ in range(3)]
    before = datetime.utcnow()

    for reply in replies:
        resp = client.post(
            f"/replies/{reply.id}/mark-posted",
            json={"account_id": account["id"], "posted_url": VALID_URL},
        )
        assert resp.status_code == 200, resp.text

    db_session.expire_all()
    acc_row = db_session.get(RedditAccount, account["id"])
    assert acc_row.next_eligible_at is not None
    delta = (acc_row.next_eligible_at - before).total_seconds()
    assert 55 <= delta <= 100, f"cooldown delta {delta}s outside [60,90] jitter window"


def test_mark_posted_supports_optional_text_override(client, make_reply, db_session):
    account = _create_account(client, "live2")
    reply = make_reply(status="PENDING", reply_text="original draft")
    resp = client.post(
        f"/replies/{reply.id}/mark-posted",
        json={
            "account_id": account["id"],
            "posted_url": VALID_URL,
            "reply_text": "edited and posted",
        },
    )
    assert resp.status_code == 200
    db_session.expire_all()
    persisted = db_session.get(Reply, reply.id)
    assert persisted.reply_text == "edited and posted"


def test_mark_posted_idempotent(client, make_reply, db_session):
    account = _create_account(client, "live3")
    reply = make_reply(status="PENDING")
    first = client.post(
        f"/replies/{reply.id}/mark-posted",
        json={"account_id": account["id"], "posted_url": VALID_URL},
    )
    assert first.status_code == 200
    # Seed a cooldown so we can verify an idempotent second call doesn't shift it.
    db_session.expire_all()
    acc_before = db_session.get(RedditAccount, account["id"])
    pinned = datetime.utcnow() + timedelta(seconds=90)
    acc_before.next_eligible_at = pinned
    db_session.add(acc_before)
    db_session.commit()

    second = client.post(
        f"/replies/{reply.id}/mark-posted",
        json={"account_id": account["id"], "posted_url": VALID_URL},
    )
    assert second.status_code == 200
    db_session.expire_all()
    acc_after = db_session.get(RedditAccount, account["id"])
    assert acc_after.next_eligible_at == pinned, (
        "second mark-posted should not re-apply cooldown"
    )


def test_mark_posted_missing_account_returns_404(client, make_reply):
    reply = make_reply(status="PENDING")
    resp = client.post(
        f"/replies/{reply.id}/mark-posted",
        json={"account_id": 999999, "posted_url": VALID_URL},
    )
    assert resp.status_code == 404


def test_mark_posted_counts_against_hourly_limit(client, make_reply, db_session):
    account = _create_account(client, "live4", posts_per_hour_limit=2)
    r1 = make_reply(status="PENDING")
    r2 = make_reply(status="PENDING")
    # Mark both posted by the account.
    for r in (r1, r2):
        resp = client.post(
            f"/replies/{r.id}/mark-posted",
            json={"account_id": account["id"], "posted_url": VALID_URL},
        )
        assert resp.status_code == 200

    activity = client.get(f"/accounts/{account['id']}/activity").json()
    assert activity["posts_last_hour"] == 2
    assert activity["is_at_hourly_limit"] is True


def test_mark_posted_requires_posted_url(client, make_reply):
    account = _create_account(client, "live_url_required")
    reply = make_reply(status="PENDING")
    resp = client.post(
        f"/replies/{reply.id}/mark-posted",
        json={"account_id": account["id"]},
    )
    assert resp.status_code == 422


@pytest.mark.parametrize(
    "bad_url",
    [
        "not a url",
        "https://example.com/r/test/comments/abc/x/y/",
        "https://www.reddit.com/r/test/",  # no /comments/ path
        "ftp://www.reddit.com/r/test/comments/abc/",
        "",
        "   ",
    ],
)
def test_mark_posted_rejects_invalid_posted_url(client, make_reply, bad_url):
    account = _create_account(client, f"live_bad_{abs(hash(bad_url))}")
    reply = make_reply(status="PENDING")
    resp = client.post(
        f"/replies/{reply.id}/mark-posted",
        json={"account_id": account["id"], "posted_url": bad_url},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.parametrize(
    "good_url",
    [
        "https://www.reddit.com/r/test/comments/abc123/title/comment_xyz/",
        "https://old.reddit.com/r/test/comments/abc123/_/comment_xyz",
        "https://reddit.com/r/test/comments/abc123/",
        "http://np.reddit.com/r/test/comments/abc123/x/y/",
    ],
)
def test_mark_posted_accepts_reddit_variants(client, make_reply, good_url):
    account = _create_account(client, f"live_ok_{abs(hash(good_url))}")
    reply = make_reply(status="PENDING")
    resp = client.post(
        f"/replies/{reply.id}/mark-posted",
        json={"account_id": account["id"], "posted_url": good_url},
    )
    assert resp.status_code == 200, resp.text
