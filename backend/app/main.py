from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import inspect, text

from app.config import settings
from app.db import models  # noqa: F401
from app.db.session import Base, engine
from app.routes.accounts import router as accounts_router
from app.routes.dashboard import router as dashboard_router
from app.routes.chan import router as chan_router
from app.routes.fetch import router as fetch_router
from app.routes.glp import router as glp_router
from app.routes.proxies import router as proxies_router
from app.routes.replies import router as replies_router
from app.routes.scrape_runs import router as scrape_runs_router
from app.routes.subreddits import router as subreddits_router
from app.routes.tracked_subreddits import router as tracked_subreddits_router
from app.routes.worker import router as worker_router


def _ensure_runtime_columns():
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    statements: list[str] = []

    if "posts" in existing_tables:
        post_columns = {column["name"] for column in inspector.get_columns("posts")}
        if "body" not in post_columns:
            statements.append("ALTER TABLE posts ADD COLUMN body TEXT")
        if "upvotes" not in post_columns:
            statements.append("ALTER TABLE posts ADD COLUMN upvotes INTEGER DEFAULT 0")
        if "number_of_comments" not in post_columns:
            statements.append("ALTER TABLE posts ADD COLUMN number_of_comments INTEGER DEFAULT 0")

    if "comments" in existing_tables:
        comment_columns = {column["name"] for column in inspector.get_columns("comments")}
        if "upvotes" not in comment_columns:
            statements.append("ALTER TABLE comments ADD COLUMN upvotes INTEGER DEFAULT 0")

    if "scrape_runs" in existing_tables:
        scrape_run_columns = {column["name"] for column in inspector.get_columns("scrape_runs")}
        if "apify_run_id" not in scrape_run_columns:
            statements.append("ALTER TABLE scrape_runs ADD COLUMN apify_run_id VARCHAR(255)")
        if "posts_count" not in scrape_run_columns:
            statements.append("ALTER TABLE scrape_runs ADD COLUMN posts_count INTEGER DEFAULT 0")
        if "comments_count" not in scrape_run_columns:
            statements.append("ALTER TABLE scrape_runs ADD COLUMN comments_count INTEGER DEFAULT 0")
        if "replies_count" not in scrape_run_columns:
            statements.append("ALTER TABLE scrape_runs ADD COLUMN replies_count INTEGER DEFAULT 0")
        if "error_message" not in scrape_run_columns:
            statements.append("ALTER TABLE scrape_runs ADD COLUMN error_message TEXT")
        if "triggered_by" not in scrape_run_columns:
            statements.append("ALTER TABLE scrape_runs ADD COLUMN triggered_by VARCHAR(255)")
        if "finished_at" not in scrape_run_columns:
            statements.append("ALTER TABLE scrape_runs ADD COLUMN finished_at TIMESTAMP")

    if "replies" in existing_tables:
        reply_columns = {column["name"] for column in inspector.get_columns("replies")}
        if "target_type" not in reply_columns:
            statements.append("ALTER TABLE replies ADD COLUMN target_type VARCHAR(20)")
        if "target_url" not in reply_columns:
            statements.append("ALTER TABLE replies ADD COLUMN target_url VARCHAR(1000)")
        if "reddit_post_id" not in reply_columns:
            statements.append("ALTER TABLE replies ADD COLUMN reddit_post_id VARCHAR(50)")
        if "reddit_comment_id" not in reply_columns:
            statements.append("ALTER TABLE replies ADD COLUMN reddit_comment_id VARCHAR(50)")
        if "subreddit" not in reply_columns:
            statements.append("ALTER TABLE replies ADD COLUMN subreddit VARCHAR(255)")
        if "posting_attempts" not in reply_columns:
            statements.append("ALTER TABLE replies ADD COLUMN posting_attempts INTEGER DEFAULT 0")
        if "posting_claimed_at" not in reply_columns:
            statements.append("ALTER TABLE replies ADD COLUMN posting_claimed_at TIMESTAMP")
        if "posting_claimed_by" not in reply_columns:
            statements.append("ALTER TABLE replies ADD COLUMN posting_claimed_by VARCHAR(255)")
        if "posting_error" not in reply_columns:
            statements.append("ALTER TABLE replies ADD COLUMN posting_error TEXT")
        if "posted_at" not in reply_columns:
            statements.append("ALTER TABLE replies ADD COLUMN posted_at TIMESTAMP")
        if "posted_reddit_comment_id" not in reply_columns:
            statements.append("ALTER TABLE replies ADD COLUMN posted_reddit_comment_id VARCHAR(50)")
        if "posted_url" not in reply_columns:
            statements.append("ALTER TABLE replies ADD COLUMN posted_url VARCHAR(1000)")
        if "posting_account_id" not in reply_columns:
            statements.append("ALTER TABLE replies ADD COLUMN posting_account_id INTEGER")
        if "platform" not in reply_columns:
            statements.append(
                "ALTER TABLE replies ADD COLUMN platform VARCHAR(16) DEFAULT 'reddit'"
            )
        if "platform_post_id" not in reply_columns:
            statements.append("ALTER TABLE replies ADD COLUMN platform_post_id VARCHAR(64)")
        if "platform_comment_id" not in reply_columns:
            statements.append("ALTER TABLE replies ADD COLUMN platform_comment_id VARCHAR(64)")
        if "platform_section" not in reply_columns:
            statements.append("ALTER TABLE replies ADD COLUMN platform_section VARCHAR(255)")
        if "posted_platform_comment_id" not in reply_columns:
            statements.append(
                "ALTER TABLE replies ADD COLUMN posted_platform_comment_id VARCHAR(64)"
            )

    if "reddit_accounts" in existing_tables:
        account_columns = {column["name"] for column in inspector.get_columns("reddit_accounts")}
        if "session_cookies_enc" not in account_columns:
            statements.append("ALTER TABLE reddit_accounts ADD COLUMN session_cookies_enc TEXT")
        if "cookies_set_at" not in account_columns:
            statements.append("ALTER TABLE reddit_accounts ADD COLUMN cookies_set_at TIMESTAMP")
        if "profile_index" not in account_columns:
            statements.append("ALTER TABLE reddit_accounts ADD COLUMN profile_index INTEGER DEFAULT 0")
        if "posts_per_hour_limit" not in account_columns:
            statements.append("ALTER TABLE reddit_accounts ADD COLUMN posts_per_hour_limit INTEGER DEFAULT 4")
        if "posts_per_day_limit" not in account_columns:
            statements.append("ALTER TABLE reddit_accounts ADD COLUMN posts_per_day_limit INTEGER DEFAULT 30")
        if "min_seconds_between_posts" not in account_columns:
            statements.append("ALTER TABLE reddit_accounts ADD COLUMN min_seconds_between_posts INTEGER DEFAULT 300")
        if "max_seconds_between_posts" not in account_columns:
            statements.append("ALTER TABLE reddit_accounts ADD COLUMN max_seconds_between_posts INTEGER DEFAULT 900")
        if "next_eligible_at" not in account_columns:
            statements.append("ALTER TABLE reddit_accounts ADD COLUMN next_eligible_at TIMESTAMP")
        if "assigned_subreddits" not in account_columns:
            statements.append("ALTER TABLE reddit_accounts ADD COLUMN assigned_subreddits TEXT")
        if "platform" not in account_columns:
            statements.append(
                "ALTER TABLE reddit_accounts ADD COLUMN platform VARCHAR(16) DEFAULT 'reddit'"
            )
        if "assigned_sections" not in account_columns:
            statements.append("ALTER TABLE reddit_accounts ADD COLUMN assigned_sections TEXT")

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def _reslot_legacy_profiles():
    """One-shot idempotent migration: any enabled account with profile_index>=5
    (left over from when the pool was 10) gets reassigned to a 0-4 slot via
    round-robin against the current usage. Runs at startup; no-op if all
    enabled accounts are already in [0,4]."""
    from app.services.profile_pool import (  # noqa: WPS433
        PROFILE_POOL_SIZE,
        pick_next_profile_index,
    )

    with engine.begin() as connection:
        rows = list(
            connection.execute(
                text(
                    "SELECT id, profile_index, is_enabled FROM reddit_accounts ORDER BY id ASC"
                )
            )
        )
        enabled = [r for r in rows if bool(r.is_enabled)]
        if not enabled:
            return
        bad_ids = {
            r.id
            for r in enabled
            if r.profile_index is None or r.profile_index >= PROFILE_POOL_SIZE
        }
        if not bad_ids:
            return
        used = [r.profile_index for r in enabled if r.id not in bad_ids and r.profile_index is not None]
        for r in enabled:
            if r.id not in bad_ids:
                continue
            new_idx = pick_next_profile_index(used)
            connection.execute(
                text("UPDATE reddit_accounts SET profile_index = :p WHERE id = :i"),
                {"p": new_idx, "i": r.id},
            )
            used.append(new_idx)


Base.metadata.create_all(bind=engine)
_ensure_runtime_columns()
try:
    _reslot_legacy_profiles()
except Exception:  # noqa: BLE001
    # Don't crash the app on a best-effort migration; logs will surface it.
    pass

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(accounts_router)
app.include_router(dashboard_router)
app.include_router(chan_router)
app.include_router(fetch_router)
app.include_router(glp_router)
app.include_router(proxies_router)
app.include_router(replies_router)
app.include_router(scrape_runs_router)
app.include_router(subreddits_router)
app.include_router(tracked_subreddits_router)
app.include_router(worker_router)


@app.get("/health")
def healthcheck():
    return {"status": "ok"}
