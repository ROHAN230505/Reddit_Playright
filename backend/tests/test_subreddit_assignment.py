"""POST /accounts/auto-assign-subreddits — LPT bin-packing of tracked
subreddits across enabled accounts, weighted by posts in the last 7 days."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.db.models import Post, RedditAccount, TrackedSubreddit
from app.routes import proxies as proxies_route


@pytest.fixture(autouse=True)
def _stub_validate(monkeypatch):
    monkeypatch.setattr(
        proxies_route,
        "validate_proxy",
        lambda **kw: (True, "203.0.113.42", None),
    )


def _create_account(client, username):
    resp = client.post(
        "/accounts",
        json={"username": username, "password": "p"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _track_subreddit(db_session, name: str) -> TrackedSubreddit:
    """Insert a TrackedSubreddit directly. We don't go through the API because
    the /tracked-subreddits handler seeds a default list on every call, which
    drowns out the test fixture data."""
    item = TrackedSubreddit(name=name)
    db_session.add(item)
    db_session.commit()
    return item


def _seed_recent_posts(db_session, subreddit: str, count: int, days_ago: float = 1.0):
    """Insert `count` Posts for the given subreddit at `days_ago` in the past."""
    base = datetime.utcnow() - timedelta(days=days_ago)
    for n in range(count):
        post = Post(
            subreddit=subreddit,
            title=f"post {subreddit}/{n}",
            url=f"https://reddit.com/r/{subreddit}/{n}-{base.timestamp()}",
            upvotes=1,
            number_of_comments=0,
            created_at=base,
        )
        db_session.add(post)
    db_session.commit()


def test_auto_assign_returns_400_when_no_accounts(client, db_session):
    _track_subreddit(db_session, "anysub")
    resp = client.post("/accounts/auto-assign-subreddits")
    assert resp.status_code == 400


def test_auto_assign_returns_empty_when_no_tracked(client):
    _create_account(client, "alone")
    resp = client.post("/accounts/auto-assign-subreddits")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_subreddits"] == 0
    assert len(body["assignments"]) == 1
    assert body["assignments"][0]["subreddits"] == []


def test_auto_assign_balances_load_via_lpt(client, db_session):
    a1 = _create_account(client, "lpt1")
    a2 = _create_account(client, "lpt2")
    # 4 subreddits with very uneven activity. LPT should pair big+small
    # together so the per-account loads converge.
    for name, weight in (("big", 100), ("medium", 60), ("small", 30), ("tiny", 10)):
        _track_subreddit(db_session, name)
        _seed_recent_posts(db_session, name, weight)

    resp = client.post("/accounts/auto-assign-subreddits")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_subreddits"] == 4

    by_account = {a["account_id"]: a for a in body["assignments"]}
    a1_subs = set(by_account[a1["id"]]["subreddits"])
    a2_subs = set(by_account[a2["id"]]["subreddits"])
    # Every tracked sub assigned somewhere, no overlap.
    assert a1_subs.union(a2_subs) == {"big", "medium", "small", "tiny"}
    assert not a1_subs.intersection(a2_subs)
    a1_load = by_account[a1["id"]]["posts_last_7d"]
    a2_load = by_account[a2["id"]]["posts_last_7d"]
    # The two heaviest subs must NOT land in the same bucket.
    assert max(a1_load, a2_load) < 100 + 60, "LPT failed to split the two heaviest subs"
    assert a1_load + a2_load == 200


def test_auto_assign_persists_into_account_row(client, db_session):
    acc = _create_account(client, "persist")
    _track_subreddit(db_session, "alpha")
    _track_subreddit(db_session, "beta")
    _seed_recent_posts(db_session, "alpha", 5)
    _seed_recent_posts(db_session, "beta", 1)

    resp = client.post("/accounts/auto-assign-subreddits")
    assert resp.status_code == 200

    db_session.expire_all()
    row = db_session.get(RedditAccount, acc["id"])
    assert row.assigned_subreddits is not None
    persisted = sorted(row.assigned_subreddits.split(","))
    assert persisted == ["alpha", "beta"]

    # And the GET endpoint reflects it.
    fetched = client.get(f"/accounts/{acc['id']}").json()
    assert sorted(fetched["assigned_subreddits"]) == ["alpha", "beta"]


def test_auto_assign_zero_activity_subreddits_still_get_assigned(client, db_session):
    a1 = _create_account(client, "zero1")
    a2 = _create_account(client, "zero2")
    _track_subreddit(db_session, "ghost1")
    _track_subreddit(db_session, "ghost2")
    _track_subreddit(db_session, "ghost3")
    # No posts seeded — every subreddit has 0 weight.
    resp = client.post("/accounts/auto-assign-subreddits")
    assert resp.status_code == 200
    body = resp.json()
    all_assigned = []
    for assn in body["assignments"]:
        all_assigned.extend(assn["subreddits"])
    assert sorted(all_assigned) == ["ghost1", "ghost2", "ghost3"]


def test_update_account_accepts_assigned_subreddits(client):
    acc = _create_account(client, "manual")
    resp = client.patch(
        f"/accounts/{acc['id']}",
        json={"assigned_subreddits": ["one", "two"]},
    )
    assert resp.status_code == 200
    assert sorted(resp.json()["assigned_subreddits"]) == ["one", "two"]
    # Empty list clears the assignment.
    resp = client.patch(
        f"/accounts/{acc['id']}",
        json={"assigned_subreddits": []},
    )
    assert resp.status_code == 200
    assert resp.json()["assigned_subreddits"] == []
