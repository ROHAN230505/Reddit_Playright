"""Persistent-context browser bring-up for the Playwright worker.

We use Playwright's `launch_persistent_context` so cookies and login state
are preserved in a dedicated profile directory across runs. This lets the
operator log into Reddit once manually and then let the worker reuse that
session indefinitely.

We deliberately use a *dedicated* profile directory (separate from the
operator's everyday Chrome profile) so we never fight Chrome's profile
lock and so server deployment uses the same code path with a different
USER_DATA_DIR.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager

# Use patchright (the hardened-stealth Playwright fork) — it's what the
# multi-account path uses, and crucially its Chromium is the one registered in
# the Docker image (`patchright install chromium`). Plain `playwright`'s browser
# binary is not installed, so importing it here would fail at launch.
from patchright.sync_api import BrowserContext, sync_playwright

logger = logging.getLogger(__name__)


@contextmanager
def persistent_context(
    user_data_dir: str,
    headless: bool,
    channel: str | None,
):
    os.makedirs(user_data_dir, exist_ok=True)
    with sync_playwright() as p:
        launch_kwargs: dict = {
            "user_data_dir": user_data_dir,
            "headless": headless,
            "viewport": {"width": 1280, "height": 900},
            # NOTE: patchright applies AutomationControlled masking itself —
            # duplicating --disable-blink-features here breaks its stealth.
            "args": [
                "--no-default-browser-check",
                "--no-first-run",
            ],
        }
        if channel:
            launch_kwargs["channel"] = channel
        context: BrowserContext = p.chromium.launch_persistent_context(**launch_kwargs)
        try:
            yield context
        finally:
            try:
                context.close()
            except Exception:  # noqa: BLE001
                logger.exception("Error closing browser context")


def run_login_helper(user_data_dir: str, channel: str | None) -> None:
    """One-off interactive login. The operator runs this once, signs in to
    Reddit by hand, then closes the window. The persisted profile is then
    reused on every worker run."""
    with persistent_context(user_data_dir, headless=False, channel=channel) as context:
        page = context.new_page()
        page.goto("https://www.reddit.com/login/")
        print(
            "\n[playwright_worker] Sign in to Reddit in the opened browser, "
            "then press Enter here to save the session..."
        )
        try:
            input()
        except EOFError:
            pass
        page.goto("https://www.reddit.com/")
        page.wait_for_timeout(1500)
