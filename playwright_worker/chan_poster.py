"""4chan posting logic via Playwright on boards.4chan.org.

4chan posting is anonymous but rate-limited per IP and gated by reCAPTCHA on
every post UNLESS the browser carries a valid `4chan_pass` cookie ($20/yr).
Without a Pass, this worker will hit the captcha and raise
`CaptchaEncountered` — the operator can either solve it manually or wire a
captcha-solver service later.

Posting flow:
  1. Navigate to https://boards.4chan.org/{board}/thread/{thread_id}
  2. Find the inline quick-reply form (#qf, or the bottom-page form).
  3. Fill the `com` textarea with the reply text. Optionally prepend a
     greentext quote of the parent post: `>>{parent_post_id}\\n`.
  4. Submit; wait for the post to appear in the thread DOM.
  5. Extract the new post id from the URL anchor or the latest [N] block.

Failure modes:
  - Captcha visible → CaptchaEncountered
  - "Thread closed" / "404" → PostingError (unrecoverable for this job)
  - "Flood detected" / "You must wait N seconds" → ChanFloodControl
  - "Banned" / "your IP has been banned" → ChanBanned
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime

from playwright.sync_api import BrowserContext, Page, TimeoutError as PWTimeout

# Reuse the typed errors so callers can stay generic.
from playwright_worker.poster import CaptchaEncountered, PostingError

logger = logging.getLogger(__name__)


CHAN_HOST = "https://boards.4chan.org"
CHAN_REPLY_FORM_SELECTOR = "form[name='post'], #qf"
CHAN_MESSAGE_TEXTAREA_SELECTOR = "textarea[name='com']"
CHAN_SUBMIT_SELECTOR = "input[type='submit'][value*='Post'], button[type='submit']"
# 4chan builds the post form with JS and hides it behind a "[Post a Reply]"
# toggle (`#togglePostFormLink`). The `textarea[name='com']` exists in the DOM
# but is display:none until that link is clicked, so a direct .click()/.fill()
# fails with "element is not visible". We click the toggle to reveal it.
CHAN_TOGGLE_FORM_SELECTOR = "#togglePostFormLink a, #togglePostFormLink, a[href='#']:has-text('Post a Reply')"

# Each post in a thread sits in a div with class 'postContainer' and an id of
# `pc<post_id>`; the inner post block uses id `p<post_id>`.
_POST_ID_RE = re.compile(r"#p(?P<post_id>\d+)", re.IGNORECASE)

_BAN_PATTERNS = (
    re.compile(r"you have been banned", re.IGNORECASE),
    re.compile(r"your ip (?:has been|is) banned", re.IGNORECASE),
    re.compile(r"range[- ]?banned", re.IGNORECASE),
)
_FLOOD_PATTERNS = (
    re.compile(r"flood detected", re.IGNORECASE),
    re.compile(r"you must wait (\d+) (?:seconds?|minutes?)", re.IGNORECASE),
    re.compile(r"posting too quickly", re.IGNORECASE),
)
_THREAD_DEAD_PATTERNS = (
    re.compile(r"thread (?:is )?closed", re.IGNORECASE),
    re.compile(r"thread (?:does not exist|has been deleted|404)", re.IGNORECASE),
    re.compile(r"specified thread", re.IGNORECASE),
)


class ChanBanned(PostingError):
    """IP/range banned — caller should disable the account."""


class ChanFloodControl(PostingError):
    """Posting too fast — caller should bump next_eligible_at."""

    def __init__(self, message: str, retry_after_seconds: int | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ChanThreadDead(PostingError):
    """Thread 404'd / closed — don't requeue."""


def _detect_captcha(page: Page) -> bool:
    selectors = [
        "iframe[src*='recaptcha']",
        "iframe[src*='hcaptcha']",
        ".g-recaptcha",
        "#t-resp",  # 4chan custom captcha input
    ]
    for selector in selectors:
        try:
            if page.locator(selector).first.is_visible(timeout=500):
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _detect_failure(html_lower: str) -> tuple[str | None, int | None]:
    """Return ('ban'|'flood'|'dead', retry_seconds) or (None, None)."""
    for pat in _BAN_PATTERNS:
        if pat.search(html_lower):
            return "ban", None
    for pat in _THREAD_DEAD_PATTERNS:
        if pat.search(html_lower):
            return "dead", None
    for pat in _FLOOD_PATTERNS:
        m = pat.search(html_lower)
        if m:
            seconds: int | None = None
            try:
                n = int(m.group(1))
                seconds = n * 60 if "minute" in m.group(0).lower() else n
            except (IndexError, ValueError):
                seconds = None
            return "flood", seconds
    return None, None


def _ensure_screenshot_dir(directory: str) -> str:
    os.makedirs(directory, exist_ok=True)
    return directory


def _screenshot(page: Page, directory: str, label: str, reply_id: int) -> str | None:
    try:
        _ensure_screenshot_dir(directory)
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        path = os.path.join(directory, f"chan_reply_{reply_id}_{label}_{timestamp}.png")
        page.screenshot(path=path, full_page=True)
        return path
    except Exception:  # noqa: BLE001
        logger.exception("Failed to capture screenshot %s", label)
        return None


def _textarea_visible(textarea) -> bool:
    try:
        return textarea.is_visible(timeout=1_000)
    except Exception:  # noqa: BLE001
        return False


def _reveal_post_form(page: Page) -> None:
    """Click 4chan's "[Post a Reply]" toggle to un-hide the post form.

    Tries the toggle link first; if that's not clickable, falls back to forcing
    the form's container visible via JS (4chan's own toggle just flips the
    inline display style on `#postForm` / `#togglePostFormLink`)."""
    try:
        toggle = page.locator(CHAN_TOGGLE_FORM_SELECTOR).first
        if toggle.is_visible(timeout=2_000):
            toggle.click(timeout=5_000)
            return
    except Exception:  # noqa: BLE001
        pass
    # Fallback: directly reveal the form 4chan would have shown.
    try:
        page.evaluate(
            """() => {
                const f = document.getElementById('postForm');
                if (f) f.style.display = 'table';
                const t = document.getElementById('togglePostFormLink');
                if (t) t.style.display = 'none';
            }"""
        )
    except Exception:  # noqa: BLE001
        logger.debug("JS fallback to reveal 4chan post form failed", exc_info=True)


def _post_to_thread(
    page: Page,
    target_url: str,
    text: str,
    parent_post_id: str | None,
) -> str | None:
    """Drive the thread page reply form. Returns new post id on success.

    If parent_post_id is given, prepend a `>>{id}` quote so the reply
    threads in 4chan's reply graph (and renders as a clickable backref).
    """
    page.goto(target_url, wait_until="domcontentloaded", timeout=60_000)

    try:
        # state="attached": the form is JS-built and starts hidden behind the
        # "[Post a Reply]" toggle, so wait for it to exist, not to be visible.
        page.wait_for_selector(CHAN_REPLY_FORM_SELECTOR, state="attached", timeout=15_000)
    except PWTimeout:
        if _detect_captcha(page):
            raise CaptchaEncountered("CAPTCHA blocked the thread page.")
        # Maybe the thread expired.
        body_lc = page.content().lower()
        kind, _ = _detect_failure(body_lc)
        if kind == "dead":
            raise ChanThreadDead("Thread no longer exists.")
        raise PostingError(
            "4chan reply form not found within 15s. Thread may have been "
            "closed or the page failed to render."
        )

    if _detect_captcha(page):
        raise CaptchaEncountered(
            "4chan reply form rendered a captcha. Install a 4chan Pass cookie "
            "or wire a solver."
        )

    form = page.locator(CHAN_REPLY_FORM_SELECTOR).first
    textarea = form.locator(CHAN_MESSAGE_TEXTAREA_SELECTOR).first

    # The form starts hidden behind the "[Post a Reply]" toggle. If the textarea
    # isn't visible, click the toggle to reveal it (idempotent — clicking when
    # already open would close it, so only act when hidden).
    if not _textarea_visible(textarea):
        _reveal_post_form(page)
        try:
            textarea.wait_for(state="visible", timeout=10_000)
        except PWTimeout:
            if _detect_captcha(page):
                raise CaptchaEncountered("CAPTCHA appeared while opening the reply form.")
            raise PostingError(
                "4chan reply textarea never became visible after toggling the "
                "post form."
            )

    body = f">>{parent_post_id}\n{text}" if parent_post_id else text
    textarea.click()
    textarea.fill(body)

    submit = form.locator(CHAN_SUBMIT_SELECTOR).first
    with page.expect_navigation(wait_until="domcontentloaded", timeout=45_000):
        submit.click()

    # Captcha can appear after submit on flagged threads.
    if _detect_captcha(page):
        raise CaptchaEncountered("CAPTCHA appeared after submit.")

    body_lc = page.content().lower()
    kind, retry = _detect_failure(body_lc)
    if kind == "ban":
        raise ChanBanned("4chan banned this IP/range.")
    if kind == "flood":
        raise ChanFloodControl(
            f"4chan flood control rejected the post (retry after {retry}s).",
            retry_after_seconds=retry,
        )
    if kind == "dead":
        raise ChanThreadDead("Thread closed before the reply landed.")

    # On success 4chan redirects to a URL with `#p<new_id>` or the new post
    # block is now the last one in the DOM.
    current_url = page.url or ""
    m = _POST_ID_RE.search(current_url)
    if m:
        return m.group("post_id")
    try:
        # The last post block id looks like `p<digits>`; related elements use
        # `pi<digits>` (post-info) etc. We just want the digits, so strip any
        # non-digit prefix rather than assuming the exact element class.
        last_id = page.locator("[id^='p']").last.get_attribute("id")
        if last_id:
            digits = re.sub(r"\D", "", last_id)
            if digits:
                return digits
    except Exception:  # noqa: BLE001
        pass
    return None


def post_reply(
    context: BrowserContext,
    job: dict,
    *,
    screenshot_dir: str,
) -> dict:
    """Drive a fresh page in `context` to post a 4chan reply.

    Returns `posted_platform_comment_id` (the new post id) and `posted_url`
    (the canonical thread URL with the new #p anchor). Raises typed errors
    on the failure modes documented in the module docstring."""
    target_url = job.get("target_url")
    text = job.get("reply_text")
    reply_id = job.get("reply_id", 0)
    parent_post_id = job.get("platform_comment_id") or job.get("platform_post_id")

    if not target_url:
        raise PostingError("Job has no target_url")
    if not text:
        raise PostingError("Job has empty reply_text")

    # If the target_url already carries a #p<id> anchor strip it — we want to
    # land on the thread page, then quote the specific post via >>id in the body.
    base_url = target_url.split("#", 1)[0]

    page = context.new_page()
    try:
        new_post_id = _post_to_thread(page, base_url, text, parent_post_id)
        anchored = f"{base_url}#p{new_post_id}" if new_post_id else base_url
        return {
            "posted_platform_comment_id": new_post_id,
            "posted_url": anchored,
        }
    except (ChanBanned, ChanFloodControl, ChanThreadDead):
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
        raise PostingError(f"Unexpected error while posting to 4chan: {exc}") from exc
    finally:
        try:
            page.close()
        except Exception:  # noqa: BLE001
            pass


__all__ = ["ChanBanned", "ChanFloodControl", "ChanThreadDead", "post_reply"]
