"""Unit tests for Reddit URL → fullname extraction."""

from app.services.reddit_targets import (
    derive_reply_targets,
    extract_comment_id,
    extract_post_id,
    fullname_comment,
    fullname_post,
)


POST_URL = "https://www.reddit.com/r/MachineLearning/comments/abc123/some_slug/"
COMMENT_URL = "https://www.reddit.com/r/MachineLearning/comments/abc123/some_slug/def456/"


def test_extract_post_id_from_post_url():
    assert extract_post_id(POST_URL) == "abc123"


def test_extract_post_id_from_comment_url():
    assert extract_post_id(COMMENT_URL) == "abc123"


def test_extract_comment_id_from_comment_url():
    assert extract_comment_id(COMMENT_URL) == "def456"


def test_extract_comment_id_returns_none_for_post_url():
    assert extract_comment_id(POST_URL) is None


def test_fullname_helpers():
    assert fullname_post(POST_URL) == "t3_abc123"
    assert fullname_comment(COMMENT_URL) == "t1_def456"
    assert fullname_comment(POST_URL) is None


def test_handles_none_and_garbage():
    assert extract_post_id(None) is None
    assert extract_post_id("https://example.com/") is None
    assert fullname_post(None) is None
    assert derive_reply_targets(None, None, None) == {
        "target_url": None,
        "target_type": None,
        "reddit_post_id": None,
        "reddit_comment_id": None,
        "subreddit": None,
    }


def test_derive_reply_targets_for_comment():
    out = derive_reply_targets(COMMENT_URL, POST_URL, "MachineLearning")
    assert out["target_url"] == COMMENT_URL
    assert out["target_type"] == "comment"
    assert out["reddit_post_id"] == "t3_abc123"
    assert out["reddit_comment_id"] == "t1_def456"
    assert out["subreddit"] == "MachineLearning"


def test_derive_reply_targets_for_post_only():
    out = derive_reply_targets(None, POST_URL, "r/MachineLearning")
    assert out["target_url"] == POST_URL
    assert out["target_type"] == "post"
    assert out["reddit_post_id"] == "t3_abc123"
    assert out["reddit_comment_id"] is None
    assert out["subreddit"] == "MachineLearning"
