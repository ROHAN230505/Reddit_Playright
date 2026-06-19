"""Reddit posting logic — old.reddit.com first, with screenshot-on-failure.

The old.reddit.com UI uses static, well-known DOM selectors and is vastly
more reliable to automate than the React-based new Reddit. We therefore
rewrite all incoming target URLs to old.reddit.com by default. The new
Reddit path is left as a fallback for the rare case where old.reddit.com
is unavailable.
"""

from __future__ import annotations

import logging
import os
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse, urlunparse

from playwright.sync_api import BrowserContext, Page, TimeoutError as PWTimeout

logger = logging.getLogger(__name__)


class PostingError(RuntimeError):
    """Recoverable posting failure with a useful message for the operator."""


class CaptchaEncountered(PostingError):
    """Posting blocked by a CAPTCHA — leave retry possible."""


@dataclass(frozen=True)
class RedditWarmupConfig:
    enabled: bool = True
    pre_reply_delay_min_seconds: float = 3
    pre_reply_delay_max_seconds: float = 9
    read_delay_min_seconds: float = 4
    read_delay_max_seconds: float = 12
    scroll_steps_min: int = 2
    scroll_steps_max: int = 5


def to_old_reddit(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.netloc:
        return url
    if "reddit.com" not in parsed.netloc:
        return url
    new_netloc = "old.reddit.com"
    return urlunparse(parsed._replace(netloc=new_netloc))


def _comment_id_from_url(url: str) -> str | None:
    parts = [p for p in urlparse(url).path.split("/") if p]
    if "comments" not in parts:
        return None
    idx = parts.index("comments")
    if len(parts) >= idx + 4:
        return parts[idx + 3] or None
    return None


def _ensure_screenshot_dir(directory: str) -> str:
    os.makedirs(directory, exist_ok=True)
    return directory


def _screenshot(page: Page, directory: str, label: str, reply_id: int) -> str | None:
    try:
        _ensure_screenshot_dir(directory)
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        path = os.path.join(directory, f"reply_{reply_id}_{label}_{timestamp}.png")
        page.screenshot(path=path, full_page=True)
        return path
    except Exception:  # noqa: BLE001
        logger.exception("Failed to capture screenshot %s", label)
        return None


def _detect_captcha(page: Page) -> bool:
    selectors = [
        "iframe[src*='captcha']",
        "iframe[src*='recaptcha']",
        "iframe[src*='hcaptcha']",
        ".g-recaptcha",
    ]
    for selector in selectors:
        try:
            if page.locator(selector).first.is_visible():
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _detect_login_required(page: Page) -> bool:
    """Old-reddit specific: shows 'login or sign up' link in top-right when
    not authenticated. If no user nav is present, treat as logged out."""
    try:
        if page.locator("#header-bottom-right .user a.login-required").first.is_visible():
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _detect_network_block(page: Page) -> bool:
    try:
        title = (page.title() or "").lower()
    except Exception:  # noqa: BLE001
        title = ""
    try:
        body_text = page.locator("body").first.inner_text(timeout=1500).lower()
    except Exception:  # noqa: BLE001
        body_text = ""
    return (
        title == "blocked"
        or "blocked by network security" in body_text
        or "you've been blocked" in body_text
        or "whoa there, pardner" in body_text
    )


def _raise_if_blocked_or_logged_out(page: Page) -> None:
    if _detect_network_block(page):
        raise PostingError(
            "blocked_by_reddit: Reddit returned a network-security block page. "
            "Rotate/fix the proxy and refresh the account session before retrying."
        )
    if _detect_login_required(page):
        raise PostingError(
            "not_logged_in: Reddit session is not valid. Refresh cookies or run the "
            "manual login helper before retrying."
        )
    if _detect_captcha(page):
        raise CaptchaEncountered("CAPTCHA challenge appeared — manual intervention needed.")


def _bounded_delay(page: Page, minimum: float, maximum: float) -> None:
    low = max(0.0, float(minimum))
    high = max(low, float(maximum))
    page.wait_for_timeout(int(random.uniform(low, high) * 1000))


def _human_scroll(page: Page, config: RedditWarmupConfig) -> None:
    if not config.enabled:
        return
    min_steps = max(0, int(config.scroll_steps_min))
    max_steps = max(min_steps, int(config.scroll_steps_max))
    for _ in range(random.randint(min_steps, max_steps)):
        delta = random.randint(250, 900)
        page.mouse.wheel(0, delta)
        _bounded_delay(page, 0.6, 1.8)
    if random.random() < 0.35:
        page.mouse.wheel(0, -random.randint(120, 420))
        _bounded_delay(page, 0.5, 1.4)


def _warmup_before_reply(page: Page, target_url: str, config: RedditWarmupConfig) -> None:
    if not config.enabled:
        return

    parsed = urlparse(target_url)
    subreddit_url = None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 2 and parts[0].lower() == "r":
        subreddit_url = urlunparse(
            parsed._replace(path=f"/r/{parts[1]}/", params="", query="", fragment="")
        )

    warmup_url = subreddit_url or "https://old.reddit.com/"
    try:
        page.goto(warmup_url, wait_until="domcontentloaded", timeout=30_000)
        _raise_if_blocked_or_logged_out(page)
        _bounded_delay(
            page,
            config.pre_reply_delay_min_seconds,
            config.pre_reply_delay_max_seconds,
        )
        _human_scroll(page, config)
    except CaptchaEncountered:
        raise
    except PostingError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("Reddit warmup failed before target navigation: %s", exc)


def post_top_level_comment(page: Page, target_url: str, text: str) -> None:
    """Comment on a Reddit post (top-level). target_url should be the post URL."""
    page.goto(target_url, wait_until="domcontentloaded", timeout=45_000)
    _raise_if_blocked_or_logged_out(page)

    page.wait_for_selector(".commentarea form.usertext textarea[name='text']", timeout=20_000)
    textarea = page.locator(".commentarea form.usertext textarea[name='text']").first
    textarea.click()
    textarea.fill(text)

    submit = page.locator(
        ".commentarea form.usertext input[name='save'], .commentarea form.usertext button.save"
    ).first
    submit.click()

    try:
        page.wait_for_function(
            """
            () => {
                const ta = document.querySelector(
                    ".commentarea form.usertext textarea[name='text']"
                );
                return !ta || ta.value === "";
            }
            """,
            timeout=25_000,
        )
    except PWTimeout as exc:
        raise PostingError("Timed out waiting for comment submission to complete.") from exc

    # Brief settle for the new comment to render so the next page nav is clean.
    page.wait_for_timeout(800)


def reply_to_comment(page: Page, target_url: str, text: str) -> None:
    """Reply to a specific comment. target_url should be a permalink to that
    comment, e.g. /r/sub/comments/POST/SLUG/COMMENT/."""
    comment_id = _comment_id_from_url(target_url)
    if not comment_id:
        raise PostingError(f"Could not parse comment id from URL: {target_url}")

    page.goto(target_url, wait_until="domcontentloaded", timeout=45_000)
    _raise_if_blocked_or_logged_out(page)

    selector = f"#thing_t1_{comment_id}"
    try:
        page.wait_for_selector(selector, timeout=20_000)
    except PWTimeout as exc:
        raise PostingError(
            f"Could not locate target comment {comment_id} on page {target_url}"
        ) from exc

    parent = page.locator(selector).first
    reply_link = parent.locator("ul.flat-list .first a").filter(has_text=re.compile(r"^reply$", re.I)).first
    if not reply_link.count():
        # Fallback: any link inside this comment whose text is exactly "reply".
        reply_link = parent.locator("a").filter(has_text=re.compile(r"^reply$", re.I)).first
    reply_link.click()

    form = parent.locator("form.usertext").filter(
        has=page.locator("textarea[name='text']")
    ).first
    form.wait_for(state="visible", timeout=15_000)
    form.locator("textarea[name='text']").fill(text)
    form.locator("input[name='save'], button.save").first.click()

    try:
        # Either the form is removed or the textarea is cleared.
        page.wait_for_function(
            f"""
            () => {{
                const parent = document.querySelector('{selector}');
                if (!parent) return true;
                const form = parent.querySelector('form.usertext');
                if (!form) return true;
                const ta = form.querySelector("textarea[name='text']");
                return !ta || ta.value === "";
            }}
            """,
            timeout=25_000,
        )
    except PWTimeout as exc:
        raise PostingError("Timed out waiting for reply submission to complete.") from exc

    page.wait_for_timeout(800)


def post_reply(
    context: BrowserContext,
    job: dict,
    *,
    use_old_reddit: bool,
    screenshot_dir: str,
    warmup_config: RedditWarmupConfig | None = None,
) -> dict:
    """Drive a fresh page in the persistent context to post `job`.

    Returns a dict with optional `posted_reddit_comment_id`. Raises
    PostingError / CaptchaEncountered on failure (caller should report)."""
    target_url = job["target_url"]
    target_type = (job.get("target_type") or "comment").lower()
    text = job["reply_text"]
    reply_id = job["reply_id"]

    if not target_url:
        raise PostingError("Job has no target_url")
    if not text:
        raise PostingError("Job has empty reply_text")

    effective_url = to_old_reddit(target_url) if use_old_reddit else target_url

    page = context.new_page()
    try:
        config = warmup_config or RedditWarmupConfig(enabled=False)
        _warmup_before_reply(page, effective_url, config)
        page.goto(effective_url, wait_until="domcontentloaded", timeout=45_000)
        _raise_if_blocked_or_logged_out(page)
        _human_scroll(page, config)
        _bounded_delay(
            page,
            config.read_delay_min_seconds if config.enabled else 0,
            config.read_delay_max_seconds if config.enabled else 0,
        )
        if target_type == "post":
            post_top_level_comment(page, effective_url, text)
        else:
            reply_to_comment(page, effective_url, text)
        return {"posted_reddit_comment_id": None}
    except CaptchaEncountered:
        _screenshot(page, screenshot_dir, "captcha", reply_id)
        raise
    except PostingError:
        _screenshot(page, screenshot_dir, "error", reply_id)
        raise
    except Exception as exc:  # noqa: BLE001
        _screenshot(page, screenshot_dir, "unexpected", reply_id)
        raise PostingError(f"Unexpected error while posting: {exc}") from exc
    finally:
        try:
            page.close()
        except Exception:  # noqa: BLE001
            pass


# Deliberately re-exported helpers for tests.
__all__ = [
    "PostingError",
    "CaptchaEncountered",
    "to_old_reddit",
    "post_reply",
    "post_top_level_comment",
    "reply_to_comment",
]
