"""Helpers for deriving exact Reddit target identifiers from URLs.

Reddit URLs follow predictable shapes:
    Post:    /r/<sub>/comments/<post_id>/<slug>/
    Comment: /r/<sub>/comments/<post_id>/<slug>/<comment_id>/

The Reddit "fullname" prefixes are:
    t1_ for comments, t3_ for posts.

These helpers are intentionally pure (no DB access, no network) so they
can be reused by the scrape pipeline, the worker routes, and tests.
"""

from urllib.parse import urlparse


def _path_parts(url: str | None) -> list[str]:
    if not url:
        return []
    parsed = urlparse(url)
    return [part for part in parsed.path.split("/") if part]


def _comments_index(parts: list[str]) -> int | None:
    try:
        return parts.index("comments")
    except ValueError:
        return None


def extract_post_id(url: str | None) -> str | None:
    """Return the bare Reddit post id (no prefix) from a post or comment URL."""
    parts = _path_parts(url)
    idx = _comments_index(parts)
    if idx is None or len(parts) < idx + 2:
        return None
    return parts[idx + 1] or None


def extract_comment_id(url: str | None) -> str | None:
    """Return the bare Reddit comment id (no prefix) from a comment URL."""
    parts = _path_parts(url)
    idx = _comments_index(parts)
    if idx is None or len(parts) < idx + 4:
        return None
    return parts[idx + 3] or None


def fullname_post(url: str | None) -> str | None:
    post_id = extract_post_id(url)
    return f"t3_{post_id}" if post_id else None


def fullname_comment(url: str | None) -> str | None:
    comment_id = extract_comment_id(url)
    return f"t1_{comment_id}" if comment_id else None


def derive_reply_targets(
    comment_url: str | None,
    post_url: str | None,
    subreddit: str | None,
) -> dict:
    """Return a dict with target_url, target_type, reddit_post_id,
    reddit_comment_id, subreddit derived from existing comment/post data.

    The reply target is the comment we want to reply to, so when a comment
    URL is known we treat target_type as 'comment' and target_url as that
    comment URL. When only a post URL exists, we reply at the post level.
    """
    target_url = comment_url or post_url
    target_type = "comment" if comment_url else ("post" if post_url else None)

    return {
        "target_url": target_url,
        "target_type": target_type,
        "reddit_post_id": fullname_post(comment_url or post_url),
        "reddit_comment_id": fullname_comment(comment_url) if comment_url else None,
        "subreddit": subreddit.removeprefix("r/") if subreddit else None,
    }
