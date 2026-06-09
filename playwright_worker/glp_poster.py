"""Godlike Productions posting logic.

GLP is a vBulletin-era PHP forum behind Cloudflare. Posting requires:
1. A logged-in browser session (cookies/storage_state captured by glp_login).
2. A residential / mobile proxy IP (datacenter IPs are 403'd at the edge).
3. Conservative cadence — moderators are known to ban for low-effort posting.

This module mirrors `playwright_worker/poster.py` but speaks the GLP DOM.
Selectors are the inferred defaults from Phase 0 recon; if the site changes,
update both the constants here and `docs/glp-recon.md`.

Posting flow (verified against the public site shape — Phase 0 recon must
confirm the exact form fields and submit URL):
  1. Navigate to the thread URL (`/forum1/message<thread>/pg<N>`)
  2. Locate the reply form on the page (no separate reply page on GLP — the
     form is in-line under the last post on each page).
  3. Fill the message textarea, optionally a subject line.
  4. Submit; wait for navigation to a URL containing `#post_<new_id>`.
  5. Extract `<new_id>` from the URL and return it as `posted_platform_comment_id`.

A captcha can appear at any of these steps — we screenshot + raise
`CaptchaEncountered` so the operator can decide whether to solve it manually.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime

from playwright.sync_api import BrowserContext, Page, TimeoutError as PWTimeout

# Reuse the Reddit poster's typed errors so callers can stay generic.
from playwright_worker.poster import CaptchaEncountered, PostingError

logger = logging.getLogger(__name__)


GLP_HOST = "https://www.godlikeproductions.com"
GLP_REPLY_FORM_SELECTOR = "form[action*='/bbs/reply.php'], form[name='replyform']"
GLP_MESSAGE_TEXTAREA_SELECTOR = "textarea[name='message'], textarea#message"
GLP_SUBJECT_INPUT_SELECTOR = "input[name='subject']"
GLP_SUBMIT_BUTTON_SELECTOR = (
    "input[type='submit'][name='submit'], input[type='submit'][value*='Post'], "
    "button[type='submit']"
)

# Posts on a thread page render with an anchor name of `post_<id>`.
_POST_ANCHOR_RE = re.compile(r"#post_(\d+)", re.IGNORECASE)
_BAN_PATTERNS = (
    re.compile(r"you have been banned", re.IGNORECASE),
    re.compile(r"your account is suspended", re.IGNORECASE),
    re.compile(r"posting is disabled for your account", re.IGNORECASE),
)
_FLOOD_PATTERNS = (
    re.compile(r"too many posts", re.IGNORECASE),
    re.compile(r"flood (?:control|protection)", re.IGNORECASE),
    re.compile(r"wait (\d+) (?:seconds?|minutes?)", re.IGNORECASE),
    re.compile(r"you must wait", re.IGNORECASE),
)


class GlpBanned(PostingError):
    """Account is banned — caller should disable the account, not retry."""


class GlpFloodControl(PostingError):
    """Posted too fast — caller should bump next_eligible_at and requeue."""

    def __init__(self, message: str, retry_after_seconds: int | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


def _detect_captcha(page: Page) -> bool:
    selectors = [
        "iframe[src*='recaptcha']",
        "iframe[src*='hcaptcha']",
        "iframe[src*='captcha']",
        ".g-recaptcha",
        "#captcha",
    ]
    for selector in selectors:
        try:
            if page.locator(selector).first.is_visible():
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _detect_ban_or_flood(html_lower: str) -> tuple[str | None, int | None]:
    """Return (kind, retry_after_seconds) — kind in {'ban', 'flood', None}."""
    for pat in _BAN_PATTERNS:
        if pat.search(html_lower):
            return "ban", None
    for pat in _FLOOD_PATTERNS:
        match = pat.search(html_lower)
        if match:
            # Try to parse "wait N seconds" / "wait N minutes" for cooldown bump.
            seconds: int | None = None
            try:
                n = int(match.group(1))
                if "minute" in match.group(0).lower():
                    seconds = n * 60
                else:
                    seconds = n
            except (IndexError, ValueError):
                seconds = None
            return "flood", seconds
    return None, None


def _detect_login_required(page: Page) -> bool:
    """GLP shows a 'log in' link in the header when not authenticated."""
    try:
        if page.locator("a[href*='login.php']").first.is_visible():
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _ensure_screenshot_dir(directory: str) -> str:
    os.makedirs(directory, exist_ok=True)
    return directory


def _screenshot(page: Page, directory: str, label: str, reply_id: int) -> str | None:
    try:
        _ensure_screenshot_dir(directory)
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        path = os.path.join(directory, f"glp_reply_{reply_id}_{label}_{timestamp}.png")
        page.screenshot(path=path, full_page=True)
        return path
    except Exception:  # noqa: BLE001
        logger.exception("Failed to capture screenshot %s", label)
        return None


def _post_to_thread(page: Page, target_url: str, text: str) -> str | None:
    """Navigate to a GLP thread page, fill the inline reply form, submit.

    Returns the new post id (string of digits) parsed from the post-submit
    URL anchor or response HTML. Raises on captcha, ban, flood, or timeout.
    """
    page.goto(target_url, wait_until="domcontentloaded", timeout=60_000)

    # Cloudflare interstitial sometimes resolves itself within a few seconds.
    try:
        page.wait_for_selector(GLP_REPLY_FORM_SELECTOR, timeout=20_000)
    except PWTimeout:
        if _detect_login_required(page):
            raise PostingError(
                "Not logged in to godlikeproductions.com. Run "
                "`python -m playwright_worker glp-login` first."
            )
        if _detect_captcha(page):
            raise CaptchaEncountered("CAPTCHA blocked the thread page load.")
        # Re-raise as a timeout — likely a Cloudflare challenge we can't auto-solve.
        raise PostingError(
            "GLP reply form not found within 20s — possibly a Cloudflare "
            "interstitial. Check proxy + storage_state freshness."
        )

    if _detect_captcha(page):
        raise CaptchaEncountered("CAPTCHA challenge on the reply form.")

    form = page.locator(GLP_REPLY_FORM_SELECTOR).first
    textarea = form.locator(GLP_MESSAGE_TEXTAREA_SELECTOR).first
    textarea.click()
    textarea.fill(text)

    # Subject is optional on most boards — leave blank.
    submit = form.locator(GLP_SUBMIT_BUTTON_SELECTOR).first
    with page.expect_navigation(wait_until="domcontentloaded", timeout=45_000):
        submit.click()

    # Captcha may appear *after* submit on flagged threads.
    if _detect_captcha(page):
        raise CaptchaEncountered("CAPTCHA appeared after submit.")

    body_text_lower = page.content().lower()
    kind, retry = _detect_ban_or_flood(body_text_lower)
    if kind == "ban":
        raise GlpBanned("Account appears banned or suspended.")
    if kind == "flood":
        raise GlpFloodControl(
            f"GLP flood control rejected the post (retry after {retry}s).",
            retry_after_seconds=retry,
        )

    # Successful post → URL gains a #post_<id> anchor or the new post block
    # appears in the page DOM. Try both signals.
    current_url = page.url or ""
    match = _POST_ANCHOR_RE.search(current_url)
    if match:
        return match.group(1)

    # Fallback: the most recent post block in the rendered page is ours.
    try:
        last_id = page.locator(
            "[name^='post_'], [id^='post_']"
        ).last.get_attribute("name") or page.locator(
            "[name^='post_'], [id^='post_']"
        ).last.get_attribute("id")
        if last_id:
            inner = _POST_ANCHOR_RE.search(f"#{last_id}")
            if inner:
                return inner.group(1)
    except Exception:  # noqa: BLE001
        pass
    return None


def post_reply(
    context: BrowserContext,
    job: dict,
    *,
    screenshot_dir: str,
) -> dict:
    """Drive a fresh page in the persistent context to post a GLP reply.

    Returns a dict with `posted_platform_comment_id` (the new post id) and
    `posted_url` (the canonical thread URL with the new post anchor).
    Raises GlpBanned / GlpFloodControl / CaptchaEncountered / PostingError
    on the typed failure modes."""
    target_url = job.get("target_url")
    text = job.get("reply_text")
    reply_id = job.get("reply_id", 0)

    if not target_url:
        raise PostingError("Job has no target_url")
    if not text:
        raise PostingError("Job has empty reply_text")

    page = context.new_page()
    try:
        new_post_id = _post_to_thread(page, target_url, text)
        anchored = (
            f"{target_url.split('#', 1)[0]}#post_{new_post_id}"
            if new_post_id
            else target_url
        )
        return {
            "posted_platform_comment_id": new_post_id,
            "posted_url": anchored,
        }
    except (GlpBanned, GlpFloodControl):
        _screenshot(page, screenshot_dir, "rate", reply_id)
        raise
    except CaptchaEncountered:
        _screenshot(page, screenshot_dir, "captcha", reply_id)
        raise
    except PostingError:
        _screenshot(page, screenshot_dir, "error", reply_id)
        raise
    except Exception as exc:  # noqa: BLE001
        _screenshot(page, screenshot_dir, "unexpected", reply_id)
        raise PostingError(f"Unexpected error while posting to GLP: {exc}") from exc
    finally:
        try:
            page.close()
        except Exception:  # noqa: BLE001
            pass


__all__ = [
    "GlpBanned",
    "GlpFloodControl",
    "post_reply",
]
