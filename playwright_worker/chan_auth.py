"""4chan Pass authentication for the Playwright worker.

A 4chan Pass lets a browser post without solving a reCAPTCHA on every reply.
You authenticate once by POSTing your Pass Token + PIN to
`https://sys.4chan.org/auth`; on success 4chan sets two cookies on `.4chan.org`:

    pass_id       (the signed session token; secure, httponly)
    pass_enabled  ("1")

These cookies are what `boards.4chan.org` checks when rendering the reply form
to decide whether to skip the captcha.

We drive the auth POST *inside the same BrowserContext* used for posting (rather
than via a standalone HTTP client) for two reasons:
  1. The context already carries the account's proxy, so the Pass binds to the
     same exit IP the posts come from. A Pass is valid from ONE IP at a time;
     authing through a different IP than we post from would immediately
     invalidate it.
  2. The resulting cookies land directly in the context's cookie jar (and the
     persistent profile), so posting picks them up with no extra plumbing.

A Pass IP binding can be changed at most once every 30 minutes, and re-auth on
an already-cookied device is free, so we auth at bootstrap and re-auth lazily if
a captcha shows up mid-run (cookie expired / IP rotated).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoid importing playwright at runtime for pure-logic tests
    from playwright.sync_api import BrowserContext

logger = logging.getLogger(__name__)

AUTH_URL = "https://sys.4chan.org/auth"
# Phrase 4chan renders on a successful auth ("You are authenticated.").
_SUCCESS_MARKER = "you are authenticated"
# Substrings that indicate a rejected token/PIN.
_FAILURE_MARKERS = (
    "incorrect token or pin",
    "your token must be exactly",
    "token or pin is invalid",
    "error:",
)


class ChanPassError(Exception):
    """Raised when 4chan rejects the Pass token/PIN."""


def has_pass_cookie(context: BrowserContext) -> bool:
    """True if the context already carries an enabled 4chan Pass cookie."""
    try:
        for c in context.cookies("https://boards.4chan.org"):
            if c.get("name") == "pass_enabled" and str(c.get("value")) == "1":
                return True
            if c.get("name") == "pass_id" and c.get("value") not in (None, "", "0"):
                return True
    except Exception:  # noqa: BLE001
        logger.debug("Could not read context cookies for Pass check", exc_info=True)
    return False


def authenticate(
    context: BrowserContext,
    token: str,
    pin: str,
    *,
    long_login: bool = True,
) -> bool:
    """POST the Pass token + PIN to sys.4chan.org/auth via `context`.

    On success the Pass cookies are set on the context automatically. Returns
    True on success; raises ChanPassError if 4chan reports an invalid token/PIN.

    `long_login=True` requests the long-lived cookie (matches the site's
    "Remember me" checkbox) so we re-auth less often.
    """
    token = (token or "").strip()
    pin = (pin or "").strip()
    if not token or not pin:
        raise ChanPassError("4chan Pass token/PIN not configured")

    page = context.new_page()
    try:
        # Load the auth page first so the POST is same-origin (4chan rejects
        # cross-origin form posts), then submit the form via fetch() so the
        # Set-Cookie response is applied to this context.
        page.goto(AUTH_URL, wait_until="domcontentloaded", timeout=60_000)

        body = page.evaluate(
            """async ({token, pin, longLogin}) => {
                const form = new URLSearchParams();
                form.set('act', 'do_login');
                form.set('id', token);
                form.set('pin', pin);
                if (longLogin) form.set('long_login', 'yes');
                const resp = await fetch('/auth', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                    body: form.toString(),
                    credentials: 'include',
                });
                return await resp.text();
            }""",
            {"token": token, "pin": pin, "longLogin": long_login},
        )

        # The authoritative success signal is the pass_id/pass_enabled cookie
        # landing in the context — 4chan does not always render the "you are
        # authenticated" text (it may return a minimal/redirect body), but it
        # always Set-Cookies on success. Check the cookie first, then fall back
        # to the text marker, and only then treat the response as a failure.
        if has_pass_cookie(context):
            logger.info("4chan Pass authenticated (token ...%s)", token[-4:])
            return True

        text = (body or "").lower()
        if _SUCCESS_MARKER in text:
            logger.info("4chan Pass authenticated (text marker, token ...%s)", token[-4:])
            return True

        if any(m in text for m in _FAILURE_MARKERS):
            # Surface the site's message (trimmed) for the operator.
            snippet = " ".join((body or "").split())[:200]
            raise ChanPassError(f"4chan rejected the Pass: {snippet}")

        snippet = " ".join((body or "").split())[:200]
        raise ChanPassError(
            f"4chan auth returned an unrecognized response: {snippet!r}"
        )
    finally:
        try:
            page.close()
        except Exception:  # noqa: BLE001
            pass


def ensure_authenticated(
    context: BrowserContext,
    token: str | None,
    pin: str | None,
    *,
    force: bool = False,
) -> bool:
    """Authenticate the Pass if needed.

    Returns True if the context ends up with a Pass; False if no Pass is
    configured (token/PIN missing) — the caller then posts captcha-gated as
    before. Re-raises ChanPassError on an invalid Pass so the operator notices.

    `force=True` re-auths even if a cookie is already present (used after a
    captcha appears mid-run, which means the existing cookie went stale).
    """
    if not token or not pin:
        logger.info("No 4chan Pass configured — posting will be captcha-gated")
        return False
    if not force and has_pass_cookie(context):
        logger.debug("4chan Pass cookie already present — skipping re-auth")
        return True
    return authenticate(context, token, pin)


__all__ = ["ChanPassError", "authenticate", "ensure_authenticated", "has_pass_cookie"]
