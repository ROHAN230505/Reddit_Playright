"""Automated login for godlikeproductions.com (GLP).

GLP login is a classic PHP form (`/login.php` → POST `/loginrespond.php`).
There is no built-in TOTP. The main failure modes:
  - Wrong credentials → page reloads with an error message.
  - reCAPTCHA on signup is verified, but the login form is *usually* captcha-
    free unless the IP is flagged. If a captcha shows up at login, we bail and
    require the operator to do a manual one-time login from the residential IP.
  - Cloudflare 403 / interstitial → not solvable here; the operator must check
    proxy + UA fingerprint.

This module mirrors `playwright_worker/login.py` so AccountRuntime can call
either depending on `account.platform`.
"""

from __future__ import annotations

import logging

from patchright.sync_api import Page, TimeoutError as PWTimeout

# Reuse the typed errors so callers can stay platform-neutral.
from playwright_worker.login import CaptchaEncountered, LoginFailed

logger = logging.getLogger(__name__)


GLP_LOGIN_URL = "https://www.godlikeproductions.com/login.php"
GLP_HOMEPAGE_URL = "https://www.godlikeproductions.com/"

_LOGGED_IN_SELECTORS = [
    # Header user-menu link visible only to authenticated members.
    "a[href*='memberlist.php']",
    "a[href*='usercp.php']",
    "a[href*='myforum.php']",
    "a[href*='logout.php']",
]
_USERNAME_SELECTORS = [
    "input[name='nick']",
    "input[name='username']",
    "input#nick",
    "input#username",
]
_PASSWORD_SELECTORS = [
    "input[name='password']",
    "input[type='password']",
]
_SUBMIT_SELECTORS = [
    "input[type='submit'][value*='Log']",
    "input[type='submit'][name='submit']",
    "button[type='submit']",
]
_ERROR_SELECTORS = [
    ".error",
    ".errormsg",
    "[role='alert']",
    ".alert",
]
_CAPTCHA_SELECTORS = [
    "iframe[src*='recaptcha']",
    "iframe[src*='hcaptcha']",
    "iframe[src*='captcha']",
    ".g-recaptcha",
]


def _find_first(page: Page, selectors: list[str], *, what: str,
                timeout_ms: int = 10_000):
    import time

    deadline = time.monotonic() + (timeout_ms / 1000.0)
    while time.monotonic() < deadline:
        for selector in selectors:
            try:
                loc = page.locator(selector).first
                if loc.count() and loc.is_visible(timeout=300):
                    return loc
            except Exception:  # noqa: BLE001
                continue
        time.sleep(0.4)
    raise LoginFailed(f"Could not locate {what} on the GLP login page")


def _check_captcha(page: Page) -> None:
    for selector in _CAPTCHA_SELECTORS:
        try:
            if page.locator(selector).first.is_visible(timeout=500):
                raise CaptchaEncountered(
                    f"CAPTCHA detected on GLP login (selector={selector!r}) — "
                    "manual login required from a residential IP."
                )
        except CaptchaEncountered:
            raise
        except Exception:  # noqa: BLE001
            continue


def is_logged_in(page: Page) -> bool:
    """Return True if the current GLP session is authenticated."""
    try:
        page.goto(GLP_HOMEPAGE_URL, wait_until="domcontentloaded", timeout=30_000)
    except Exception as exc:  # noqa: BLE001
        logger.warning("GLP is_logged_in: navigation error: %s", exc)
        return False
    for selector in _LOGGED_IN_SELECTORS:
        try:
            if page.locator(selector).first.is_visible(timeout=2_000):
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def automated_glp_login(page: Page, username: str, password: str,
                        totp_secret: str | None = None) -> None:
    """Programmatic GLP login. `totp_secret` is accepted for API parity with
    `automated_login()` but unused (GLP has no TOTP)."""
    logger.info("Logging in to GLP as %s", username)
    page.goto(GLP_LOGIN_URL, wait_until="domcontentloaded", timeout=45_000)

    _check_captcha(page)

    user_field = _find_first(page, _USERNAME_SELECTORS, what="username field")
    pass_field = _find_first(page, _PASSWORD_SELECTORS, what="password field")
    user_field.fill(username)
    pass_field.fill(password)

    submit = _find_first(page, _SUBMIT_SELECTORS, what="submit button", timeout_ms=5_000)
    submit.click()

    try:
        page.wait_for_load_state("domcontentloaded", timeout=20_000)
    except PWTimeout:
        pass

    _check_captcha(page)

    # Look for either logged-in state OR an explicit error.
    for selector in _LOGGED_IN_SELECTORS:
        try:
            if page.locator(selector).first.is_visible(timeout=3_000):
                logger.info("GLP login successful for %s", username)
                return
        except Exception:  # noqa: BLE001
            continue

    for error_selector in _ERROR_SELECTORS:
        try:
            el = page.locator(error_selector).first
            if el.is_visible(timeout=500):
                text = el.inner_text().strip()
                if text:
                    raise LoginFailed(f"GLP login error for {username}: {text!r}")
        except LoginFailed:
            raise
        except Exception:  # noqa: BLE001
            continue

    raise LoginFailed(
        f"GLP login: could not confirm authenticated session for {username} "
        "(no logged-in markers and no explicit error message)."
    )


__all__ = ["automated_glp_login", "is_logged_in", "LoginFailed", "CaptchaEncountered"]
