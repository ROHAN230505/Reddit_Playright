"""Per-account rate-limit enforcement on /worker/claim + cooldown setting on /worker/posted."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.db.models import RedditAccount, Reply
from app.routes import proxies as proxies_route


@pytest.fixture(autouse=True)
def _stub_validate(monkeypatch):
    monkeypatch.setattr(
        proxies_route,
        "validate_proxy",
        lambda **kw: (True, "203.0.113.42", None),
    )


def _create_account(
    client,
    username,
    *,
    posts_per_hour_limit=2,
    posts_per_day_limit=5,
    min_seconds_between_posts=10,
    max_seconds_between_posts=12,
):
    resp = client.post(
        "/accounts",
        json={
            "username": username,
            "password": "p",
            "posts_per_hour_limit": posts_per_hour_limit,
            "posts_per_day_limit": posts_per_day_limit,
            "min_seconds_between_posts": min_seconds_between_posts,
            "max_seconds_between_posts": max_seconds_between_posts,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_profile_index_auto_assigned_round_robin(client):
    a1 = _create_account(client, "rr1")
    a2 = _create_account(client, "rr2")
    a3 = _create_account(client, "rr3")
    assert a1["profile_index"] == 0
    assert a2["profile_index"] == 1
    assert a3["profile_index"] == 2
    # Each profile has a distinct summary.
    assert a1["profile_summary"] != a2["profile_summary"] != a3["profile_summary"]


def test_explicit_profile_index_overrides_round_robin(client):
    resp = client.post(
        "/accounts",
        json={"username": "explicit", "password": "p", "profile_index": 3},
    )
    assert resp.status_code == 200
    assert resp.json()["profile_index"] == 3


def test_profile_index_above_pool_size_is_rejected(client):
    """Pool is now 5 (slots 0..4); higher values must 422."""
    resp = client.post(
        "/accounts",
        json={"username": "outofrange", "password": "p", "profile_index": 7},
    )
    assert resp.status_code == 422


def test_claim_returns_null_when_account_in_cooldown(client, make_reply, db_session):
    a = _create_account(client, "cooldown")
    make_reply(status="APPROVED")
    # Manually pin next_eligible_at into the future.
    account = db_session.get(RedditAccount, a["id"])
    account.next_eligible_at = datetime.utcnow() + timedelta(seconds=120)
    db_session.add(account)
    db_session.commit()

    resp = client.post(
        "/worker/claim",
        json={"worker_name": "w1", "account_id": a["id"]},
    )
    assert resp.status_code == 200
    assert resp.json() is None


def test_claim_returns_null_when_account_at_hourly_limit(client, make_reply, db_session):
    a = _create_account(client, "hourly", posts_per_hour_limit=2)
    # Fabricate 2 already-posted replies attributed to this account in the last hour.
    now = datetime.utcnow()
    for _ in range(2):
        r = make_reply(status="POSTED")
        r.posting_account_id = a["id"]
        r.posted_at = now - timedelta(minutes=10)
        db_session.add(r)
    db_session.commit()

    # And one APPROVED waiting in queue.
    make_reply(status="APPROVED")

    resp = client.post(
        "/worker/claim",
        json={"worker_name": "w1", "account_id": a["id"]},
    )
    assert resp.status_code == 200
    assert resp.json() is None


def test_claim_returns_null_when_account_at_daily_limit(client, make_reply, db_session):
    a = _create_account(client, "daily", posts_per_hour_limit=100, posts_per_day_limit=3)
    now = datetime.utcnow()
    for _ in range(3):
        r = make_reply(status="POSTED")
        r.posting_account_id = a["id"]
        r.posted_at = now - timedelta(hours=12)
        db_session.add(r)
    db_session.commit()
    make_reply(status="APPROVED")

    resp = client.post(
        "/worker/claim",
        json={"worker_name": "w1", "account_id": a["id"]},
    )
    assert resp.status_code == 200
    assert resp.json() is None


def test_claim_succeeds_when_account_within_limits_and_records_account_id(
    client, make_reply, db_session
):
    a = _create_account(client, "ok")
    reply = make_reply(status="APPROVED")
    resp = client.post(
        "/worker/claim",
        json={"worker_name": "w1", "account_id": a["id"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body is not None and body["reply_id"] == reply.id
    db_session.expire_all()
    persisted = db_session.get(Reply, reply.id)
    assert persisted.posting_account_id == a["id"]


def test_mark_posted_sets_next_eligible_within_jitter_range(client, make_reply, db_session):
    a = _create_account(
        client,
        "cooldown_set",
        min_seconds_between_posts=60,
        max_seconds_between_posts=120,
    )
    reply = make_reply(status="APPROVED")
    # Claim it for the account.
    client.post(
        "/worker/claim",
        json={"worker_name": "w1", "account_id": a["id"]},
    )
    before_post = datetime.utcnow()
    resp = client.post(
        f"/worker/{reply.id}/posted",
        json={"worker_name": "w1"},
    )
    assert resp.status_code == 200

    db_session.expire_all()
    account = db_session.get(RedditAccount, a["id"])
    assert account.next_eligible_at is not None
    delta = (account.next_eligible_at - before_post).total_seconds()
    # Allow a generous boundary because the request roundtrip + the random
    # uniform should land in [60, 120] from the moment posted_at was stamped.
    assert 55 <= delta <= 130, f"cooldown delta out of range: {delta}s"


def test_activity_endpoint_returns_recent_posts_and_limits(client, make_reply, db_session):
    a = _create_account(client, "activity", posts_per_hour_limit=5, posts_per_day_limit=20)
    now = datetime.utcnow()
    # 3 posted in last hour, 2 more in last day-but-not-hour.
    for offset in (5, 30, 50):
        r = make_reply(status="POSTED", subreddit="testsub")
        r.posting_account_id = a["id"]
        r.posted_at = now - timedelta(minutes=offset)
        db_session.add(r)
    for hours_ago in (3, 10):
        r = make_reply(status="POSTED", subreddit="testsub")
        r.posting_account_id = a["id"]
        r.posted_at = now - timedelta(hours=hours_ago)
        db_session.add(r)
    db_session.commit()

    resp = client.get(f"/accounts/{a['id']}/activity")
    assert resp.status_code == 200
    body = resp.json()
    assert body["posts_last_hour"] == 3
    assert body["posts_last_day"] == 5
    assert body["posts_per_hour_limit"] == 5
    assert body["is_at_hourly_limit"] is False
    assert body["is_at_daily_limit"] is False
    assert len(body["recent_posts"]) == 5
    assert body["last_posted_at"] is not None


def test_accounts_health_returns_batched_activity(client, make_reply, db_session):
    first = _create_account(client, "health1", posts_per_hour_limit=5, posts_per_day_limit=20)
    second = _create_account(client, "health2", posts_per_hour_limit=5, posts_per_day_limit=20)
    now = datetime.utcnow()
    for account_id, minutes_ago in ((first["id"], 5), (second["id"], 15)):
        reply = make_reply(status="POSTED", subreddit="testsub")
        reply.posting_account_id = account_id
        reply.posted_at = now - timedelta(minutes=minutes_ago)
        db_session.add(reply)
    db_session.commit()

    resp = client.get("/accounts/health")

    assert resp.status_code == 200
    body = resp.json()
    assert {account["id"] for account in body["accounts"]} >= {first["id"], second["id"]}
    assert str(first["id"]) in body["activity"]
    assert str(second["id"]) in body["activity"]
    assert body["activity"][str(first["id"])]["posts_last_hour"] == 1
    assert body["activity"][str(second["id"])]["posts_last_hour"] == 1
    assert any(item["account"]["id"] == first["id"] for item in body["items"])
