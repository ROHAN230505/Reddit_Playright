from datetime import datetime

from app.db.models import Comment, Post, Reply, ScrapeRun, TrackedSubreddit


def test_patch_reply_text_and_status(client, make_reply):
    pending = make_reply(status="PENDING", reply_text="Original draft")

    resp = client.patch(
        f"/replies/{pending.id}",
        json={"status": "DONE", "reply_text": "Edited draft"},
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "DONE"
    done_items = client.get("/replies", params={"status": "DONE"}).json()
    assert len(done_items) == 1
    assert done_items[0]["reply_text"] == "Edited draft"


def test_dashboard_summary_counts_and_latest_errors(client, db_session):
    db_session.add(TrackedSubreddit(name="python"))
    post = Post(
        subreddit="python",
        title="Useful thread",
        url="https://www.reddit.com/r/python/comments/a/useful/",
        upvotes=10,
        number_of_comments=2,
        created_at=datetime(2026, 1, 1),
    )
    db_session.add(post)
    db_session.commit()
    db_session.refresh(post)

    comment = Comment(
        post_id=post.id,
        text="Helpful comment",
        comment_url="https://www.reddit.com/r/python/comments/a/useful/b/",
        post_url=post.url,
        author="someone",
        upvotes=5,
    )
    db_session.add(comment)
    db_session.commit()
    db_session.refresh(comment)

    db_session.add_all(
        [
            Reply(comment_id=comment.id, reply_text="Promo", is_ai_relevant=True, includes_promo=True, status="PENDING"),
            Reply(comment_id=comment.id, reply_text="Normal", is_ai_relevant=True, includes_promo=False, status="DONE"),
            ScrapeRun(
                subreddit="python",
                source="manual_selected",
                limit=5,
                status="FAILED",
                posts_count=1,
                comments_count=1,
                replies_count=2,
                error_message="Apify failed",
                created_at=datetime(2026, 1, 2),
            ),
            ScrapeRun(
                subreddit="python",
                source="manual_selected",
                limit=5,
                status="SUCCEEDED",
                posts_count=1,
                comments_count=1,
                replies_count=2,
                finished_at=datetime(2026, 1, 3),
                created_at=datetime(2026, 1, 3),
            ),
        ]
    )
    db_session.commit()

    body = client.get("/dashboard/summary").json()

    assert body["total_subreddits"] == 1
    assert body["total_posts"] == 1
    assert body["total_comments"] == 1
    assert body["reply_counts"]["PENDING"] == 1
    assert body["reply_counts"]["DONE"] == 1
    assert body["promo_replies"] == 1
    assert body["normal_replies"] == 1
    assert body["promo_ratio"] == 0.5
    assert body["latest_scrape_time"].startswith("2026-01-03")
    assert body["latest_scrape_errors"][0]["error_message"] == "Apify failed"


def test_bulk_reply_update(client, make_reply):
    first = make_reply(status="PENDING")
    second = make_reply(status="PENDING")

    resp = client.patch(
        "/replies/bulk/status",
        json={"reply_ids": [first.id, second.id], "status": "DONE"},
    )

    assert resp.status_code == 200
    assert resp.json()["updated"] == 2
    done_items = client.get("/replies", params={"status": "DONE"}).json()
    assert {item["reply_id"] for item in done_items} == {first.id, second.id}


def test_dashboard_search_and_subreddit_health(client, db_session):
    db_session.add(TrackedSubreddit(name="python"))
    post = Post(
        subreddit="python",
        title="Need a practical automation tool",
        body="Looking for a way to reply faster.",
        url="https://www.reddit.com/r/python/comments/searchcase/tool/",
        upvotes=12,
        number_of_comments=1,
        created_at=datetime(2026, 2, 1),
    )
    db_session.add(post)
    db_session.commit()
    db_session.refresh(post)

    comment = Comment(
        post_id=post.id,
        text="Automation helps when the draft is reviewed.",
        comment_url=f"{post.url}comment/",
        post_url=post.url,
        author="reviewer",
        upvotes=4,
    )
    db_session.add(comment)
    db_session.commit()
    db_session.refresh(comment)

    db_session.add_all(
        [
            Reply(
                comment_id=comment.id,
                reply_text="Use a reviewed automation workflow.",
                is_ai_relevant=True,
                includes_promo=True,
                status="PENDING",
            ),
            ScrapeRun(
                subreddit="python",
                source="manual_selected",
                limit=5,
                status="SUCCEEDED",
                posts_count=1,
                comments_count=1,
                replies_count=1,
                finished_at=datetime(2026, 2, 2),
                created_at=datetime(2026, 2, 2),
            ),
        ]
    )
    db_session.commit()

    search = client.get("/dashboard/search", params={"q": "automation"}).json()
    assert {item["kind"] for item in search} >= {"post", "comment", "reply"}

    health = client.get("/dashboard/subreddit-health").json()
    assert health[0]["subreddit"] == "python"
    assert health[0]["total_posts"] == 1
    assert health[0]["total_comments"] == 1
    assert health[0]["pending_replies"] == 1
    assert health[0]["promo_replies"] == 1
    assert health[0]["latest_scrape_status"] == "SUCCEEDED"
