"""Test fixtures: isolated SQLite DB + FastAPI TestClient.

Each test gets a fresh in-memory database via SQLAlchemy's StaticPool, so
tests are fully isolated and parallelizable.
"""

import os
import sys
from pathlib import Path

# Use a fresh on-disk SQLite database for each test session BEFORE importing
# the app (which reads DATABASE_URL at import time).
TEST_DB_PATH = Path(__file__).parent / "_test.sqlite"
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"

# Default Fernet key so the accounts/proxies routes can encrypt during tests.
if not os.environ.get("ACCOUNT_ENCRYPTION_KEY"):
    from cryptography.fernet import Fernet  # noqa: E402
    os.environ["ACCOUNT_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

# Make `app` importable (the FastAPI package lives at backend/app/).
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.models import Comment, Post, Reply  # noqa: E402
from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def make_reply(db_session):
    """Factory returning a function that creates a Post + Comment + Reply."""

    counter = {"n": 0}

    def _make(
        status: str = "APPROVED",
        subreddit: str = "TestSubreddit",
        comment_url: str | None = None,
        post_url: str | None = None,
        reply_text: str = "Hello world reply",
        target_type: str | None = None,
        target_url: str | None = None,
        posting_attempts: int = 0,
    ) -> Reply:
        counter["n"] += 1
        n = counter["n"]
        post_url = post_url or f"https://www.reddit.com/r/{subreddit}/comments/post{n}/slug/"
        comment_url = comment_url or f"{post_url}commentid{n}/"

        post = Post(
            subreddit=subreddit,
            title=f"Test Post {n}",
            url=post_url,
            upvotes=5,
            number_of_comments=2,
        )
        db_session.add(post)
        db_session.commit()
        db_session.refresh(post)

        comment = Comment(
            post_id=post.id,
            text=f"Comment text {n}",
            comment_url=comment_url,
            post_url=post_url,
            author=f"user{n}",
            upvotes=1,
        )
        db_session.add(comment)
        db_session.commit()
        db_session.refresh(comment)

        reply = Reply(
            comment_id=comment.id,
            reply_text=reply_text,
            is_ai_relevant=True,
            includes_promo=False,
            status=status,
            target_type=target_type or ("comment" if comment_url else "post"),
            target_url=target_url or comment_url or post_url,
            subreddit=subreddit,
            posting_attempts=posting_attempts,
        )
        db_session.add(reply)
        db_session.commit()
        db_session.refresh(reply)
        return reply

    return _make
