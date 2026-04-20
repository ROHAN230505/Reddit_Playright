from fastapi import FastAPI

from sqlalchemy import inspect, text

from app.config import settings
from app.db.session import Base, engine
from app.routes.fetch import router as fetch_router
from app.routes.replies import router as replies_router
from app.routes.subreddits import router as subreddits_router
from app.routes.tracked_subreddits import router as tracked_subreddits_router

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

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


Base.metadata.create_all(bind=engine)
_ensure_runtime_columns()

app = FastAPI(title=settings.app_name)
app.include_router(fetch_router)
app.include_router(replies_router)
app.include_router(subreddits_router)
app.include_router(tracked_subreddits_router)


@app.get("/health")
def healthcheck():
    return {"status": "ok"}
