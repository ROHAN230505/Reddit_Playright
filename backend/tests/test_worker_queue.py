"""Tests for the /worker/* queue endpoints (claim, posted, failed)."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.db.models import Reply


def test_claim_returns_null_when_queue_empty(client):
    resp = client.post("/worker/claim", json={"worker_name": "w1"})
    assert resp.status_code == 200
    assert resp.json() is None


def test_claim_returns_only_approved_replies(client, make_reply):
    pending = make_reply(status="PENDING")
    approved = make_reply(status="APPROVED")
    posted = make_reply(status="POSTED")

    resp = client.post("/worker/claim", json={"worker_name": "w1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body is not None
    assert body["reply_id"] == approved.id

    # Once claimed, status flips to POSTING and counters update.
    resp2 = client.get("/replies", params={"status": "POSTING"})
    assert resp2.status_code == 200
    items = resp2.json()
    assert len(items) == 1
    assert items[0]["reply_id"] == approved.id
    assert items[0]["posting_attempts"] == 1
    assert items[0]["posting_claimed_by"] == "w1"

    # PENDING and POSTED are untouched.
    pending_items = client.get("/replies", params={"status": "PENDING"}).json()
    posted_items = client.get("/replies", params={"status": "POSTED"}).json()
    assert {item["reply_id"] for item in pending_items} == {pending.id}
    assert {item["reply_id"] for item in posted_items} == {posted.id}


def test_claim_is_atomic_under_concurrent_claims(client, make_reply):
    """Two claim calls back-to-back must not return the same reply twice."""
    r1 = make_reply(status="APPROVED")
    r2 = make_reply(status="APPROVED")

    first = client.post("/worker/claim", json={"worker_name": "w1"}).json()
    second = client.post("/worker/claim", json={"worker_name": "w2"}).json()
    third = client.post("/worker/claim", json={"worker_name": "w3"}).json()

    assert first is not None
    assert second is not None
    assert third is None  # only two approved drafts exist

    assert {first["reply_id"], second["reply_id"]} == {r1.id, r2.id}


def test_posted_drafts_are_never_returned_again(client, make_reply):
    reply = make_reply(status="APPROVED")
    claim = client.post("/worker/claim", json={"worker_name": "w1"}).json()
    assert claim is not None

    resp = client.post(
        f"/worker/{reply.id}/posted",
        json={"worker_name": "w1", "posted_reddit_comment_id": "t1_xyz"},
    )
    assert resp.status_code == 200

    # A subsequent claim must not return the posted draft.
    again = client.post("/worker/claim", json={"worker_name": "w1"}).json()
    assert again is None


def test_mark_posted_is_idempotent(client, make_reply):
    reply = make_reply(status="APPROVED")
    client.post("/worker/claim", json={"worker_name": "w1"})
    client.post(f"/worker/{reply.id}/posted", json={"worker_name": "w1"})

    # Calling mark-posted again should succeed without changing state.
    resp = client.post(f"/worker/{reply.id}/posted", json={"worker_name": "w1"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "POSTED"


def test_mark_posted_rejects_other_workers(client, make_reply):
    reply = make_reply(status="APPROVED")
    client.post("/worker/claim", json={"worker_name": "w1"})

    resp = client.post(f"/worker/{reply.id}/posted", json={"worker_name": "intruder"})
    assert resp.status_code == 409


def test_mark_posted_rejects_unclaimed_replies(client, make_reply):
    reply = make_reply(status="APPROVED")
    resp = client.post(f"/worker/{reply.id}/posted", json={"worker_name": "w1"})
    assert resp.status_code == 409


def test_mark_failed_requeues_to_approved_by_default(client, make_reply):
    reply = make_reply(status="APPROVED")
    client.post("/worker/claim", json={"worker_name": "w1"})

    resp = client.post(
        f"/worker/{reply.id}/failed",
        json={"worker_name": "w1", "error": "selector timeout"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "APPROVED"
    assert body["posting_error"] == "selector timeout"

    # The next claim picks it up again.
    again = client.post("/worker/claim", json={"worker_name": "w2"}).json()
    assert again is not None
    assert again["reply_id"] == reply.id
    assert again["posting_attempts"] == 2


def test_mark_failed_without_requeue_holds_in_failed(client, make_reply):
    reply = make_reply(status="APPROVED")
    client.post("/worker/claim", json={"worker_name": "w1"})

    resp = client.post(
        f"/worker/{reply.id}/failed",
        json={"worker_name": "w1", "error": "permanent", "requeue": False},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "FAILED"

    # The worker should not pick it up again until the operator re-approves.
    nxt = client.post("/worker/claim", json={"worker_name": "w2"}).json()
    assert nxt is None


def test_stale_claim_recovery(client, make_reply, db_session):
    """A reply stuck in POSTING for too long should be re-claimable by another
    worker so jobs aren't lost when a worker dies mid-run."""
    reply = make_reply(status="APPROVED")
    first = client.post(
        "/worker/claim",
        json={"worker_name": "dead-worker", "stale_after_seconds": 600},
    ).json()
    assert first is not None

    # Simulate the original worker dying — manually backdate the claim.
    db_reply = db_session.get(Reply, reply.id)
    db_reply.posting_claimed_at = datetime.utcnow() - timedelta(hours=2)
    db_session.add(db_reply)
    db_session.commit()

    recovered = client.post(
        "/worker/claim",
        json={"worker_name": "fresh-worker", "stale_after_seconds": 60},
    ).json()
    assert recovered is not None
    assert recovered["reply_id"] == reply.id
    assert recovered["posting_claimed_by"] == "fresh-worker"
    assert recovered["posting_attempts"] == 2


def test_existing_replies_endpoint_still_works(client, make_reply):
    """Backward compatibility: the original GET /replies?status=PENDING flow
    still returns drafts and exposes the new posting fields as nullable."""
    pending = make_reply(status="PENDING")
    items = client.get("/replies", params={"status": "PENDING"}).json()
    assert len(items) == 1
    item = items[0]
    assert item["reply_id"] == pending.id
    assert "status" in item
    # New posting fields are present on the response (None for un-posted drafts).
    assert "posting_attempts" in item
    assert "posted_at" in item
    assert item["posted_at"] is None


def test_existing_patch_status_still_works(client, make_reply):
    """Original PATCH /replies/{id} still updates status (PENDING → DONE)."""
    pending = make_reply(status="PENDING")
    resp = client.patch(f"/replies/{pending.id}", json={"status": "DONE"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "DONE"

    done_items = client.get("/replies", params={"status": "DONE"}).json()
    assert len(done_items) == 1
    assert done_items[0]["reply_id"] == pending.id


def test_patch_to_approved_makes_it_claimable(client, make_reply):
    """Approving a PENDING reply via PATCH must make it visible to the worker."""
    pending = make_reply(status="PENDING")
    client.patch(f"/replies/{pending.id}", json={"status": "APPROVED"})

    resp = client.post("/worker/claim", json={"worker_name": "w1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body is not None
    assert body["reply_id"] == pending.id


def test_queue_summary_counts(client, make_reply):
    make_reply(status="APPROVED")
    make_reply(status="APPROVED")
    make_reply(status="POSTED")
    make_reply(status="FAILED")

    counts = client.get("/worker/queue").json()["counts"]
    assert counts["APPROVED"] == 2
    assert counts["POSTED"] == 1
    assert counts["FAILED"] == 1
    assert counts["POSTING"] == 0
