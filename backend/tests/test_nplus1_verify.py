"""Regression guards for the Reddit-page load path.

1. GET /replies must eager-load comment+post. The serialization loop reads
   reply.comment and comment.post for every row; without contains_eager that's
   an N+1 (1 + rows*2 SELECTs), which made the Reddit page — the only platform
   that fills the 2000-row cap — load slowly.
2. GET /replies/summary must be the lightweight projection the analytics/feed
   views use: single-table, newest-first, only the fields they read.
"""

from contextlib import contextmanager

from sqlalchemy import event

from app.db.session import engine


@contextmanager
def count_selects():
    counts = {"n": 0}

    def _count(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            counts["n"] += 1

    event.listen(engine, "before_cursor_execute", _count)
    try:
        yield counts
    finally:
        event.remove(engine, "before_cursor_execute", _count)


def test_get_replies_is_constant_query_count(client, make_reply):
    for _ in range(40):
        make_reply(status="POSTED")

    with count_selects() as counts:
        resp = client.get(
            "/replies?status=POSTED&limit=2000&order=newest&platform=reddit"
        )

    assert resp.status_code == 200
    assert len(resp.json()) == 40
    # One eager-loaded query, not 1 + 40*2. Small margin for framework selects.
    assert counts["n"] <= 5, f"N+1 regression: {counts['n']} SELECTs for 40 rows"


SUMMARY_FIELDS = {
    "reply_id",
    "reply_text",
    "includes_promo",
    "status",
    "created_at",
    "subreddit",
    "posted_at",
    "posted_url",
    "platform",
    "platform_section",
}


def test_summary_is_single_lightweight_query(client, make_reply):
    for _ in range(40):
        make_reply(status="POSTED")

    with count_selects() as counts:
        resp = client.get("/replies/summary?status=POSTED&limit=2000&platform=reddit")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 40
    # Single-table select — no comment/post JOIN, no per-row lazy loads.
    assert counts["n"] <= 2, f"summary did more queries than expected: {counts['n']}"
    # Carries exactly the fields the dashboard reads, and none of the heavy ones.
    assert set(body[0].keys()) == SUMMARY_FIELDS
    assert "post_body" not in body[0] and "comment_text" not in body[0]


def test_summary_filters_and_orders(client, make_reply, db_session):
    from datetime import datetime, timedelta

    older = make_reply(status="POSTED")
    newer = make_reply(status="POSTED")
    make_reply(status="PENDING")  # excluded by the status filter

    base = datetime(2026, 1, 1, 12, 0, 0)
    db_session.get(type(older), older.id).posted_at = base
    db_session.get(type(newer), newer.id).posted_at = base + timedelta(hours=1)
    db_session.commit()

    resp = client.get("/replies/summary?status=POSTED&platform=reddit")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 2
    assert all(r["status"] == "POSTED" for r in rows)
    # Newest posted_at first.
    assert rows[0]["reply_id"] == newer.id
    assert rows[1]["reply_id"] == older.id
