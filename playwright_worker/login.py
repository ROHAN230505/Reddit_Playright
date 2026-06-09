"""Automated Reddit login for the multi-account Playwright worker.

This module handles programmatic login to www.reddit.com, including TOTP-based
2FA. It is designed to be called from AccountRuntime.bootstrap() when a
persistent browser context does not already have a valid Reddit session.

Key responsibilities:
- Detect whether a page is already logged in (is_logged_in).
- Fill username/password and submit the login form (automated_login).
- Handle TOTP 2FA by computing a TOTP code via pyotp.
- Raise LoginFailed or CaptchaEncountered so the caller can update account
  status accordingly without crashing the overall orchestrator.
"""

from __future__ import annotations

import logging
import re

from patchright.sync_api import Page, TimeoutError as PWTimeout

logger = logging.getLogger(__name__)


class LoginFailed(RuntimeError):
    """Raised when login fails (wrong credentials, error toast, 2FA with no secret, etc.)."""


class CaptchaEncountered(RuntimeError):
    """Raised when a CAPTCHA iframe is detected during login — requires manual intervention."""


# Reddit consolidated all login UX (including old.reddit.com/login) onto a
# Web-Components SPA rendered by <auth-flow-manager>. The username/password
# inputs are real <input> elements but live inside <faceplate-text-input>
# shadow roots. Playwright's accessibility locators (get_by_label) pierce
# shadow DOM transparently, so we use those as the primary strategy with
# raw-CSS fallbacks for resilience.
LOGIN_URL = "https://www.reddit.com/login/"
HOMEPAGE_URL = "https://old.reddit.com/"

_LOGGED_IN_SELECTORS = [
    "#header-bottom-right .user .userkarma",     # old reddit
    "#header-bottom-right .user a.user",         # old reddit (no karma displayed)
    "[data-testid='user-drawer-button']",        # new reddit fallback
    "button[id*='USER_DRAWER']",                 # new reddit variant
]
_TOTP_SELECTORS = [
    "input[name='otp']",
    "input[autocomplete='one-time-code']",
    "input[name='code']",
    "input[name='2fa']",
]
_ERROR_SELECTORS = [
    "#login-form .status",                        # old reddit error span
    "#login-form .error",                         # old reddit error class
    ".AnimatedForm__errorMessage",                # new reddit
    ".error.c-form-control-feedback",             # new reddit variant
    "[role='alert']",                             # generic
]
_CAPTCHA_SELECTORS = [
    "iframe[src*='captcha']",
    "iframe[src*='recaptcha']",
    "iframe[src*='hcaptcha']",
    ".g-recaptcha",
]


def _find_first(
    page: Page,
    strategies: list[tuple[str, object]],
    *,
    what: str,
    timeout_ms: int,
):
    """Try each (kind, value) pair in order; return the first locator that becomes visible.

    `kind` ∈ {"get_by_label", "get_by_role_button", "css"}. Raises LoginFailed
    if none succeed within `timeout_ms` total.
    """
    import time

    deadline = time.monotonic() + (timeout_ms / 1000.0)
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        for kind, value in strategies:
            try:
                if kind == "get_by_label":
                    loc = page.get_by_label(value).first
                elif kind == "get_by_role_button":
                    loc = page.get_by_role("button", name=value).first
                else:
                    loc = page.locator(str(value)).first
                if loc.count() and loc.is_visible(timeout=300):
                    return loc
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue
        time.sleep(0.4)

    raise LoginFailed(
        f"Could not locate {what} on the login page within {timeout_ms}ms"
        + (f" (last error: {last_error})" if last_error else "")
    )


def _has_reddit_session_cookie(page: Page) -> bool:
    """Return True if the page context has a reddit_session cookie."""
    try:
        cookies = page.context.cookies()
        return any(c.get("name") == "reddit_session" for c in cookies)
    except Exception:  # noqa: BLE001
        return False


def _check_captcha(page: Page) -> None:
    """Raise CaptchaEncountered if a CAPTCHA widget is visible on the page."""
    for selector in _CAPTCHA_SELECTORS:
        try:
            if page.locator(selector).first.is_visible(timeout=500):
                raise CaptchaEncountered(
                    f"CAPTCHA detected (selector={selector!r}) — manual login required."
                )
        except CaptchaEncountered:
            raise
        except Exception:  # noqa: BLE001
            continue


def _check_network_security_block(page: Page) -> None:
    """Raise LoginFailed with a precise message if Reddit's anti-bot block page is showing."""
    try:
        body_text = page.locator("body").first.inner_text(timeout=1500)
    except Exception:  # noqa: BLE001
        return
    text = (body_text or "").lower()
    if "blocked by network security" in text or "you've been blocked" in text:
        raise LoginFailed(
            "Reddit network-security block — proxy IP and/or browser fingerprint flagged. "
            "Mitigations: rotate to a fresh proxy session, use a different residential IP, "
            "or do a one-time manual login (`python -m playwright_worker login`) on the server."
        )


def is_logged_in(page: Page) -> bool:
    """Navigate to www.reddit.com and return True if a valid session is detected.

    Checks for the presence of user-menu elements or the reddit_session cookie.
    Call this before automated_login to skip unnecessary re-authentication.
    """
    try:
        page.goto(HOMEPAGE_URL, wait_until="domcontentloaded", timeout=30_000)
    except Exception as exc:  # noqa: BLE001
        logger.warning("is_logged_in: navigation error: %s", exc)
        return False

    if _has_reddit_session_cookie(page):
        return True

    for selector in _LOGGED_IN_SELECTORS:
        try:
            if page.locator(selector).first.is_visible(timeout=2_000):
                return True
        except Exception:  # noqa: BLE001
            continue

    return False


def automated_login(
    page: Page,
    username: str,
    password: str,
    totp_secret: str | None,
) -> None:
    """Log in to Reddit programmatically.

    Args:
        page: A Playwright Page in an already-open persistent context.
        username: Reddit username (without u/ prefix).
        password: Plaintext Reddit password.
        totp_secret: Base32 TOTP secret, or None if no 2FA.

    Raises:
        LoginFailed: On wrong credentials, error toast, or 2FA required with no secret.
        CaptchaEncountered: When a CAPTCHA widget appears at any step.
    """
    logger.info("Logging in as u/%s via %s", username, LOGIN_URL)

    # Pre-warm: hit the homepage first so anonymous cookies + bot-score
    # heuristics get a "human-like" prior before /login's auth-flow API kicks in.
    try:
        page.goto("https://www.reddit.com/", wait_until="domcontentloaded", timeout=20_000)
        page.wait_for_timeout(1500)
    except PWTimeout:
        pass

    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)

    # Detect Reddit's hard anti-bot block immediately — before any other waits,
    # since the block page never reaches networkidle and never renders the form.
    _check_network_security_block(page)
    _check_captcha(page)

    # Wait for the auth web components to hydrate. The <auth-flow-manager>
    # element is what renders the actual login form.
    try:
        page.wait_for_selector("auth-flow-manager", timeout=20_000)
    except PWTimeout:
        # Fall through — page may already be on a variant without that wrapper.
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=8_000)
    except PWTimeout:
        # Networkidle never fires on some pages with long-poll/WS connections.
        # Not fatal — we proceed and let the field locator do its own waiting.
        pass

    # Re-check after hydration in case the block page is rendered late.
    _check_network_security_block(page)
    _check_captcha(page)

    # Target the inner <input> directly, not the <faceplate-text-input>
    # wrapper. get_by_label matches the wrapper and fill() rejects it.
    user_field = _find_first(
        page,
        [
            ("css", 'faceplate-text-input[name="username"] input'),
            ("css", 'input[name="username"]'),
            ("css", "#login-username"),
            ("css", 'input[type="text"][autocomplete*="username"]'),
        ],
        what="username field",
        timeout_ms=20_000,
    )
    pass_field = _find_first(
        page,
        [
            ("css", 'faceplate-text-input[name="password"] input'),
            ("css", 'input[name="password"]'),
            ("css", "#login-password"),
            ("css", 'input[type="password"]'),
        ],
        what="password field",
        timeout_ms=10_000,
    )
    user_field.fill(username)
    pass_field.fill(password)

    submit = _find_first(
        page,
        [
            ("css", 'faceplate-button[type="submit"] button'),
            ("css", 'auth-flow-manager button[type="submit"]'),
            ("css", 'button[type="submit"]'),
            ("css", 'faceplate-button[type="submit"]'),
            ("get_by_role_button", re.compile(r"^\s*log\s*in\s*$", re.I)),
        ],
        what="submit button",
        timeout_ms=10_000,
    )
    submit.click()

    # Wait for one of: logged-in indicator, 2FA prompt, error toast, or captcha.
    _wait_for_login_result(page, username, totp_secret)


def _wait_for_login_result(
    page: Page,
    username: str,
    totp_secret: str | None,
) -> None:
    """After clicking submit, poll for the next state with up to 25s timeout."""
    import time

    deadline = time.monotonic() + 25.0
    poll_interval = 0.4

    while time.monotonic() < deadline:
        _check_captcha(page)

        # Check logged-in state.
        if _has_reddit_session_cookie(page):
            logger.info("Login successful for u/%s (cookie)", username)
            return
        for selector in _LOGGED_IN_SELECTORS:
            try:
                if page.locator(selector).first.is_visible(timeout=300):
                    logger.info("Login successful for u/%s (selector=%r)", username, selector)
                    return
            except Exception:  # noqa: BLE001
                pass

        # Check for 2FA input.
        for totp_selector in _TOTP_SELECTORS:
            try:
                otp_input = page.locator(totp_selector).first
                if otp_input.is_visible(timeout=300):
                    _handle_totp(page, otp_input, username, totp_secret)
                    # After submitting TOTP, reset deadline and continue polling.
                    deadline = time.monotonic() + 25.0
                    break
            except (LoginFailed, CaptchaEncountered):
                raise
            except Exception:  # noqa: BLE001
                pass

        # Check for error toast.
        for error_selector in _ERROR_SELECTORS:
            try:
                el = page.locator(error_selector).first
                if el.is_visible(timeout=300):
                    error_text = el.inner_text().strip()
                    raise LoginFailed(f"Login error for u/{username}: {error_text!r}")
            except (LoginFailed, CaptchaEncountered):
                raise
            except Exception:  # noqa: BLE001
                pass

        time.sleep(poll_interval)

    raise LoginFailed(
        f"Timed out waiting for login completion for u/{username} (25s)."
    )


def _handle_totp(
    page: Page,
    otp_input,
    username: str,
    totp_secret: str | None,
) -> None:
    """Fill TOTP code and submit the verification step."""
    if not totp_secret:
        raise LoginFailed(
            f"2FA required for u/{username} but no TOTP secret stored."
        )

    try:
        import pyotp
    except ImportError as exc:
        raise LoginFailed(
            "pyotp is not installed — cannot compute TOTP code."
        ) from exc

    code = pyotp.TOTP(totp_secret).now()
    logger.info("Submitting TOTP for u/%s", username)
    otp_input.fill(code)

    # Submit via Enter or a Verify button.
    verify_btn = page.locator("button[type='submit'], button:has-text('Verify')").first
    if verify_btn.count() and verify_btn.is_visible(timeout=1_000):
        verify_btn.click()
    else:
        otp_input.press("Enter")
