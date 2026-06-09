"""Tests for 4chan Pass auth logic (no real browser).

We fake a Playwright BrowserContext/Page: the context owns a cookie list and
the page's evaluate() returns a canned auth-response body. This lets us exercise
the success/failure detection and the cookie-vs-marker precedence without
launching Chromium.
"""

import pytest

from playwright_worker.chan_auth import (
    ChanPassError,
    authenticate,
    ensure_authenticated,
    has_pass_cookie,
)


class FakePage:
    def __init__(self, body):
        self._body = body
        self.closed = False

    def goto(self, *a, **k):
        pass

    def evaluate(self, *a, **k):
        return self._body

    def close(self):
        self.closed = True


class FakeContext:
    """Fake context. `body` is what the auth fetch returns; `set_cookies_on_post`
    are cookies 4chan would Set-Cookie (we apply them when the page evaluates)."""

    def __init__(self, body="", cookies=None, set_cookies_on_post=None):
        self._body = body
        self._cookies = list(cookies or [])
        self._set_on_post = set_cookies_on_post

    def cookies(self, _url=None):
        return self._cookies

    def new_page(self):
        # Simulate the Set-Cookie side effect of a successful POST.
        if self._set_on_post is not None:
            self._cookies = list(self._set_on_post)
        return FakePage(self._body)


def test_has_pass_cookie_true_on_enabled():
    ctx = FakeContext(cookies=[{"name": "pass_enabled", "value": "1"}])
    assert has_pass_cookie(ctx) is True


def test_has_pass_cookie_true_on_pass_id():
    ctx = FakeContext(cookies=[{"name": "pass_id", "value": "ABC.deadbeef"}])
    assert has_pass_cookie(ctx) is True


def test_has_pass_cookie_false_when_logged_out():
    # Logout sets pass_id=0 / pass_enabled=0 — must not count as authenticated.
    ctx = FakeContext(cookies=[{"name": "pass_id", "value": "0"},
                               {"name": "pass_enabled", "value": "0"}])
    assert has_pass_cookie(ctx) is False


def test_authenticate_succeeds_on_cookie_even_without_text_marker():
    # Real-world case: 4chan sets the cookie but the body has no success text.
    ctx = FakeContext(
        body="<html><body>redirecting...</body></html>",
        set_cookies_on_post=[{"name": "pass_id", "value": "TOK.sig"},
                             {"name": "pass_enabled", "value": "1"}],
    )
    assert authenticate(ctx, "TEST_CHAN_PASS_TOKEN", "TEST_CHAN_PASS_PIN") is True


def test_authenticate_succeeds_on_text_marker():
    ctx = FakeContext(body="<h1>You are authenticated.</h1>")
    assert authenticate(ctx, "TEST_CHAN_PASS_TOKEN", "TEST_CHAN_PASS_PIN") is True


def test_authenticate_rejects_bad_credentials():
    ctx = FakeContext(body="<div>Error: Incorrect Token or PIN.</div>")
    with pytest.raises(ChanPassError, match="rejected"):
        authenticate(ctx, "BAD_CHAN_PASS_TOKEN", "BAD_CHAN_PASS_PIN")


def test_authenticate_requires_token_and_pin():
    ctx = FakeContext()
    with pytest.raises(ChanPassError, match="not configured"):
        authenticate(ctx, "", "")


def test_ensure_authenticated_no_pass_returns_false():
    ctx = FakeContext()
    assert ensure_authenticated(ctx, None, None) is False


def test_ensure_authenticated_skips_when_cookie_present():
    ctx = FakeContext(cookies=[{"name": "pass_enabled", "value": "1"}])
    # body has a failure marker; if it re-authed it would raise. It must not.
    ctx._body = "Error: Incorrect Token or PIN."
    assert ensure_authenticated(ctx, "TEST_CHAN_PASS_TOKEN", "TEST_CHAN_PASS_PIN") is True


def test_ensure_authenticated_force_reauths_even_with_cookie():
    ctx = FakeContext(
        cookies=[{"name": "pass_enabled", "value": "1"}],
        body="<h1>You are authenticated.</h1>",
    )
    assert ensure_authenticated(
        ctx, "TEST_CHAN_PASS_TOKEN", "TEST_CHAN_PASS_PIN", force=True
    ) is True
