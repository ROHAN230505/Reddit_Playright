from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import inspect, text

from app.config import settings
from app.db import models  # noqa: F401
from app.db.session import Base, engine
from app.routes.dashboard import router as dashboard_router
from app.routes.fetch import router as fetch_router
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

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


Base.metadata.create_all(bind=engine)
_ensure_runtime_columns()

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(dashboard_router)
app.include_router(fetch_router)
app.include_router(replies_router)
app.include_router(scrape_runs_router)
app.include_router(subreddits_router)
app.include_router(tracked_subreddits_router)
app.include_router(worker_router)


@app.get("/health")
def healthcheck():
    return {"status": "ok"}
